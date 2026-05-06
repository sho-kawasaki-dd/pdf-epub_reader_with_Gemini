"""Presenter から利用する UI 翻訳サービス。"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from pdf_epub_reader.dto import (
    AnalysisStatusTexts,
    BookmarkPanelTexts,
    CacheDialogTexts,
    LanguageDialogTexts,
    MainWindowTexts,
    MarkdownExportTexts,
    PlotlyTexts,
    PlotWindowTexts,
    SettingsDialogTexts,
    SidePanelTexts,
)
from pdf_epub_reader.resources.i18n import TRANSLATIONS
from pdf_epub_reader.utils.config import DEFAULT_UI_LANGUAGE, UiLanguage, normalize_ui_language

logger = logging.getLogger(__name__)


class TranslationService:
    """階層キーで UI 文言を解決するサービス。"""

    def __init__(
        self,
        translations: Mapping[str, Mapping[str, str]] | None = None,
        default_language: UiLanguage = DEFAULT_UI_LANGUAGE,
    ) -> None:
        source = translations or TRANSLATIONS
        self._translations = {
            language_code: dict(entries)
            for language_code, entries in source.items()
        }
        self._default_language = normalize_ui_language(default_language)

    def translate(self, key: str, language: str, **kwargs: object) -> str:
        """指定言語の翻訳を返し、無ければ英語へフォールバックする。"""
        resolved_language = normalize_ui_language(
            language,
            fallback=self._default_language,
        )
        template = self._lookup(key, resolved_language)
        if template is None and resolved_language != self._default_language:
            template = self._lookup(key, self._default_language)
        if template is None:
            return key
        if not kwargs:
            return template

        try:
            return template.format(**kwargs)
        except (IndexError, KeyError, ValueError) as exc:
            logger.warning(
                "翻訳テンプレートの補間に失敗しました: key=%s, language=%s, error=%s",
                key,
                resolved_language,
                exc,
            )
            return template

    def _lookup(self, key: str, language: UiLanguage) -> str | None:
        entries = self._translations.get(language)
        if entries is None:
            return None
        return entries.get(key)

    def build_bookmark_panel_texts(self, language: str) -> BookmarkPanelTexts:
        return BookmarkPanelTexts(
            header_label=self.translate("bookmark.header", language),
        )

    def build_main_window_texts(self, language: str) -> MainWindowTexts:
        return MainWindowTexts(
            window_title=self.translate("main.window.title", language),
            file_menu_title=self.translate("main.menu.file.title", language),
            open_action_text=self.translate("main.menu.file.open", language),
            recent_menu_title=self.translate("main.menu.file.recent", language),
            recent_none_text=self.translate("main.menu.file.none", language),
            quit_action_text=self.translate("main.menu.file.exit", language),
            view_menu_title=self.translate("main.menu.view.title", language),
            bookmark_toggle_text=self.translate("main.menu.view.bookmarks", language),
            edit_menu_title=self.translate("main.menu.edit.title", language),
            preferences_action_text=self.translate("main.menu.edit.preferences", language),
            cache_menu_title=self.translate("main.menu.cache.title", language),
            cache_management_action_text=self.translate("main.menu.cache.manage", language),
            language_menu_title=self.translate("menu.language.title", language),
            language_settings_action_text=self.translate("menu.language.settings", language),
            overlay_page_label=self.translate("main.overlay.page", language),
            default_status_text=self.translate("main.status.ready", language),
            open_dialog_title=self.translate("main.dialog.open.title", language),
            open_dialog_filter=self.translate("main.dialog.open.filter", language),
            password_dialog_title=self.translate("main.dialog.password.title", language),
            password_dialog_message_template=self.translate("main.dialog.password.message", language),
            bookmark_panel=self.build_bookmark_panel_texts(language),
        )

    def build_analysis_status_texts(self, language: str) -> AnalysisStatusTexts:
        """AI request の状態表示文言を 1 つの DTO にまとめて返す。

        この DTO を分けておくことで、MainPresenter は running / cancel /
        timing の文言だけを独立して差し替えられる。Plotly や MainWindow の
        静的テキスト束と責務を混ぜずに済むのが利点である。
        """
        return AnalysisStatusTexts(
            running_message=self.translate("ai.running_message", language),
            cancelled_message=self.translate("ai.cancelled_message", language),
            timing_only=self.translate("ai.timing_only", language),
            timing_with_graph=self.translate("ai.timing_with_graph", language),
            cancel_link_text=self.translate("ai.cancel_link_text", language),
        )

    def build_side_panel_texts(self, language: str) -> SidePanelTexts:
        return SidePanelTexts(
            model_label=self.translate("side.model.label", language),
            model_unset_placeholder=self.translate("side.model.unset_placeholder", language),
            selection_section_title=self.translate("side.section.selections", language),
            selection_summary_template=self.translate("side.selection.summary", language),
            selection_clear_button=self.translate("side.selection.clear", language),
            selection_warning_text=self.translate("side.selection.warning", language),
            selection_empty_text=self.translate("side.selection.empty", language),
            selection_preview_label=self.translate("side.selection.preview_label", language),
            selection_preview_placeholder=self.translate("side.selection.preview_placeholder", language),
            selection_force_image_text=self.translate("side.selection.force_image", language),
            plotly_toggle_tooltip=self.translate("side.plotly_toggle_tooltip.json", language),
            plotly_toggle_tooltip_off=self.translate("side.plotly_toggle_tooltip.off", language),
            plotly_toggle_tooltip_json=self.translate("side.plotly_toggle_tooltip.json", language),
            plotly_toggle_tooltip_python=self.translate("side.plotly_toggle_tooltip.python", language),
            ai_section_title=self.translate("side.section.ai", language),
            translation_button_text=self.translate("side.translation.button", language),
            translation_explain_button_text=self.translate("side.translation.explain_button", language),
            translation_tab_text=self.translate("side.translation.tab", language),
            translation_placeholder_text=self.translate("side.translation.placeholder", language),
            custom_tab_text=self.translate("side.custom.tab", language),
            custom_prompt_placeholder=self.translate("side.custom.prompt_placeholder", language),
            custom_submit_button_text=self.translate("side.custom.submit", language),
            export_button_text=self.translate("side.export.button", language),
            custom_placeholder_text=self.translate("side.custom.placeholder", language),
            cache_status_placeholder=self.translate("side.cache.status_placeholder", language),
            cache_create_button_text=self.translate("side.cache.create", language),
            cache_delete_button_text=self.translate("side.cache.delete", language),
            cache_remaining_template=self.translate("side.cache.remaining", language),
            cache_expired_text=self.translate("side.cache.expired", language),
            selection_card_page_template=self.translate("side.selection.card.page", language),
            selection_card_delete_button=self.translate("side.selection.card.delete", language),
            selection_card_pending_text=self.translate("side.selection.card.pending", language),
            selection_card_error_text=self.translate("side.selection.card.error", language),
            selection_card_ready_text=self.translate("side.selection.card.ready", language),
            selection_card_extracting_text=self.translate("side.selection.card.extracting", language),
            selection_card_extract_failed_text=self.translate("side.selection.card.extract_failed", language),
            selection_card_no_text=self.translate("side.selection.card.no_text", language),
        )

    def build_plotly_texts(self, language: str) -> PlotlyTexts:
        return PlotlyTexts(
            multi_select_dialog_title=self.translate(
                "plotly.dialog.multi_select.title", language
            ),
            multi_select_dialog_label=self.translate(
                "plotly.dialog.multi_select.label", language
            ),
            multi_select_cancel_button_text=self.translate(
                "plotly.dialog.multi_select.cancel", language
            ),
            spec_fallback_title_template=self.translate(
                "plotly.spec.fallback_title", language
            ),
            render_success_message_template=self.translate(
                "plotly.status.render_success", language
            ),
            extraction_failed_message=self.translate(
                "plotly.status.extraction_failed", language
            ),
            restore_failed_message_template=self.translate(
                "plotly.status.restore_failed", language
            ),
            invalid_json_message_template=self.translate(
                "plotly.status.invalid_json", language
            ),
            window_title_template=self.translate(
                "plotly.window.title", language
            ),
            sandbox_running_message=self.translate(
                "plotly.status.sandbox_running", language
            ),
            sandbox_timeout_message=self.translate(
                "plotly.status.sandbox_timeout", language
            ),
            sandbox_runtime_error_message=self.translate(
                "plotly.status.sandbox_runtime_error", language
            ),
            sandbox_static_check_error_message=self.translate(
                "plotly.status.sandbox_static_check_error", language
            ),
            sandbox_cancelled_message=self.translate(
                "plotly.status.sandbox_cancelled", language
            ),
            sandbox_provisioning_message=self.translate(
                "plotly.status.sandbox_provisioning", language
            ),
            sandbox_provisioning_failed_message=self.translate(
                "plotly.status.sandbox_provisioning_failed", language
            ),
            sandbox_provisioning_failed_offline_message=self.translate(
                "plotly.status.sandbox_provisioning_failed_offline", language
            ),
            sandbox_fallback_to_json_message=self.translate(
                "plotly.status.sandbox_fallback_to_json", language
            ),
            sandbox_cancel_link_text=self.translate(
                "plotly.sandbox.cancel_link", language
            ),
        )

    def build_plot_window_texts(self, language: str) -> PlotWindowTexts:
        return PlotWindowTexts(
            spec_list_pane_title=self.translate(
                "plotly.window.spec_list_pane_title", language
            ),
            toolbar_rerender=self.translate(
                "plotly.window.toolbar.rerender", language
            ),
            toolbar_copy_source=self.translate(
                "plotly.window.toolbar.copy_source", language
            ),
            toolbar_copy_png=self.translate(
                "plotly.window.toolbar.copy_png", language
            ),
            toolbar_save=self.translate(
                "plotly.window.toolbar.save", language
            ),
            kaleido_unavailable_tooltip=self.translate(
                "plotly.window.kaleido_unavailable_tooltip", language
            ),
            rerender_failed_status=self.translate(
                "plotly.window.status.rerender_failed", language
            ),
            copy_png_failed_status=self.translate(
                "plotly.window.status.copy_png_failed", language
            ),
            tab_title_template=self.translate(
                "plotly.window.tab.title", language
            ),
        )

    def build_settings_dialog_texts(self, language: str) -> SettingsDialogTexts:
        return SettingsDialogTexts(
            window_title=self.translate("settings.dialog.title", language),
            rendering_tab_text=self.translate("settings.tab.rendering", language),
            detection_tab_text=self.translate("settings.tab.detection", language),
            ai_tab_text=self.translate("settings.tab.ai", language),
            export_tab_text=self.translate("settings.tab.export", language),
            visualization_tab_text=self.translate("settings.tab.visualization", language),
            image_format_label=self.translate("settings.render.image_format", language),
            jpeg_quality_label=self.translate("settings.render.jpeg_quality", language),
            default_dpi_label=self.translate("settings.render.default_dpi", language),
            page_cache_size_label=self.translate("settings.render.page_cache_size", language),
            high_quality_downscale_text=self.translate("settings.render.high_quality_downscale", language),
            auto_detect_images_text=self.translate("settings.detection.auto_images", language),
            auto_detect_math_text=self.translate("settings.detection.auto_math", language),
            default_model_label=self.translate("settings.ai.default_model", language),
            available_models_label=self.translate("settings.ai.available_models", language),
            fetch_models_button_text=self.translate("settings.ai.fetch_models", language),
            fetch_models_loading_text=self.translate("settings.ai.fetch_loading", language),
            output_language_label=self.translate("settings.ai.output_language", language),
            translation_prompt_label=self.translate("settings.ai.translation_prompt", language),
            cache_ttl_label=self.translate("settings.ai.cache_ttl", language),
            export_folder_label=self.translate("settings.export.folder", language),
            export_browse_button_text=self.translate("settings.export.browse", language),
            export_include_explanation_text=self.translate(
                "settings.export.include_explanation", language
            ),
            export_include_selection_list_text=self.translate(
                "settings.export.include_selection_list", language
            ),
            export_include_raw_response_text=self.translate(
                "settings.export.include_raw_response", language
            ),
            export_include_document_metadata_text=self.translate(
                "settings.export.include_document_metadata", language
            ),
            export_include_usage_metrics_text=self.translate(
                "settings.export.include_usage_metrics", language
            ),
            export_include_yaml_frontmatter_text=self.translate(
                "settings.export.include_yaml_frontmatter", language
            ),
            plotly_multi_spec_prompt_text=self.translate(
                "settings.visualization.plotly_multi_spec_prompt", language
            ),
            plotly_multi_spec_first_only_text=self.translate(
                "settings.visualization.plotly_multi_spec_first_only", language
            ),
            plotly_multi_spec_all_tabs_text=self.translate(
                "settings.visualization.plotly_multi_spec_all_tabs", language
            ),
            plotly_timeout_label=self.translate(
                "settings.visualization.plotly_timeout", language
            ),
            plotly_timeout_suffix_seconds=self.translate(
                "settings.visualization.plotly_timeout_seconds", language
            ),
            minutes_suffix=self.translate("common.minutes_suffix", language),
            reset_defaults_button_text=self.translate("settings.button.reset_defaults", language),
            ok_button_text=self.translate("common.ok", language),
            cancel_button_text=self.translate("common.cancel", language),
        )

    def build_markdown_export_texts(self, language: str) -> MarkdownExportTexts:
        return MarkdownExportTexts(
            success_message_template=self.translate(
                "export.status.success", language
            ),
            failure_message_template=self.translate(
                "export.status.failure", language
            ),
            folder_unset_message=self.translate(
                "export.status.folder_unset", language
            ),
            exported_at_label=self.translate("export.field.exported_at", language),
            action_label=self.translate("export.field.action", language),
            model_label=self.translate("export.field.model", language),
            source_document_label=self.translate(
                "export.field.source_document", language
            ),
            source_file_label=self.translate("export.field.source_file", language),
            selections_section_title=self.translate(
                "export.section.selections", language
            ),
            ai_response_section_title=self.translate(
                "export.section.ai_response", language
            ),
            explanation_section_title=self.translate(
                "export.section.explanation", language
            ),
            raw_response_section_title=self.translate(
                "export.section.raw_response", language
            ),
            document_metadata_section_title=self.translate(
                "export.section.document_metadata", language
            ),
            usage_metrics_section_title=self.translate(
                "export.section.usage_metrics", language
            ),
            document_title_label=self.translate(
                "export.metadata.document_title", language
            ),
            file_name_label=self.translate("export.metadata.file_name", language),
            selection_count_label=self.translate(
                "export.metadata.selection_count", language
            ),
            prompt_tokens_label=self.translate(
                "export.metrics.prompt_tokens", language
            ),
            cached_tokens_label=self.translate(
                "export.metrics.cached_tokens", language
            ),
            candidates_tokens_label=self.translate(
                "export.metrics.candidates_tokens", language
            ),
            total_tokens_label=self.translate(
                "export.metrics.total_tokens", language
            ),
            action_translation_label=self.translate(
                "export.action.translation", language
            ),
            action_custom_prompt_label=self.translate(
                "export.action.custom_prompt", language
            ),
        )

    def build_cache_dialog_texts(self, language: str) -> CacheDialogTexts:
        return CacheDialogTexts(
            window_title=self.translate("cache.dialog.title", language),
            tab_current_text=self.translate("cache.tab.current", language),
            tab_list_text=self.translate("cache.tab.list", language),
            field_name_label=self.translate("cache.field.name", language),
            field_model_label=self.translate("cache.field.model", language),
            field_tokens_label=self.translate("cache.field.tokens", language),
            field_remaining_ttl_label=self.translate("cache.field.remaining_ttl", language),
            field_expire_time_label=self.translate("cache.field.expire_time", language),
            field_status_label=self.translate("cache.field.status", language),
            field_new_ttl_label=self.translate("cache.field.new_ttl", language),
            button_update_ttl_text=self.translate("cache.button.update_ttl", language),
            button_create_text=self.translate("cache.button.create", language),
            button_delete_text=self.translate("cache.button.delete", language),
            button_delete_selected_text=self.translate("cache.button.delete_selected", language),
            button_close_text=self.translate("common.close", language),
            table_name_header=self.translate("cache.table.name", language),
            table_model_header=self.translate("cache.table.model", language),
            table_display_name_header=self.translate("cache.table.display_name", language),
            table_tokens_header=self.translate("cache.table.tokens", language),
            table_expire_header=self.translate("cache.table.expire", language),
            status_active_text=self.translate("cache.status.active", language),
            status_inactive_text=self.translate("cache.status.inactive", language),
            status_expired_text=self.translate("cache.status.expired", language),
            ttl_minutes_seconds_template=self.translate("cache.ttl.minutes_seconds", language),
            minutes_suffix=self.translate("common.minutes_suffix", language),
            not_set_text=self.translate("common.not_set", language),
        )

    def build_language_dialog_texts(self, language: str) -> LanguageDialogTexts:
        return LanguageDialogTexts(
            window_title=self.translate("dialog.language.title", language),
            description_text=self.translate("dialog.language.description", language),
            label_text=self.translate("dialog.language.label", language),
            ok_button_text=self.translate("common.ok", language),
            cancel_button_text=self.translate("common.cancel", language),
        )