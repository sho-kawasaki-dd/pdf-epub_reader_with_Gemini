"""設定ダイアログの操作を仲介する Presenter。

SettingsPresenter は ISettingsDialogView と AppConfig の間を仲介し、
ダイアログの表示・値の読み書き・リセット・永続化を担当する。

MainPresenter から呼び出され、ダイアログが OK で閉じられた場合に
更新後の AppConfig を返す。Cancel の場合は None を返す。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from pdf_epub_reader.interfaces.model_interfaces import IAIModel
from pdf_epub_reader.interfaces.view_interfaces import ISettingsDialogView
from pdf_epub_reader.services.translation_service import TranslationService
from pdf_epub_reader.utils.config import AppConfig, save_config
from pdf_epub_reader.utils.exceptions import AIError

logger = logging.getLogger(__name__)


class SettingsPresenter:
    """ISettingsDialogView と AppConfig の調停役。

    ダイアログの表示ライフサイクルを管理し、
    ユーザーが OK を押した場合のみ設定を永続化する。
    """

    def __init__(
        self,
        view: ISettingsDialogView,
        config: AppConfig,
        ai_model: IAIModel | None = None,
    ) -> None:
        """依存オブジェクトを受け取り、コールバックを登録する。

        Args:
            view: 設定ダイアログの View（Protocol 準拠）。
            config: 現在のアプリケーション設定。
            ai_model: AI モデル。None の場合は Fetch Models 不可。
        """
        self._view = view
        self._config = config
        self._ai_model = ai_model
        self._translation_service = TranslationService()
        self._view.set_on_reset_defaults(self._on_reset_defaults)
        self._view.set_on_fetch_models_requested(self._on_fetch_models)

    def show(self) -> AppConfig | None:
        """設定ダイアログを表示し、OK なら更新済み AppConfig を返す。

        1. 現在の AppConfig 値で View を populate する
        2. モーダルダイアログを実行する（exec_dialog）
        3. OK → View から値を読み取り → AppConfig 生成 → JSON 永続化 → 返却
        4. Cancel → None を返す

        Returns:
            OK の場合は更新後の AppConfig。Cancel の場合は None。
        """
        self._view.apply_ui_texts(
            self._translation_service.build_settings_dialog_texts(
                self._config.ui_language
            )
        )
        self._populate_view(self._config)

        if not self._view.exec_dialog():
            return None

        new_config = self._read_config_from_view()
        save_config(new_config)
        return new_config

    def _populate_view(self, config: AppConfig) -> None:
        """AppConfig の値をダイアログの各ウィジェットに反映する。"""
        self._view.set_render_format(config.render_format)
        self._view.set_jpeg_quality(config.jpeg_quality)
        self._view.set_default_dpi(config.default_dpi)
        self._view.set_page_cache_max_size(config.page_cache_max_size)
        self._view.set_auto_detect_embedded_images(
            config.auto_detect_embedded_images
        )
        self._view.set_auto_detect_math_fonts(config.auto_detect_math_fonts)
        self._view.set_high_quality_downscale(config.high_quality_downscale)
        # Phase 6: AI 設定
        self._view.set_gemini_model_name(config.gemini_model_name)
        self._view.set_selected_models(config.selected_models)
        self._view.set_output_language(config.output_language)
        self._view.set_system_prompt_translation(
            config.system_prompt_translation
        )
        self._view.set_cache_ttl_minutes(config.cache_ttl_minutes)
        self._view.set_export_folder(config.export_folder)
        self._view.set_export_include_explanation(
            config.export_include_explanation
        )
        self._view.set_export_include_selection_list(
            config.export_include_selection_list
        )
        self._view.set_export_include_raw_response(
            config.export_include_raw_response
        )
        self._view.set_export_include_document_metadata(
            config.export_include_document_metadata
        )
        self._view.set_export_include_usage_metrics(
            config.export_include_usage_metrics
        )
        self._view.set_export_include_yaml_frontmatter(
            config.export_include_yaml_frontmatter
        )

    def _read_config_from_view(self) -> AppConfig:
        """ダイアログの現在値から AppConfig を生成する。

        ダイアログに含まれないフィールド（window_width, window_height,
        recent_files）は現在の config からコピーして保持する。
        """
        return AppConfig(
            render_format=self._view.get_render_format(),
            jpeg_quality=self._view.get_jpeg_quality(),
            default_dpi=self._view.get_default_dpi(),
            page_cache_max_size=self._view.get_page_cache_max_size(),
            auto_detect_embedded_images=self._view.get_auto_detect_embedded_images(),
            auto_detect_math_fonts=self._view.get_auto_detect_math_fonts(),
            high_quality_downscale=self._view.get_high_quality_downscale(),
            # Phase 6: AI 設定
            gemini_model_name=self._view.get_gemini_model_name(),
            selected_models=self._view.get_selected_models(),
            output_language=self._view.get_output_language(),
            system_prompt_translation=self._view.get_system_prompt_translation(),
            cache_ttl_minutes=self._view.get_cache_ttl_minutes(),
            export_folder=self._view.get_export_folder(),
            export_include_explanation=self._view.get_export_include_explanation(),
            export_include_selection_list=self._view.get_export_include_selection_list(),
            export_include_raw_response=self._view.get_export_include_raw_response(),
            export_include_document_metadata=self._view.get_export_include_document_metadata(),
            export_include_usage_metrics=self._view.get_export_include_usage_metrics(),
            export_include_yaml_frontmatter=self._view.get_export_include_yaml_frontmatter(),
            ui_language=self._config.ui_language,
            # ダイアログ対象外のフィールドは既存値を引き継ぐ
            window_width=self._config.window_width,
            window_height=self._config.window_height,
            recent_files=list(self._config.recent_files),
        )

    def _on_reset_defaults(self) -> None:
        """「Reset to Defaults」ボタン押下時にデフォルト値で再 populate する。"""
        self._populate_view(replace(AppConfig(), ui_language=self._config.ui_language))

    def _on_fetch_models(self) -> None:
        """「Fetch Models」ボタン押下時にモデル一覧を非同期取得する。

        ダイアログはモーダルなため asyncio.ensure_future で
        バックグラウンドタスクとして取得を開始する。
        """
        if self._ai_model is None:
            self._view.show_fetch_models_error(
                self._translate("presenter.settings.ai_model_unavailable")
            )
            return
        asyncio.ensure_future(self._fetch_models_async())

    async def _fetch_models_async(self) -> None:
        """モデル一覧を API から取得し View に反映する。"""
        assert self._ai_model is not None
        self._view.set_fetch_models_loading(True)
        try:
            models = await self._ai_model.list_available_models()
            model_tuples = [
                (m.model_id, m.display_name) for m in models
            ]
            self._view.set_available_models_for_selection(model_tuples)
        except AIError as exc:
            logger.warning("モデル一覧の取得に失敗: %s", exc)
            self._view.show_fetch_models_error(
                self._translate(
                    "presenter.settings.fetch_models_failed",
                    details=str(exc),
                )
            )
        finally:
            self._view.set_fetch_models_loading(False)

    def _translate(self, key: str, **kwargs: object) -> str:
        return self._translation_service.translate(
            key,
            self._config.ui_language,
            **kwargs,
        )
