from __future__ import annotations

import os
from pathlib import Path
from typing import cast
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from pdf_epub_reader.dto import PlotTabPayload
from pdf_epub_reader.services.translation_service import TranslationService
from pdf_epub_reader.views.plot_window import PlotWindow


def _get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return cast(QApplication, app)


def test_show_figures_builds_splitter_tabs_and_syncs_selection() -> None:
    _get_app()
    window = PlotWindow()

    with patch("pdf_epub_reader.views.plot_window.QWebEngineView.load") as mock_load:
        window.show_figures(
            [
                PlotTabPayload(
                    title="Plotly Visualization - Demo",
                    html="<html><body>plot</body></html>",
                    spec_source_text='{"data": []}',
                    spec_language="json",
                    spec_index=0,
                )
            ]
        )

    assert window.windowTitle() == "Plotly Visualization - Demo"
    assert window._splitter.orientation() == Qt.Orientation.Horizontal
    assert window._spec_list.count() == 1
    assert window._tab_widget.count() == 1
    assert window._spec_list.currentRow() == 0
    assert window._tab_widget.currentIndex() == 0
    mock_load.assert_called_once()
    loaded_url = mock_load.call_args.args[0]
    assert loaded_url.isLocalFile() is True
    loaded_path = Path(loaded_url.toLocalFile())
    assert loaded_path.name == "plot_0001.html"
    assert loaded_path.read_text(encoding="utf-8") == "<html><body>plot</body></html>"
    assert window.isVisible() is True
    window.close()


def test_selection_sync_keeps_list_and_tabs_aligned() -> None:
    _get_app()
    window = PlotWindow()

    with patch("pdf_epub_reader.views.plot_window.QWebEngineView.load"):
        window.show_figures(
            [
                PlotTabPayload(
                    title="Plot A",
                    html="<html><body>plot</body></html>",
                    spec_source_text="{}",
                    spec_language="json",
                    spec_index=0,
                ),
                PlotTabPayload(
                    title="Plot B",
                    html="<html><body>plot2</body></html>",
                    spec_source_text="{}",
                    spec_language="json",
                    spec_index=1,
                ),
            ]
        )

    window._spec_list.setCurrentRow(1)
    assert window._tab_widget.currentIndex() == 1

    window._tab_widget.setCurrentIndex(0)
    assert window._spec_list.currentRow() == 0


def test_toolbar_actions_copy_source_and_reload_tab() -> None:
    _get_app()
    window = PlotWindow()
    copied_texts: list[str] = []
    rerendered: list[PlotTabPayload] = []

    class _Clipboard:
        def setText(self, text: str) -> None:
            copied_texts.append(text)

        def setPixmap(self, pixmap) -> None:
            copied_texts.append("pixmap")

    with patch(
        "pdf_epub_reader.views.plot_window.QWebEngineView.load"
    ) as mock_load:
        with patch(
            "pdf_epub_reader.views.plot_window.QApplication.clipboard",
            return_value=_Clipboard(),
        ):
            window.show_figures(
                [
                    PlotTabPayload(
                        title="Plot A",
                        html="<html><body>plot</body></html>",
                        spec_source_text='{"data": []}',
                        spec_language="json",
                        spec_index=0,
                    )
                ]
            )
            window.set_on_rerender_requested(rerendered.append)

            window._tab_states[0].copy_source_action.trigger()
            assert copied_texts == ['{"data": []}']

            window._tab_states[0].rerender_action.trigger()
            assert len(rerendered) == 1
            assert rerendered[0].spec_source_text == '{"data": []}'

            window.reload_tab(
                0,
                PlotTabPayload(
                    title="Plot A",
                    html="<html><body>plot updated</body></html>",
                    spec_source_text='{"data": [1]}',
                    spec_language="json",
                    spec_index=0,
                ),
            )

    assert mock_load.call_count == 2
    assert window._tab_states[0].html_path.name == "plot_0002.html"


def test_plot_window_texts_are_applied_to_chrome() -> None:
    _get_app()
    texts = TranslationService().build_plot_window_texts("ja")
    window = PlotWindow(texts=texts)

    with patch("pdf_epub_reader.views.plot_window.QWebEngineView.load"):
        window.show_figures(
            [
                PlotTabPayload(
                    title="Plot A",
                    html="<html><body>plot</body></html>",
                    spec_source_text="{}",
                    spec_language="json",
                    spec_index=0,
                )
            ]
        )

    assert window._spec_toggle_button.text() == "Spec 一覧"
    assert window._tab_states[0].rerender_action.text() == "再描画"
    assert window._tab_states[0].copy_source_action.text() == "ソースをコピー"
    assert window._tab_states[0].copy_png_action.text() == "PNG をコピー"
    assert window._tab_states[0].save_action.text() == "保存"
    assert window._tab_states[0].save_action.toolTip() == (
        "PNG 保存は kaleido をインストールすると利用できます。"
    )
    assert window._tab_widget.tabText(0) == "Plot A"
    assert window._spec_list.item(0).text() == "Plot A"
    window.close()


def test_close_event_cleans_up_temp_html_directory() -> None:
    _get_app()
    window = PlotWindow()

    with patch("pdf_epub_reader.views.plot_window.QWebEngineView.load"):
        window.show_figures(
            [
                PlotTabPayload(
                    title="Plotly Visualization - Demo",
                    html="<html><body>plot</body></html>",
                    spec_source_text='{"data": []}',
                    spec_language="json",
                    spec_index=0,
                )
            ]
        )

    assert window._tab_states[0].html_path.exists() is True
    html_path = window._tab_states[0].html_path
    window.close()

    assert html_path.exists() is False
    assert window._temp_dir is None
    assert window._tab_states == []