# -*- coding: utf-8 -*-
"""
theme.py —— 全局视觉规范（深色工业风）

所有颜色、字体、QSS 全部集中定义在这里，界面其它模块只从这里引用，
保证整套上位机配色统一。改主题只改这一处。
"""

# ============================================================
# 一、基础配色（固定色值，全局复用）
# ============================================================
COLOR_BG            = "#0F1318"   # 窗口背景（近黑）
COLOR_PANEL         = "#181D24"   # 卡片 / 面板背景
COLOR_PANEL_2       = "#1F252E"   # 输入框 / 表头等次级面
COLOR_BORDER        = "#2A313B"   # 边框 / 分隔线
COLOR_TEXT          = "#E6EAF0"   # 主文字
COLOR_TEXT_WEAK     = "#8A94A3"   # 次要文字 / 说明

# 主强调色（青蓝）
COLOR_ACCENT        = "#00C8E0"   # 主按钮、高亮、FPS、选中态
COLOR_ACCENT_HOVER  = "#2FD6EA"   # hover
COLOR_ACCENT_PRESS  = "#00A6BC"   # pressed

# 语义色
COLOR_OK            = "#28C76F"   # 成功 / 就绪（状态绿点）
COLOR_WARN          = "#FFB020"   # 警告
COLOR_DANGER        = "#FF5C5C"   # 危险 / 告警

# ============================================================
# 二、6 类缺陷固定颜色（检测框 + 统计柱状图共用同一套）
# 顺序与模型类别顺序严格一致，不可调换。
# ============================================================
CLASS_NAMES_EN = [
    "missing_hole", "mouse_bite", "open_circuit",
    "short", "spur", "spurious_copper",
]
CLASS_NAMES_CN = ["漏孔", "鼠咬", "开路", "短路", "毛刺", "杂铜"]

# 每类固定颜色（十六进制，统计图用）
CLASS_COLORS_HEX = {
    "missing_hole":    "#FF5C5C",  # 漏孔
    "mouse_bite":      "#FFB020",  # 鼠咬
    "open_circuit":    "#00C8E0",  # 开路
    "short":           "#A66BFF",  # 短路
    "spur":            "#28C76F",  # 毛刺
    "spurious_copper": "#FF7AC6",  # 杂铜
}

# 同一套颜色的 BGR 元组（OpenCV 画框用，注意 OpenCV 是 BGR 顺序）
def _hex_to_bgr(h):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)

CLASS_COLORS_BGR = {name: _hex_to_bgr(hx) for name, hx in CLASS_COLORS_HEX.items()}

# 中文名 -> 英文 key，便于按类取色
CN_TO_EN = {cn: en for cn, en in zip(CLASS_NAMES_CN, CLASS_NAMES_EN)}


# ============================================================
# 三、字体栈
# ============================================================
# 中文字体栈（带回退，板上可能缺字体）
FONT_CN = '"Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "Microsoft YaHei", sans-serif'
# 数字 / FPS / 耗时等用等宽更专业
FONT_MONO = '"DejaVu Sans Mono", "Consolas", monospace'

# 应用默认字体名（QFont 用，取栈里第一个）
APP_FONT_FAMILY = "Noto Sans CJK SC"
APP_FONT_SIZE = 10  # 正文 10pt


# ============================================================
# 四、全局 QSS（类似 CSS，应用到整个 QApplication）
# ============================================================
def build_qss():
    """拼出全局样式表字符串。用函数包一层，方便用上面的常量做插值。"""
    return f"""
/* ---------- 全局 ---------- */
QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: {FONT_CN};
    font-size: {APP_FONT_SIZE}pt;
}}

QToolTip {{
    background-color: {COLOR_PANEL_2};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    padding: 4px 6px;
}}

/* ---------- 顶部工具条 ---------- */
QToolBar {{
    background-color: {COLOR_PANEL};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER};
    spacing: 8px;
    padding: 8px 10px;
}}

/* ---------- 卡片式分区（用 objectName="Card" 的 QFrame） ---------- */
QFrame#Card {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}

/* 卡片小标题（objectName="CardTitle"） */
QLabel#CardTitle {{
    color: {COLOR_TEXT};
    font-size: 13pt;
    font-weight: bold;
    padding: 2px 0px 6px 0px;
    background: transparent;
}}

/* 画面显示区（objectName="Canvas"） */
QLabel#Canvas {{
    background-color: #0B0E12;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    color: {COLOR_TEXT_WEAK};
}}

/* ---------- 按钮：主操作（objectName="PrimaryBtn"） ---------- */
QPushButton#PrimaryBtn {{
    background-color: {COLOR_ACCENT};
    color: #06222A;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
}}
QPushButton#PrimaryBtn:hover    {{ background-color: {COLOR_ACCENT_HOVER}; }}
QPushButton#PrimaryBtn:pressed  {{ background-color: {COLOR_ACCENT_PRESS}; }}
QPushButton#PrimaryBtn:disabled {{ background-color: {COLOR_PANEL_2}; color: {COLOR_TEXT_WEAK}; }}

/* ---------- 按钮：次操作（普通 QPushButton） ---------- */
QPushButton {{
    background-color: transparent;
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton:hover    {{ border: 1px solid {COLOR_ACCENT}; color: {COLOR_ACCENT}; }}
QPushButton:pressed  {{ background-color: {COLOR_PANEL_2}; }}
QPushButton:disabled {{ color: {COLOR_TEXT_WEAK}; border-color: {COLOR_BORDER}; }}

/* ---------- 表格 ---------- */
QTableWidget {{
    background-color: {COLOR_PANEL};
    alternate-background-color: {COLOR_PANEL_2};
    gridline-color: transparent;
    border: none;
    selection-background-color: rgba(0, 200, 224, 0.25);
    selection-color: {COLOR_TEXT};
}}
QTableWidget::item {{
    padding: 6px 8px;
    border: none;
}}
QHeaderView::section {{
    background-color: {COLOR_PANEL_2};
    color: {COLOR_TEXT_WEAK};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER};
    padding: 8px 8px;
    font-weight: bold;
}}
QTableCornerButton::section {{
    background-color: {COLOR_PANEL_2};
    border: none;
}}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background-color: {COLOR_PANEL_2};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    text-align: center;
    color: {COLOR_TEXT};
    height: 16px;
}}
QProgressBar::chunk {{
    background-color: {COLOR_ACCENT};
    border-radius: 5px;
}}

/* ---------- 状态栏 ---------- */
QStatusBar {{
    background-color: {COLOR_PANEL};
    border-top: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT_WEAK};
    font-size: 9pt;
}}
QStatusBar QLabel {{
    background: transparent;
    padding: 0px 10px;
}}
QStatusBar::item {{ border: none; }}

/* ---------- 滚动条（细、深色、圆角） ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {COLOR_ACCENT_PRESS}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {COLOR_BORDER};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {COLOR_ACCENT_PRESS}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

/* ---------- 指标数值标签（objectName="MetricValue"） ---------- */
QLabel#MetricValue {{
    color: {COLOR_ACCENT};
    font-family: {FONT_MONO};
    font-size: 15pt;
    font-weight: bold;
    background: transparent;
}}
QLabel#MetricLabel {{
    color: {COLOR_TEXT_WEAK};
    font-size: 9pt;
    background: transparent;
}}
"""


# matplotlib 统计图配色（与整体一致），main_window 里引用
MPL_FACE   = COLOR_PANEL      # 图 / 坐标区背景 = 卡片色
MPL_TEXT   = COLOR_TEXT_WEAK  # 文字 / 刻度
MPL_GRID   = COLOR_BORDER     # 网格线（低透明度）
