# -*- coding: utf-8 -*-
"""
detect.py —— PCB 缺陷检测推理核心（与界面解耦）

界面只需：
    det = PCBDetector()          # 构造时加载模型
    annotated, detections, ms = det.detect(bgr_image)

其中：
    annotated    : 画好框 + 中文类名 + 置信度的 BGR 图（可直接显示/保存）
    detections   : list[dict]，每个 {'cls_en','cls_cn','conf','box':(x1,y1,x2,y2)}
    ms           : 本次推理耗时（毫秒，float）

注意：本文件在沙箱里只做静态检查，真正跑在 RK3588 板上。
凡涉及 rknnlite / 模型缺失，均给清晰中文报错，不直接崩。
"""
import os
import time

import numpy as np

try:
    import cv2
except ImportError as e:
    raise ImportError("缺少 opencv-python，请在板端安装：pip install opencv-python") from e

import theme  # 复用类别名 / 配色（画框颜色、中文名）

# ============================================================
# 模型与解码参数（严格遵守需求文档，改错检测框就乱）
# ============================================================
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL_PATH = os.path.join(HERE, "model", "yolov5s_pcb.rknn")

INPUT_SIZE = 640
CONF_THRESHOLD = 0.6      # 目标置信度阈值
IOU_THRESHOLD = 0.3       # NMS IOU 阈值

CLASS_NAMES_EN = theme.CLASS_NAMES_EN   # 6 类英文（顺序固定）
CLASS_NAMES_CN = theme.CLASS_NAMES_CN   # 6 类中文（一一对应）
NUM_CLASSES = len(CLASS_NAMES_EN)

# --- 坐标约定开关 ---
# 需求文档给的还原公式是 x=(x*640-pad)/scale，即假设单张量输出的 xywh 已归一化到 0~1。
# 这里统一把"解码后的框"换算到 640 像素空间，再做一次性的去 padding / 反缩放。
# 若 probe 在板上确认输出 xywh 其实已经是 640 像素值（不是 0~1），
# 把下面这个开关改成 False 即可，其余逻辑不用动。
OUTPUT_XYWH_NORMALIZED = False

