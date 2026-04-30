from __future__ import annotations

import os
from typing import cast
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PySide6.QtWidgets import QApplication

from pdf_epub_reader.views.plot_window import PlotWindow


def _get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return cast(QApplication, app)


def test_show_figure_html_updates_title_and_loads_html() -> None:
    _get_app()
    window = PlotWindow()

    with patch.object(window._web_view, "setHtml") as mock_set_html:
        window.show_figure_html("<html><body>plot</body></html>", "Plotly Visualization - Demo")

    assert window.windowTitle() == "Plotly Visualization - Demo"
    mock_set_html.assert_called_once()
    args = mock_set_html.call_args.args
    assert args[0] == "<html><body>plot</body></html>"
    assert args[1].toString() == ""
    assert window.isVisible() is True
    window.close()