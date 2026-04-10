"""設定ダイアログの操作を仲介する Presenter。

SettingsPresenter は ISettingsDialogView と AppConfig の間を仲介し、
ダイアログの表示・値の読み書き・リセット・永続化を担当する。

MainPresenter から呼び出され、ダイアログが OK で閉じられた場合に
更新後の AppConfig を返す。Cancel の場合は None を返す。
"""

from __future__ import annotations

from pdf_epub_reader.interfaces.view_interfaces import ISettingsDialogView
from pdf_epub_reader.utils.config import AppConfig, save_config


class SettingsPresenter:
    """ISettingsDialogView と AppConfig の調停役。

    ダイアログの表示ライフサイクルを管理し、
    ユーザーが OK を押した場合のみ設定を永続化する。
    """

    def __init__(
        self, view: ISettingsDialogView, config: AppConfig
    ) -> None:
        """依存オブジェクトを受け取り、リセットコールバックを登録する。

        Args:
            view: 設定ダイアログの View（Protocol 準拠）。
            config: 現在のアプリケーション設定。
        """
        self._view = view
        self._config = config
        self._view.set_on_reset_defaults(self._on_reset_defaults)

    def show(self) -> AppConfig | None:
        """設定ダイアログを表示し、OK なら更新済み AppConfig を返す。

        1. 現在の AppConfig 値で View を populate する
        2. モーダルダイアログを実行する（exec_dialog）
        3. OK → View から値を読み取り → AppConfig 生成 → JSON 永続化 → 返却
        4. Cancel → None を返す

        Returns:
            OK の場合は更新後の AppConfig。Cancel の場合は None。
        """
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
            # ダイアログ対象外のフィールドは既存値を引き継ぐ
            window_width=self._config.window_width,
            window_height=self._config.window_height,
            recent_files=list(self._config.recent_files),
        )

    def _on_reset_defaults(self) -> None:
        """「Reset to Defaults」ボタン押下時にデフォルト値で再 populate する。"""
        self._populate_view(AppConfig())