# 3 特征图分支用的标准 YOLOv5 anchors / strides（仅当 probe 显示是 3 个特征图时才走这条路）
_ANCHORS = np.array([
    [[10, 13], [16, 30], [33, 23]],      # P3/8
    [[30, 61], [62, 45], [59, 119]],     # P4/16
    [[116, 90], [156, 198], [373, 326]], # P5/32
], dtype=np.float32)
_STRIDES = [8, 16, 32]


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def letterbox(img, new_size=INPUT_SIZE, color=(0, 0, 0)):
    """等比缩放 + 补黑边。返回 (处理后图, scale, pad_left, pad_top)。"""
    h, w = img.shape[:2]
    scale = min(new_size / h, new_size / w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    pad_w, pad_h = new_size - nw, new_size - nh
    top, bottom = pad_h // 2, pad_h - pad_h // 2
    left, right = pad_w // 2, pad_w - pad_w // 2
    out = cv2.copyMakeBorder(resized, top, bottom, left, right,
                             cv2.BORDER_CONSTANT, value=color)
    return out, scale, left, top


class PCBDetector:
    """PCB 缺陷检测器。构造时加载 RKNN 模型，detect() 做单张推理。"""

    def __init__(self, model_path=DEFAULT_MODEL_PATH):
        self.model_path = model_path
        self.rknn = None
        self.ready = False
        self._load_model()

    # ---------- 模型加载 ----------
    def _load_model(self):
        """加载 RKNN 模型。失败时抛中文异常，由界面捕获后状态栏/弹窗提示。"""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"模型文件不存在：{self.model_path}")

        try:
            from rknnlite.api import RKNNLite
        except ImportError as e:
            raise ImportError(
                "导入 rknnlite 失败：本程序需在装有 rknn-toolkit-lite2 的 RK3588 板上运行。"
            ) from e

        self.rknn = RKNNLite()
        if self.rknn.load_rknn(self.model_path) != 0:
            raise RuntimeError("load_rknn 失败：模型文件可能损坏或不兼容。")
        if self.rknn.init_runtime() != 0:
            raise RuntimeError("init_runtime 失败：NPU 运行时初始化未成功。")
        self.ready = True

    # ---------- 对外主接口 ----------
    def detect(self, bgr):
        """对一张 BGR 图做检测。返回 (带框图BGR, detections, 耗时ms)。"""
        if bgr is None:
            raise ValueError("输入图像为空（imread 可能失败）。")
        if not self.ready or self.rknn is None:
            raise RuntimeError("模型尚未就绪，无法推理。")

        orig_h, orig_w = bgr.shape[:2]

        # 1) 预处理：letterbox + BGR->RGB
        lb, scale, pad_left, pad_top = letterbox(bgr, INPUT_SIZE)
        rgb = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB)
        inp = np.expand_dims(rgb, 0)  # (1,640,640,3)

        # 2) 推理（计时只算 NPU 这段）
        t0 = time.time()
        outputs = self.rknn.inference(inputs=[inp])
        ms = (time.time() - t0) * 1000.0

        # 3) 解码 -> 640 像素空间的候选框
        boxes, scores, class_ids = self._decode(outputs)

        # 4) NMS
        detections = self._nms_and_restore(
            boxes, scores, class_ids, scale, pad_left, pad_top, orig_w, orig_h
        )

        # 5) 画框
        annotated = self.draw(bgr, detections)
        return annotated, detections, ms

    # ---------- 解码 ----------
    def _decode(self, outputs):
        """把模型原始输出解码成 (boxes_xyxy_640, scores, class_ids)。
        boxes 在 640 输入像素空间。自动区分单张量 / 3 特征图两种输出。"""
        arrs = [np.array(o) for o in outputs]

        # 情况 A：单张量 (1, 25200, 11) —— 需求文档声明的标准输出
        if len(arrs) == 1 and arrs[0].ndim == 3 and arrs[0].shape[-1] == (5 + NUM_CLASSES):
            return self._decode_single(arrs[0])

        # 情况 B：3 个分开特征图（80/40/20）—— probe 若显示这种再走这里
        return self._decode_three(arrs)

    def _decode_single(self, pred):
        """解码 (1, N, 5+nc)。返回 640 像素空间 xyxy。"""
        pred = pred[0]  # (N, 11)
        cxcywh = pred[:, 0:4].astype(np.float32)
        obj = pred[:, 4]
        cls = pred[:, 5:5 + NUM_CLASSES]

        # xywh 若归一化到 0~1，则乘 640 回到输入像素空间
        if OUTPUT_XYWH_NORMALIZED:
            cxcywh = cxcywh * INPUT_SIZE

        cls_id = np.argmax(cls, axis=1)
        cls_score = cls[np.arange(cls.shape[0]), cls_id]
        conf = obj * cls_score

        mask = conf >= CONF_THRESHOLD
        if not np.any(mask):
            return np.empty((0, 4)), np.empty((0,)), np.empty((0,), dtype=int)

        cxcywh = cxcywh[mask]
        conf = conf[mask]
        cls_id = cls_id[mask]

        boxes = self._cxcywh_to_xyxy(cxcywh)
        return boxes, conf, cls_id

    def _decode_three(self, arrs):
        """解码 3 个 YOLOv5 特征图（标准 anchor 解码）。返回 640 像素空间 xyxy。
        每个特征图形如 (1, 3*(5+nc), gh, gw) 或 (1, 3, gh, gw, 5+nc)。"""
        all_boxes, all_conf, all_cls = [], [], []
        for li, feat in enumerate(arrs):
            feat = np.array(feat, dtype=np.float32)
            # 统一成 (3, gh, gw, 5+nc)
            if feat.ndim == 4:  # (1, 3*(5+nc), gh, gw)
                _, c, gh, gw = feat.shape
                na = 3
                feat = feat.reshape(na, 5 + NUM_CLASSES, gh, gw).transpose(0, 2, 3, 1)
            elif feat.ndim == 5:  # (1, 3, gh, gw, 5+nc)
                feat = feat[0]
                na, gh, gw = feat.shape[0], feat.shape[1], feat.shape[2]
            else:
                continue

            feat = _sigmoid(feat)
            stride = _STRIDES[li]
            anchors = _ANCHORS[li]

            gy, gx = np.meshgrid(np.arange(gh), np.arange(gw), indexing="ij")
            grid = np.stack((gx, gy), axis=-1).astype(np.float32)  # (gh,gw,2)

            for a in range(na):
                xy = (feat[a, :, :, 0:2] * 2.0 - 0.5 + grid) * stride
                wh = (feat[a, :, :, 2:4] * 2.0) ** 2 * anchors[a]
                obj = feat[a, :, :, 4]
                cls = feat[a, :, :, 5:5 + NUM_CLASSES]

                cxcywh = np.concatenate([xy, wh], axis=-1).reshape(-1, 4)
                obj = obj.reshape(-1)
                cls = cls.reshape(-1, NUM_CLASSES)

                cls_id = np.argmax(cls, axis=1)
                cls_score = cls[np.arange(cls.shape[0]), cls_id]
                conf = obj * cls_score

                m = conf >= CONF_THRESHOLD
                if not np.any(m):
                    continue
                all_boxes.append(self._cxcywh_to_xyxy(cxcywh[m]))
                all_conf.append(conf[m])
                all_cls.append(cls_id[m])

        if not all_boxes:
            return np.empty((0, 4)), np.empty((0,)), np.empty((0,), dtype=int)
        return (np.concatenate(all_boxes, 0),
                np.concatenate(all_conf, 0),
                np.concatenate(all_cls, 0))

    @staticmethod
    def _cxcywh_to_xyxy(cxcywh):
        """中心宽高 -> 左上右下。"""
        xyxy = np.empty_like(cxcywh)
        xyxy[:, 0] = cxcywh[:, 0] - cxcywh[:, 2] / 2.0
        xyxy[:, 1] = cxcywh[:, 1] - cxcywh[:, 3] / 2.0
        xyxy[:, 2] = cxcywh[:, 0] + cxcywh[:, 2] / 2.0
        xyxy[:, 3] = cxcywh[:, 1] + cxcywh[:, 3] / 2.0
        return xyxy

    # ---------- NMS + 坐标还原 ----------
    def _nms_and_restore(self, boxes, scores, class_ids,
                         scale, pad_left, pad_top, orig_w, orig_h):
        """逐类 NMS，并把 640 空间坐标还原到原图。返回 detections 列表。"""
        detections = []
        if boxes.shape[0] == 0:
            return detections

        # 用 cv2.dnn.NMSBoxes，按类别分组做（避免不同类互相压制）
        for c in range(NUM_CLASSES):
            idx = np.where(class_ids == c)[0]
            if idx.size == 0:
                continue
            cls_boxes = boxes[idx]
            cls_scores = scores[idx]

            # NMSBoxes 需要 [x, y, w, h]
            rects = [[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])]
                     for b in cls_boxes]
            keep = cv2.dnn.NMSBoxes(rects, cls_scores.tolist(),
                                    CONF_THRESHOLD, IOU_THRESHOLD)
            if len(keep) == 0:
                continue
            keep = np.array(keep).reshape(-1)

            for k in keep:
                x1, y1, x2, y2 = cls_boxes[k]
                # 去 padding + 反缩放，回到原图坐标
                x1 = (x1 - pad_left) / scale
                y1 = (y1 - pad_top) / scale
                x2 = (x2 - pad_left) / scale
                y2 = (y2 - pad_top) / scale
                # 裁剪到图像范围内
                x1 = int(max(0, min(orig_w - 1, round(x1))))
                y1 = int(max(0, min(orig_h - 1, round(y1))))
                x2 = int(max(0, min(orig_w - 1, round(x2))))
                y2 = int(max(0, min(orig_h - 1, round(y2))))
                if x2 <= x1 or y2 <= y1:
                    continue
                detections.append({
                    "cls_en": CLASS_NAMES_EN[c],
                    "cls_cn": CLASS_NAMES_CN[c],
                    "conf": float(cls_scores[k]),
                    "box": (x1, y1, x2, y2),
                })

        # 按置信度从高到低排序，明细表更好看
        detections.sort(key=lambda d: d["conf"], reverse=True)
        return detections

    # ---------- 画框 ----------
    @staticmethod
    def draw(bgr, detections):
        """在 BGR 图上画框 + 中文类名 + 置信度。每类一种固定颜色。
        说明：OpenCV 的 putText 不支持中文，会显示成 ???，因此标签用
        '英文名 + 置信度'，中文类名在右侧明细表里展示。"""
        img = bgr.copy()
        h, w = img.shape[:2]
        thickness = max(1, int(round(min(h, w) / 400)))
        font_scale = max(0.4, min(h, w) / 1000.0)

        for d in detections:
            x1, y1, x2, y2 = d["box"]
            color = theme.CLASS_COLORS_BGR.get(d["cls_en"], (0, 200, 224))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

            label = f"{d['cls_en']} {d['conf']:.2f}"
            (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX,
                                           font_scale, thickness)
            ty = max(0, y1 - th - bl)
            cv2.rectangle(img, (x1, ty), (x1 + tw + 4, y1), color, -1)
            cv2.putText(img, label, (x1 + 2, y1 - bl),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                        (10, 10, 10), thickness, cv2.LINE_AA)
        return img

    def release(self):
        """释放 NPU 资源。程序退出时调用。"""
        if self.rknn is not None:
            try:
                self.rknn.release()
            except Exception:
                pass
            self.rknn = None
            self.ready = False
