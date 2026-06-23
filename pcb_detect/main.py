# -*- coding: utf-8 -*-
"""
main.py —— 程序入口

在 RK3588 板上运行：
    python3 main.py
"""
import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

import theme
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # 全局默认字体（中文栈在 QSS 里，这里给个兜底 family + 字号）
    app.setFont(QFont(theme.APP_FONT_FAMILY, theme.APP_FONT_SIZE))

    # 应用全局 QSS（深色工业风）
    app.setStyleSheet(theme.build_qss())

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
