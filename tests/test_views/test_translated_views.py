from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QWidget

from pdf_epub_reader.dto import CacheStatus
from pdf_epub_reader.services.translation_service import TranslationService
from pdf_epub_reader.views.bookmark_panel import BookmarkPanelView
from pdf_epub_reader.views.cache_dialog import CacheDialog
from pdf_epub_reader.views.language_dialog import LanguageDialog
from pdf_epub_reader.views.main_window import MainWindow
from pdf_epub_reader.views.settings_dialog import SettingsDialog
from pdf_epub_reader.views.side_panel_view import SidePanelView


_APP = QApplication.instance() or QApplication([])
_TRANSLATIONS = TranslationService()


def _button_texts(widget: QWidget) -> set[str]:
    return {button.text() for button in widget.findChildren(QPushButton)}


def _checkbox_texts(widget: QWidget) -> set[str]:
    return {checkbox.text() for checkbox in widget.findChildren(QCheckBox)}


class TestSettingsDialogTranslations:
    def test_english_static_strings_are_translated(self) -> None:
        dialog = SettingsDialog(ui_language="en")
        dialog.apply_ui_texts(_TRANSLATIONS.build_settings_dialog_texts("en"))

        assert dialog.windowTitle() == "Preferences"
        assert dialog._tabs.tabText(0) == "Rendering"
        assert dialog._tabs.tabText(1) == "Detection"
        assert dialog._tabs.tabText(2) == "AI Models"
        assert dialog._tabs.tabText(3) == "Export"
        assert dialog._tabs.tabText(4) == "Visualization"
        assert "Fetch Models" in _button_texts(dialog)
        assert "Browse..." in _button_texts(dialog)
        assert "Reset to Defaults" in _button_texts(dialog)
        assert "High-quality downscale (Lanczos)" in _checkbox_texts(dialog)
        assert "Include explanation" in _checkbox_texts(dialog)
        assert "Include YAML frontmatter" in _checkbox_texts(dialog)
        assert (
            dialog._plotly_multi_spec_prompt_radio.text()
            == "When multiple Plotly specs are found, ask which one to open"
        )
        assert (
            dialog._plotly_multi_spec_first_only_radio.text()
            == "When multiple Plotly specs are found, open only the first one"
        )
        assert dialog._plotly_timeout_label.text() == "Plotly sandbox timeout:"
        assert dialog._plotly_timeout_spin.suffix() == " sec"

        dialog.set_fetch_models_loading(True)

        assert dialog._fetch_status_label.text() == "Fetching..."
        dialog.close()


class TestCacheDialogTranslations:
    def test_english_static_strings_are_translated(self) -> None:
        dialog = CacheDialog(ui_language="en")
        dialog.apply_ui_texts(_TRANSLATIONS.build_cache_dialog_texts("en"))

        assert dialog.windowTitle() == "Cache Management"
        assert dialog._tabs.tabText(0) == "Current Cache"
        assert dialog._tabs.tabText(1) == "Cache Browser"
        assert "Update TTL" in _button_texts(dialog)
        assert "Delete Selected" in _button_texts(dialog)
        assert "Close" in _button_texts(dialog)
        headers = [dialog._table.horizontalHeaderItem(i).text() for i in range(5)]
        assert headers == ["Name", "Model", "Display Name", "Tokens", "Expire Time"]

        dialog.set_cache_ttl_seconds(125)
        dialog.set_cache_is_active(True)
        assert dialog._ttl_label.text() == "2 min 5 sec"
        assert dialog._active_label.text() == "Active"

        dialog.set_cache_token_count(None)
        dialog.set_cache_ttl_seconds(None)
        dialog.set_cache_expire_time(None)
        assert dialog._token_label.text() == "Not set"
        assert dialog._ttl_label.text() == "Not set"
        assert dialog._expire_label.text() == "Not set"

        dialog.set_cache_is_active(False)
        assert dialog._active_label.text() == "Inactive"
        dialog.close()

    def test_cache_list_uses_api_display_name(self) -> None:
        dialog = CacheDialog(ui_language="en")
        dialog.apply_ui_texts(_TRANSLATIONS.build_cache_dialog_texts("en"))
        dialog.set_cache_list(
            [
                CacheStatus(
                    cache_name="caches/app-1",
                    display_name="pdf-reader: sample.pdf",
                    model_name="models/gemini-test",
                    token_count=123,
                    expire_time="2026-04-11T12:00:00Z",
                )
            ]
        )

        assert dialog._table.item(0, 0).text() == "caches/app-1"
        assert dialog._table.item(0, 2).text() == "pdf-reader: sample.pdf"
        dialog.close()


