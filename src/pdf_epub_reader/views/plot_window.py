"""Plotly figure HTML を表示するモードレスウィンドウ。"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget


class PlotWindow(QWidget):
    """Plotly 可視化を独立表示するための軽量ウィンドウ。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.resize(960, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._web_view = QWebEngineView(self)
        layout.addWidget(self._web_view)

    def show_figure_html(self, html: str, title: str) -> None:
        """HTML 化済みの Plotly figure を読み込み、ウィンドウを前面表示する。"""
        self.setWindowTitle(title)
        self._web_view.setHtml(html, QUrl())
        self.show()
        self.raise_()
        self.activateWindow()