"""キャッシュ管理ダイアログの操作を仲介する Presenter。

CachePresenter は ICacheDialogView に現在のキャッシュ情報と
一覧データを設定し、ダイアログをモーダル表示して
ユーザーアクションと入力値を MainPresenter に返却する。
"""

from __future__ import annotations

from pdf_epub_reader.dto import CacheStatus
from pdf_epub_reader.interfaces.view_interfaces import ICacheDialogView
from pdf_epub_reader.utils.config import AppConfig


class CachePresenter:
    """ICacheDialogView を仲介し、ユーザー操作結果を返す。"""

    def __init__(
        self,
        view: ICacheDialogView,
        cache_status: CacheStatus,
        cache_list: list[CacheStatus],
        config: AppConfig,
    ) -> None:
        self._view = view
        self._cache_status = cache_status
        self._cache_list = cache_list
        self._config = config

    def show(self) -> tuple[str | None, int, str | None]:
        """ダイアログを表示し (action, new_ttl_minutes, selected_cache_name) を返す。"""
        # タブ1: 現在のキャッシュ情報を View に設定
        self._view.set_cache_name(self._cache_status.cache_name or "---")
        self._view.set_cache_model(self._cache_status.model_name or "---")
        self._view.set_cache_token_count(self._cache_status.token_count)
        self._view.set_cache_ttl_seconds(self._cache_status.ttl_seconds)
        self._view.set_cache_expire_time(self._cache_status.expire_time)
        self._view.set_cache_is_active(self._cache_status.is_active)
        self._view.set_ttl_spin_value(self._config.cache_ttl_minutes)

        # タブ2: キャッシュ一覧
        self._view.set_cache_list(self._cache_list)

        # Phase 7.5: active + expire_time ならカウントダウン開始
        if self._cache_status.is_active and self._cache_status.expire_time:
            self._view.start_countdown(self._cache_status.expire_time)

        # ダイアログ表示 → アクション文字列を受け取る
        action = self._view.show()
        new_ttl = self._view.get_new_ttl_minutes()
        selected_name = self._view.get_selected_cache_name()
        return action, new_ttl, selected_name