class TestLanguageDialogTranslations:
    def test_english_strings_are_translated(self) -> None:
        dialog = LanguageDialog(ui_language="en")
        dialog.apply_ui_texts(_TRANSLATIONS.build_language_dialog_texts("en"))
        dialog.set_available_languages(
            [("ja", "日本語"), ("en", "English")]
        )

        assert dialog.windowTitle() == "Language"
        assert dialog._description_label.text() == (
            "Choose the language used in the interface."
        )
        assert dialog._label.text() == "Display Language:"
        assert dialog._language_combo.itemText(0) == "日本語"
        assert dialog._language_combo.itemText(1) == "English"
        assert "OK" in _button_texts(dialog)
        assert "Cancel" in _button_texts(dialog)

        dialog.set_selected_language("en")

        assert dialog.get_selected_language() == "en"
        dialog.close()


class TestBookmarkPanelTranslations:
    def test_header_updates_with_language_change(self) -> None:
        panel = BookmarkPanelView(ui_language="en")
        panel.apply_ui_texts(_TRANSLATIONS.build_bookmark_panel_texts("en"))

        assert panel._tree.headerItem().text(0) == "Bookmarks"

        panel.apply_ui_texts(_TRANSLATIONS.build_bookmark_panel_texts("ja"))

        assert panel._tree.headerItem().text(0) == "しおり"
        panel.close()


class TestMainWindowTranslations:
    def test_language_application_updates_menu_status_and_overlay(self) -> None:
        bookmark_panel = BookmarkPanelView(ui_language="en")
        side_panel = QWidget()
        window = MainWindow(
            side_panel=side_panel,
            bookmark_panel=bookmark_panel,
            ui_language="en",
        )
        window.apply_ui_texts(_TRANSLATIONS.build_main_window_texts("en"))

        assert window.windowTitle() == "Gem Read"
        assert window._file_menu.title() == "&File"
        assert window._status_label.text() == "Ready"
        assert bookmark_panel._tree.headerItem().text(0) == "Bookmarks"
        assert window._overlay._page_label.text() == "Page:"

        window.apply_ui_texts(_TRANSLATIONS.build_main_window_texts("ja"))

        assert window._file_menu.title() == "ファイル"
        assert window._open_action.text() == "開く..."
        assert window._status_label.text() == "準備完了"
        assert bookmark_panel._tree.headerItem().text(0) == "しおり"
        assert window._overlay._page_label.text() == "ページ:"
        window.close()
        bookmark_panel.close()
        side_panel.close()

    def test_running_operation_ui_uses_generic_status_surface(self) -> None:
        bookmark_panel = BookmarkPanelView(ui_language="en")
        side_panel = QWidget()
        window = MainWindow(
            side_panel=side_panel,
            bookmark_panel=bookmark_panel,
            ui_language="en",
        )

        observed: list[str] = []

        window.show_running_operation(
            "Running Gemini request...",
            lambda: observed.append("cancelled"),
            "Cancel",
        )
        assert window._running_operation_label.text() == "Running Gemini request..."
        assert window._running_operation_cancel_label.text() == '<a href="#">Cancel</a>'
        window._handle_running_operation_cancel_link("#")
        assert observed == ["cancelled"]

        window.clear_running_operation()
        assert not window._running_operation_label.isVisible()
        assert not window._running_operation_cancel_label.isVisible()

        window.show_plotly_running(observed.append)
        assert window._running_operation_label.text() == "Plotly sandbox running"
        assert window._running_operation_cancel_label.text() == '<a href="#">Cancel</a>'
        window.clear_plotly_running()
        assert not window._running_operation_label.isVisible()
        assert not window._running_operation_cancel_label.isVisible()

        window.close()
        bookmark_panel.close()
        side_panel.close()


