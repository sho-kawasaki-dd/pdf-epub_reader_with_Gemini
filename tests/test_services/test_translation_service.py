from __future__ import annotations

from pdf_epub_reader.services.translation_service import TranslationService


class TestTranslationService:
    def test_translate_returns_requested_language(self) -> None:
        service = TranslationService()

        assert service.translate("common.not_set", "ja") == "未設定"

    def test_translate_falls_back_to_english_when_key_missing_in_language(self) -> None:
        service = TranslationService(
            translations={
                "en": {"settings.ui_language.label": "Display Language"},
                "ja": {},
            }
        )

        assert (
            service.translate("settings.ui_language.label", "ja")
            == "Display Language"
        )

    def test_translate_normalizes_language_alias_and_formats_text(self) -> None:
        service = TranslationService(
            translations={
                "en": {"status.greeting": "Hello {name}"},
                "ja": {"status.greeting": "こんにちは {name}"},
            }
        )

        assert (
            service.translate("status.greeting", "en-US", name="Alice")
            == "Hello Alice"
        )

    def test_translate_returns_key_when_missing_in_all_languages(self) -> None:
        service = TranslationService()

        assert service.translate("missing.key", "ja") == "missing.key"

    def test_build_main_window_texts_keeps_accelerators_only_in_english(self) -> None:
        service = TranslationService()

        english = service.build_main_window_texts("en")
        japanese = service.build_main_window_texts("ja")

        assert english.file_menu_title == "&File"
        assert english.open_action_text == "&Open..."
        assert japanese.file_menu_title == "ファイル"
        assert japanese.open_action_text == "開く..."

    def test_build_side_panel_texts_includes_export_button_label(self) -> None:
        service = TranslationService()

        texts = service.build_side_panel_texts("ja")

        assert texts.export_button_text == "Markdown 保存"
        assert (
            texts.plotly_toggle_tooltip
            == "可視化可能な応答では Plotly JSON の出力を要求します"
        )
        assert texts.plotly_toggle_tooltip_off == "Plotly 可視化は無効です"
        assert (
            texts.plotly_toggle_tooltip_python
            == "可視化可能な応答では sandboxed Plotly Python の出力を要求します"
        )

    def test_build_plotly_texts_returns_localized_dialog_and_status_texts(self) -> None:
        service = TranslationService()

        texts = service.build_plotly_texts("en")

        assert texts.multi_select_dialog_title == "Choose Plotly Visualization"
        assert texts.multi_select_cancel_button_text == "Cancel"
        assert texts.spec_fallback_title_template == "Plot {index}"
        assert (
            texts.restore_failed_message_template
            == "Failed to restore the Plotly figure: {details}"
        )
        assert texts.window_title_template == "Plotly Visualization - {title}"
        assert texts.sandbox_running_message == "Running Plotly sandbox..."
        assert texts.sandbox_cancel_link_text == "Cancel"

    def test_build_plot_window_texts_returns_localized_toolbar_labels(self) -> None:
        service = TranslationService()

        texts = service.build_plot_window_texts("ja")

        assert texts.spec_list_pane_title == "Spec 一覧"
        assert texts.toolbar_rerender == "再描画"
        assert texts.toolbar_copy_source == "ソースをコピー"
        assert texts.toolbar_copy_png == "PNG をコピー"
        assert texts.toolbar_save == "保存"
        assert texts.kaleido_unavailable_tooltip == "PNG 保存は kaleido をインストールすると利用できます。"
        assert (
            texts.rerender_failed_status
            == "Plotly 図を再描画できませんでした: {details}"
        )
        assert texts.tab_title_template == "{title}"

    def test_build_settings_dialog_texts_includes_export_tab_fields(self) -> None:
        service = TranslationService()

        texts = service.build_settings_dialog_texts("en")

        assert texts.export_tab_text == "Export"
        assert texts.visualization_tab_text == "Visualization"
        assert texts.export_folder_label == "Export Folder:"
        assert texts.export_browse_button_text == "Browse..."
        assert texts.export_include_explanation_text == "Include explanation"
        assert (
            texts.export_include_yaml_frontmatter_text
            == "Include YAML frontmatter"
        )
        assert (
            texts.plotly_multi_spec_prompt_text
            == "When multiple Plotly specs are found, ask which one to open"
        )
        assert texts.plotly_timeout_label == "Plotly sandbox timeout:"
        assert texts.plotly_timeout_suffix_seconds == "sec"

    def test_build_markdown_export_texts_returns_localized_labels(self) -> None:
        service = TranslationService()

        texts = service.build_markdown_export_texts("ja")

        assert texts.success_message_template == "Markdown を {file_path} に保存しました"
        assert texts.folder_unset_message == "エクスポートフォルダが設定されていません"
        assert texts.ai_response_section_title == "AI 応答"
        assert texts.document_title_label == "文書タイトル"
        assert texts.action_custom_prompt_label == "カスタムプロンプト"