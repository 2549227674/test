# -*- coding: utf-8 -*-
"""
main_window.py —— 主窗口与界面逻辑（深色工业风）

布局：顶部工具条 + 中间大画面区 + 右侧信息区（明细表 / 统计面板）+ 底部状态栏。
界面只调用 detect.PCBDetector，推理放在 camera_thread 的工作线程里。
所有配色 / 字体 / 样式来自 theme.py。
"""
import os

import cv2
import numpy as np

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QFrame, QFileDialog,
    QHBoxLayout, QVBoxLayout, QGridLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QStatusBar, QProgressBar, QMessageBox, QToolBar, QSizePolicy,
    QAbstractItemView,
)

# matplotlib 嵌入 Qt
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import theme
from detect import PCBDetector
from camera_thread import CameraThread, BatchThread

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")


# ============================================================
# 小工具：彩色状态圆点标签
# ============================================================
def make_dot_label(text, color):
    """生成一个带彩色圆点的状态标签（用于状态栏）。"""
    lab = QLabel(f'<span style="color:{color};">●</span> {text}')
    lab.setTextFormat(Qt.RichText)
    return lab


def make_card(title):
    """生成一张卡片 QFrame，返回 (frame, 内容布局)。卡片顶部带小标题。"""
    card = QFrame()
    card.setObjectName("Card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 12, 12, 12)
    lay.setSpacing(8)
    title_lab = QLabel(title)
    title_lab.setObjectName("CardTitle")
    lay.addWidget(title_lab)
    return card, lay


# ============================================================
# 累计统计管理
# ============================================================
class StatsManager:
    """累计指标：图片/帧数、缺陷总数、平均耗时、平均 FPS、每类数量。"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.frame_count = 0          # 累计检测图片 / 帧数
        self.total_defects = 0        # 累计缺陷总数
        self.total_ms = 0.0           # 累计耗时（算平均用）
        self.per_class = {en: 0 for en in theme.CLASS_NAMES_EN}

    def update(self, detections, ms):
        self.frame_count += 1
        self.total_ms += ms
        self.total_defects += len(detections)
        for d in detections:
            if d["cls_en"] in self.per_class:
                self.per_class[d["cls_en"]] += 1

    @property
    def avg_ms(self):
        return self.total_ms / self.frame_count if self.frame_count else 0.0

    @property
    def avg_fps(self):
        return 1000.0 / self.avg_ms if self.avg_ms > 0 else 0.0


# ============================================================
# 统计柱状图（matplotlib 嵌入）
# ============================================================
class BarChart(FigureCanvas):
    """每类缺陷数量柱状图，配色与整体一致、柱子用每类固定色。"""

    def __init__(self):
        self.fig = Figure(figsize=(3, 2.4), dpi=100)
        self.fig.patch.set_facecolor(theme.MPL_FACE)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self._style_axes()
        self.update_chart({en: 0 for en in theme.CLASS_NAMES_EN})

    def _style_axes(self):
        ax = self.ax
        ax.set_facecolor(theme.MPL_FACE)
        for spine in ax.spines.values():
            spine.set_color(theme.MPL_GRID)
        ax.tick_params(colors=theme.MPL_TEXT, labelsize=8)
        ax.yaxis.label.set_color(theme.MPL_TEXT)
        ax.title.set_color(theme.COLOR_TEXT)

    def update_chart(self, per_class):
        """per_class: {en_name: count}。柱子按每类固定颜色上色。"""
        self.ax.clear()
        self._style_axes()
        names_cn = theme.CLASS_NAMES_CN
        values = [per_class.get(en, 0) for en in theme.CLASS_NAMES_EN]
        colors = [theme.CLASS_COLORS_HEX[en] for en in theme.CLASS_NAMES_EN]

        x = np.arange(len(names_cn))
        bars = self.ax.bar(x, values, color=colors, width=0.62)
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(names_cn, rotation=0, fontsize=8)
        self.ax.grid(axis="y", color=theme.MPL_GRID, alpha=0.35, linewidth=0.8)
        self.ax.set_axisbelow(True)
        # 顶部数值
        ymax = max(values) if any(values) else 1
        self.ax.set_ylim(0, ymax * 1.25 + 0.5)
        for rect, v in zip(bars, values):
            if v > 0:
                self.ax.text(rect.get_x() + rect.get_width() / 2, v,
                             str(v), ha="center", va="bottom",
                             color=theme.COLOR_TEXT, fontsize=8)
        self.fig.tight_layout(pad=0.6)
        self.draw()


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PCB 缺陷检测上位机 · RK3588 边缘 AI")
        self.resize(1360, 820)

        self.detector = None          # PCBDetector，延迟加载
        self.camera_thread = None
        self.batch_thread = None
        self.camera_on = False
        self.stats = StatsManager()

        self._build_ui()
        self._try_load_model()

    # ---------- 构建界面 ----------
    def _build_ui(self):
        self._build_toolbar()
        self._build_statusbar()

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # 中间：大画面区（卡片）
        canvas_card, canvas_lay = make_card("实时画面 / 检测结果")
        self.canvas = QLabel("打开图片或开启摄像头开始检测")
        self.canvas.setObjectName("Canvas")
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setMinimumSize(640, 480)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        canvas_lay.addWidget(self.canvas)
        root.addWidget(canvas_card, stretch=3)

        # 右侧：信息区（上明细表 / 下统计面板）
        right = QVBoxLayout()
        right.setSpacing(12)

        # 上：检测明细表
        table_card, table_lay = make_card("检测明细")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["序号", "缺陷类别", "置信度", "坐标[x1,y1,x2,y2]"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)
        table_lay.addWidget(self.table)
        right.addWidget(table_card, stretch=3)

        # 下：统计面板
        stat_card, stat_lay = make_card("统计面板")
        self.chart = BarChart()
        stat_lay.addWidget(self.chart, stretch=1)
        stat_lay.addWidget(self._build_metrics())
        right.addWidget(stat_card, stretch=4)

        right_wrap = QWidget()
        right_wrap.setLayout(right)
        right_wrap.setMinimumWidth(420)
        right_wrap.setMaximumWidth(480)
        root.addWidget(right_wrap, stretch=0)

        self.setCentralWidget(central)

    def _build_metrics(self):
        """累计指标四宫格。"""
        wrap = QWidget()
        grid = QGridLayout(wrap)
        grid.setContentsMargins(2, 6, 2, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        self.lab_frames = QLabel("0")
        self.lab_defects = QLabel("0")
        self.lab_avgms = QLabel("0.0")
        self.lab_avgfps = QLabel("0.0")

        items = [
            ("累计图片/帧", self.lab_frames),
            ("累计缺陷数", self.lab_defects),
            ("平均耗时(ms)", self.lab_avgms),
            ("平均 FPS", self.lab_avgfps),
        ]
        for i, (name, val) in enumerate(items):
            cell = QVBoxLayout()
            v = val
            v.setObjectName("MetricValue")
            n = QLabel(name)
            n.setObjectName("MetricLabel")
            cell.addWidget(v)
            cell.addWidget(n)
            holder = QWidget()
            holder.setLayout(cell)
            grid.addWidget(holder, i // 2, i % 2)
        return wrap

    def _build_toolbar(self):
        tb = QToolBar("主工具条")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.btn_open = QPushButton("打开图片")
        self.btn_open.setObjectName("PrimaryBtn")
        self.btn_batch = QPushButton("批量检测文件夹")
        self.btn_cam = QPushButton("开始摄像头")
        self.btn_clear = QPushButton("清空统计")

        self.btn_open.clicked.connect(self.on_open_image)
        self.btn_batch.clicked.connect(self.on_batch)
        self.btn_cam.clicked.connect(self.on_toggle_camera)
        self.btn_clear.clicked.connect(self.on_clear_stats)

        for b in (self.btn_open, self.btn_batch, self.btn_cam, self.btn_clear):
            tb.addWidget(b)
            spacer = QWidget()
            spacer.setFixedWidth(8)
            tb.addWidget(spacer)

        # 批量进度条放工具条右侧
        right_spacer = QWidget()
        right_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(right_spacer)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setVisible(False)
        tb.addWidget(self.progress)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.st_model = make_dot_label("模型 未加载", theme.COLOR_TEXT_WEAK)
        self.st_npu = make_dot_label("NPU 未就绪", theme.COLOR_TEXT_WEAK)
        self.st_fps = QLabel("FPS --")
        self.st_ms = QLabel("最近耗时 -- ms")
        for lab in (self.st_fps, self.st_ms):
            lab.setFont(QFont("DejaVu Sans Mono", 9))
        sb.addWidget(self.st_model)
        sb.addWidget(self.st_npu)
        sb.addPermanentWidget(self.st_fps)
        sb.addPermanentWidget(self.st_ms)

    # ---------- 模型加载 ----------
    def _try_load_model(self):
        """启动时尝试加载模型；失败不崩，只在状态栏/弹窗提示。"""
        try:
            self.detector = PCBDetector()
            self.st_model.setText(f'<span style="color:{theme.COLOR_OK};">●</span> 模型 已加载')
            self.st_npu.setText(f'<span style="color:{theme.COLOR_OK};">●</span> NPU 就绪')
        except Exception as e:
            self.detector = None
            self.st_model.setText(f'<span style="color:{theme.COLOR_DANGER};">●</span> 模型 加载失败')
            self.st_npu.setText(f'<span style="color:{theme.COLOR_DANGER};">●</span> NPU 未就绪')
            QMessageBox.warning(self, "模型加载失败",
                                f"{e}\n\n（在 RK3588 板上运行时请确认 rknnlite 与模型文件就绪。）")

    def _ensure_detector(self):
        if self.detector is None or not getattr(self.detector, "ready", False):
            QMessageBox.warning(self, "无法检测", "模型尚未就绪，请确认在 RK3588 板上运行且模型已放好。")
            return False
        return True

    # ---------- 单张图片 ----------
    def on_open_image(self):
        if self.camera_on:
            QMessageBox.information(self, "提示", "请先停止摄像头再做单张检测。")
            return
        if not self._ensure_detector():
            return
        start_dir = os.path.join(HERE, "test_images")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", start_dir if os.path.isdir(start_dir) else HERE,
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp)")
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            QMessageBox.warning(self, "读取失败", "图片打不开或格式不支持。")
            return
        try:
            annotated, detections, ms = self.detector.detect(img)
        except Exception as e:
            QMessageBox.warning(self, "检测出错", str(e))
            return
        self.show_image(annotated)
        self.fill_table(detections)
        self.stats.update(detections, ms)
        self.refresh_stats(ms)

    # ---------- 摄像头 ----------
    def on_toggle_camera(self):
        if self.camera_on:
            self.stop_camera()
        else:
            self.start_camera()

    def start_camera(self):
        if not self._ensure_detector():
            return
        self.camera_thread = CameraThread(self.detector, cam_index=0)
        self.camera_thread.frame_ready.connect(self.on_frame)
        self.camera_thread.error.connect(self.on_thread_error)
        self.camera_thread.start()
        self.camera_on = True
        self.btn_cam.setText("停止摄像头")
        self.btn_cam.setObjectName("PrimaryBtn")
        self._restyle(self.btn_cam)
        self.btn_open.setEnabled(False)
        self.btn_batch.setEnabled(False)

    def stop_camera(self):
        if self.camera_thread is not None:
            self.camera_thread.stop()
            self.camera_thread = None
        self.camera_on = False
        self.btn_cam.setText("开始摄像头")
        self.btn_cam.setObjectName("")
        self._restyle(self.btn_cam)
        self.btn_open.setEnabled(True)
        self.btn_batch.setEnabled(True)

    def on_frame(self, annotated, detections, ms):
        self.show_image(annotated)
        self.fill_table(detections)
        self.stats.update(detections, ms)
        self.refresh_stats(ms)

    # ---------- 批量 ----------
    def on_batch(self):
        if self.camera_on:
            QMessageBox.information(self, "提示", "请先停止摄像头再做批量检测。")
            return
        if not self._ensure_detector():
            return
        folder = QFileDialog.getExistingDirectory(self, "选择待检测文件夹", HERE)
        if not folder:
            return
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.btn_open.setEnabled(False)
        self.btn_cam.setEnabled(False)
        self.btn_batch.setEnabled(False)

        self.batch_thread = BatchThread(self.detector, folder, RESULTS_DIR)
        self.batch_thread.progress.connect(self.on_batch_progress)
        self.batch_thread.one_done.connect(self.on_batch_one)
        self.batch_thread.finished_all.connect(self.on_batch_done)
        self.batch_thread.error.connect(self.on_thread_error)
        self.batch_thread.start()

    def on_batch_progress(self, i, total, detections, ms):
        self.progress.setMaximum(total)
        self.progress.setValue(i)
        self.statusBar().showMessage(f"批量检测中… {i}/{total}", 1500)
        if detections:
            self.stats.update(detections, ms)
            self.refresh_stats(ms)
        else:
            # 即便本图无缺陷也计入帧数
            self.stats.update([], ms)
            self.refresh_stats(ms)

    def on_batch_one(self, out_path, annotated, detections):
        # 预览最近一张结果，并刷新明细表
        self.show_image(annotated)
        self.fill_table(detections)

    def on_batch_done(self, done, total_defects):
        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self.btn_cam.setEnabled(True)
        self.btn_batch.setEnabled(True)
        QMessageBox.information(
            self, "批量检测完成",
            f"共处理 {done} 张图片，发现缺陷 {total_defects} 处。\n带框结果已保存到：\n{RESULTS_DIR}")

    # ---------- 清空统计 ----------
    def on_clear_stats(self):
        self.stats.reset()
        self.table.setRowCount(0)
        self.chart.update_chart(self.stats.per_class)
        self.lab_frames.setText("0")
        self.lab_defects.setText("0")
        self.lab_avgms.setText("0.0")
        self.lab_avgfps.setText("0.0")
        self.st_fps.setText("FPS --")
        self.st_ms.setText("最近耗时 -- ms")

    # ---------- 显示与刷新 ----------
    def show_image(self, bgr):
        """BGR 图 -> QPixmap -> QLabel，自适应缩放且不变形。"""
        if bgr is None:
            return
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        scaled = pix.scaled(self.canvas.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.canvas.setPixmap(scaled)

    def fill_table(self, detections):
        self.table.setRowCount(0)
        for i, d in enumerate(detections, start=1):
            r = self.table.rowCount()
            self.table.insertRow(r)
            x1, y1, x2, y2 = d["box"]
            cells = [
                str(i),
                d["cls_cn"],
                f"{d['conf']:.2f}",
                f"[{x1},{y1},{x2},{y2}]",
            ]
            for c, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                if c == 0 or c == 2:
                    item.setTextAlignment(Qt.AlignCenter)
                # 类别列用该类固定色标识
                if c == 1:
                    color = theme.CLASS_COLORS_HEX.get(d["cls_en"])
                    if color:
                        from PyQt5.QtGui import QColor
                        item.setForeground(QColor(color))
                self.table.setItem(r, c, item)

    def refresh_stats(self, last_ms):
        self.lab_frames.setText(str(self.stats.frame_count))
        self.lab_defects.setText(str(self.stats.total_defects))
        self.lab_avgms.setText(f"{self.stats.avg_ms:.1f}")
        self.lab_avgfps.setText(f"{self.stats.avg_fps:.1f}")
        self.chart.update_chart(self.stats.per_class)
        self.st_fps.setText(f"FPS {self.stats.avg_fps:4.1f}")
        self.st_ms.setText(f"最近耗时 {last_ms:5.1f} ms")

    # ---------- 杂项 ----------
    def on_thread_error(self, msg):
        self.statusBar().showMessage(msg, 5000)
        if self.camera_on:
            self.stop_camera()
        QMessageBox.warning(self, "运行提示", msg)

    @staticmethod
    def _restyle(widget):
        """objectName 改了之后强制刷新 QSS。"""
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def resizeEvent(self, event):
        # 窗口缩放时，让当前画面重新适配（若有 pixmap）
        super().resizeEvent(event)

    def closeEvent(self, event):
        # 退出时安全释放线程与 NPU
        try:
            if self.camera_thread is not None:
                self.camera_thread.stop()
            if self.batch_thread is not None:
                self.batch_thread.stop()
            if self.detector is not None:
                self.detector.release()
        except Exception:
            pass
        super().closeEvent(event)