class TestSidePanelTranslations:
    def test_language_application_updates_static_strings(self) -> None:
        panel = SidePanelView(ui_language="en")
        panel.apply_ui_texts(_TRANSLATIONS.build_side_panel_texts("en"))

        assert panel._selection_section._toggle_btn.text().endswith("Selections")
        assert panel._selection_summary_label.text() == "Selections 0"
        assert panel._translate_btn.text() == "Translate"
        assert panel._explain_btn.text() == "Translate with Explanation"
        assert panel._export_btn.text() == "Export Markdown"
        assert panel._plotly_toggle_btn.text() == "📊"
        assert panel._plotly_toggle_btn.toolTip() == "Plotly visualization is disabled"
        assert panel._submit_btn.text() == "Submit"
        assert panel._tab_widget.tabText(0) == "Translation"
        assert panel._tab_widget.tabText(1) == "Custom Prompt"
        assert panel._cache_label.text() == "Cache Status: ---"

        panel.apply_ui_texts(_TRANSLATIONS.build_side_panel_texts("ja"))

        assert panel._selection_section._toggle_btn.text().endswith("選択一覧")
        assert panel._selection_summary_label.text() == "選択 0 件"
        assert panel._translate_btn.text() == "翻訳"
        assert panel._explain_btn.text() == "解説付き翻訳"
        assert panel._export_btn.text() == "Markdown 保存"
        assert panel._plotly_toggle_btn.text() == "📊"
        assert panel._plotly_toggle_btn.toolTip() == "Plotly 可視化は無効です"
        assert panel._submit_btn.text() == "送信"
        assert panel._tab_widget.tabText(0) == "翻訳"
        assert panel._tab_widget.tabText(1) == "カスタムプロンプト"
        assert panel._cache_label.text() == "キャッシュステータス: ---"
        panel.close()

    def test_ai_request_running_ui_is_shown_inside_side_panel(self) -> None:
        panel = SidePanelView(ui_language="en")
        panel.apply_ui_texts(_TRANSLATIONS.build_side_panel_texts("en"))

        observed: list[str] = []

        panel.show_ai_request_running(
            "Running Gemini request...",
            "Cancel",
            lambda: observed.append("cancelled"),
        )

        assert not panel._ai_request_row.isHidden()
        assert panel._ai_request_status_label.text() == "Running Gemini request..."
        assert panel._ai_request_cancel_btn.text() == "Cancel"

        panel._ai_request_cancel_btn.click()

        assert observed == ["cancelled"]

        panel.clear_ai_request_running()

        assert panel._ai_request_row.isHidden()
        panel.close()

    def test_plotly_button_cycles_through_three_modes(self) -> None:
        panel = SidePanelView(ui_language="en")
        panel.apply_ui_texts(_TRANSLATIONS.build_side_panel_texts("en"))
        observed: list[str] = []
        panel.set_on_plotly_mode_changed(observed.append)

        panel._plotly_toggle_btn.click()
        panel._plotly_toggle_btn.click()
        panel._plotly_toggle_btn.click()

        assert observed == ["json", "python", "off"]
        assert panel._plotly_toggle_btn.text() == "📊"
        assert panel._plotly_toggle_btn.toolTip() == "Plotly visualization is disabled"
        panel.close()

    def test_plotly_mode_menu_action_updates_button(self) -> None:
        panel = SidePanelView(ui_language="en")
        panel.apply_ui_texts(_TRANSLATIONS.build_side_panel_texts("en"))

        panel._plotly_mode_actions["python"].trigger()

        assert panel._plotly_toggle_btn.text() == "📊 Py"
        assert panel._plotly_toggle_btn.toolTip() == (
            "Request sandboxed Plotly Python when the response can be visualized"
        )

        panel.set_plotly_mode("json")
        assert panel._plotly_toggle_btn.text() == "📊 J"
        assert panel._plotly_toggle_btn.toolTip() == (
            "Request Plotly JSON when the response can be visualized"
        )
        panel.close()

    def test_model_combo_stays_placeholder_until_selection(self) -> None:
        panel = SidePanelView(ui_language="en")
        texts = _TRANSLATIONS.build_side_panel_texts("en")
        panel.apply_ui_texts(texts)

        panel.set_available_models(["model-a", "model-b"])
        panel.set_selected_model("")
        panel.set_model_combo_enabled(False)

        assert panel._model_combo.currentIndex() == -1
        assert panel._model_combo.placeholderText() == texts.model_unset_placeholder
        assert panel._model_combo.isEnabled() is False

        panel.set_selected_model("model-b")
        panel.set_model_combo_enabled(True)

        assert panel._model_combo.currentText() == "model-b"
        assert panel._model_combo.isEnabled() is True
        panel.close()