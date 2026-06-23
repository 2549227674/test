# -*- coding: utf-8 -*-
"""
probe.py —— 输出形状探针（最先在板上跑这个）

目的：加载 rknn 模型、跑一张测试图，打印模型输出张量的形状/数量，
用来确认解码方式。按需求文档，期望输出是单张量 (1, 25200, 11)；
若实际是 3 个分开特征图（80/40/20），把打印结果贴回来，再据此调 detect.py。

用法（在 RK3588 板上）：
    python3 probe.py                      # 自动取 test_images 里第一张图
    python3 probe.py test_images/xxx.jpg  # 指定一张图
"""
import os
import sys
import glob

import numpy as np

# 这两个库只有板上才有，导入失败给清晰中文提示，不要让程序莫名崩溃
try:
    import cv2
except ImportError:
    print("[错误] 缺少 opencv-python，请确认板端已安装 cv2。")
    sys.exit(1)

try:
    from rknnlite.api import RKNNLite
except ImportError:
    print("[错误] 导入 rknnlite 失败。本脚本必须在装有 rknn-toolkit-lite2 的 RK3588 板上运行。")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "model", "yolov5s_pcb.rknn")
INPUT_SIZE = 640


def letterbox(img, new_size=640, color=(0, 0, 0)):
    """等比缩放 + 补黑边，返回处理后图、缩放比、左/上 padding。"""
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


def pick_image(argv):
    """取命令行指定的图，或 test_images 下第一张。"""
    if len(argv) > 1:
        return argv[1]
    candidates = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        candidates += glob.glob(os.path.join(HERE, "test_images", ext))
    return candidates[0] if candidates else None


def main():
    if not os.path.exists(MODEL_PATH):
        print(f"[错误] 找不到模型文件：{MODEL_PATH}")
        return

    img_path = pick_image(sys.argv)
    if not img_path or not os.path.exists(img_path):
        print("[错误] 找不到测试图片，请在 test_images/ 放一张，或命令行指定路径。")
        return

    print(f"[信息] 模型：{MODEL_PATH}")
    print(f"[信息] 测试图：{img_path}")

    # 1) 加载模型
    rknn = RKNNLite()
    print("[信息] 正在加载 RKNN 模型 ...")
    if rknn.load_rknn(MODEL_PATH) != 0:
        print("[错误] load_rknn 失败。")
        return
    # RK3588 三核 NPU，自动分配；若失败可改 CORE_MASK
    if rknn.init_runtime() != 0:
        print("[错误] init_runtime 失败。")
        return
    print("[信息] 模型加载成功，NPU 运行时就绪。")

    # 2) 预处理一张图
    img = cv2.imread(img_path)
    if img is None:
        print("[错误] 图片读取失败（路径或格式问题）。")
        return
    lb, scale, left, top = letterbox(img, INPUT_SIZE)
    rgb = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB)
    # RKNN 量化模型通常转换时已配 mean/std，这里一般不需要再 /255。
    # 送入 (1, H, W, 3)。
    inp = np.expand_dims(rgb, 0)

    # 3) 推理
    print("[信息] 正在推理 ...")
    outputs = rknn.inference(inputs=[inp])

    # 4) 打印关键信息
    print("\n========== 探针结果 ==========")
    print(f"输出张量个数: {len(outputs)}")
    for i, out in enumerate(outputs):
        print(f"  outputs[{i}].shape = {np.array(out).shape}")
    print("================================")
    print("判读：")
    print("  · 若 outputs[0].shape == (1, 25200, 11) → 按单张量解码（detect.py 默认路径）。")
    print("  · 若是 3 个特征图（如 (1,255,80,80)/(1,255,40,40)/(1,255,20,20)）")
    print("    → 走 detect.py 的 3 特征图解码分支；把上面形状贴回来确认。")

    rknn.release()


if __name__ == "__main__":
    main()
