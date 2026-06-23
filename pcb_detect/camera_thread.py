# -*- coding: utf-8 -*-
"""
camera_thread.py —— 摄像头 / 批量推理工作线程（QThread）

为什么用线程：推理（NPU）放主线程会把界面卡死。这里把抓帧+推理放到
工作线程，用 pyqtSignal 把"带框画面 + 检测结果 + 耗时"发回主线程刷新。

包含两个线程：
    CameraThread  —— 摄像头逐帧实时检测
    BatchThread   —— 文件夹批量检测（结果存 results/）
"""
import os

import cv2

from PyQt5.QtCore import QThread, pyqtSignal


class CameraThread(QThread):
    """摄像头实时检测线程。

    信号：
        frame_ready(object, list, float) : (带框BGR图, detections, 耗时ms)
        error(str)                       : 出错时的中文提示
    """
    frame_ready = pyqtSignal(object, list, float)
    error = pyqtSignal(str)

    def __init__(self, detector, cam_index=0, parent=None):
        super().__init__(parent)
        self.detector = detector
        self.cam_index = cam_index
        self._running = False
        self.cap = None

    def run(self):
        # 打开摄像头，失败给中文提示后退出
        self.cap = cv2.VideoCapture(self.cam_index)
        if not self.cap or not self.cap.isOpened():
            self.error.emit(f"无法打开摄像头（设备号 {self.cam_index}），请检查 USB 摄像头连接。")
            return

        self._running = True
        while self._running:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                self.error.emit("摄像头读取帧失败，可能被拔出或被其它程序占用。")
                break
            try:
                annotated, detections, ms = self.detector.detect(frame)
            except Exception as e:
                self.error.emit(f"推理出错：{e}")
                break
            # 把结果发回主线程刷新
            self.frame_ready.emit(annotated, detections, ms)

        # 收尾：安全释放摄像头
        self._release_cap()

    def stop(self):
        """请求停止并等待线程退出（主线程调用）。"""
        self._running = False
        self.wait(2000)
        self._release_cap()

    def _release_cap(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None


class BatchThread(QThread):
    """文件夹批量检测线程。

    信号：
        progress(int, int, list, float) : (当前序号, 总数, 当前图 detections, 耗时ms)
        one_done(str, object, list)     : (输出文件路径, 带框图, detections) —— 可用于预览
        finished_all(int, int)          : (处理图片数, 累计缺陷数)
        error(str)
    """
    progress = pyqtSignal(int, int, list, float)
    one_done = pyqtSignal(str, object, list)
    finished_all = pyqtSignal(int, int)
    error = pyqtSignal(str)

    IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

    def __init__(self, detector, folder, out_dir, parent=None):
        super().__init__(parent)
        self.detector = detector
        self.folder = folder
        self.out_dir = out_dir
        self._running = True

    def run(self):
        try:
            files = [f for f in sorted(os.listdir(self.folder))
                     if f.lower().endswith(self.IMG_EXTS)]
        except Exception as e:
            self.error.emit(f"读取文件夹失败：{e}")
            return

        if not files:
            self.error.emit("该文件夹下没有可识别的图片（jpg/png/bmp 等）。")
            return

        os.makedirs(self.out_dir, exist_ok=True)
        total = len(files)
        total_defects = 0
        done = 0

        for i, name in enumerate(files, start=1):
            if not self._running:
                break
            path = os.path.join(self.folder, name)
            img = cv2.imread(path)
            if img is None:
                # 跳过坏图，但不中断整体批处理
                self.progress.emit(i, total, [], 0.0)
                continue
            try:
                annotated, detections, ms = self.detector.detect(img)
            except Exception as e:
                self.error.emit(f"处理 {name} 出错：{e}")
                break

            out_path = os.path.join(self.out_dir, f"det_{name}")
            try:
                cv2.imwrite(out_path, annotated)
            except Exception:
                out_path = ""

            total_defects += len(detections)
            done += 1
            self.one_done.emit(out_path, annotated, detections)
            self.progress.emit(i, total, detections, ms)

        self.finished_all.emit(done, total_defects)

    def stop(self):
        self._running = False
        self.wait(3000)
