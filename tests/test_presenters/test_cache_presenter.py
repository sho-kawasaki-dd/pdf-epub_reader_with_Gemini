"""CachePresenter の振る舞いを検証するテスト群。

CachePresenter はキャッシュ管理ダイアログのデータ設定と
ユーザーアクションの取得を仲介する。
"""

from __future__ import annotations

import pytest

from tests.mocks.mock_views import MockCacheDialogView

from pdf_epub_reader.dto import CacheStatus
from pdf_epub_reader.interfaces.view_interfaces import ICacheDialogView
from pdf_epub_reader.presenters.cache_presenter import CachePresenter
from pdf_epub_reader.utils.config import AppConfig


class TestProtocolConformance:
    """Mock が ICacheDialogView Protocol を満たすことを確認する。"""

    def test_mock_cache_dialog_satisfies_protocol(self) -> None:
        mock = MockCacheDialogView()
        assert isinstance(mock, ICacheDialogView)


class TestShowPopulatesView:
    """show() が View に正しくデータを設定することを検証する。"""

    def test_active_cache_populates_all_fields(self) -> None:
        """active なキャッシュ情報が View の各フィールドに反映されること。"""
        mock_view = MockCacheDialogView()
        status = CacheStatus(
            is_active=True,
            cache_name="cache-abc",
            model_name="gemini-2.5-flash",
            token_count=5000,
            ttl_seconds=1800,
            expire_time="2026-04-11T12:00:00Z",
        )
        cache_list = [
            CacheStatus(cache_name="cache-1", model_name="m1"),
            CacheStatus(cache_name="cache-2", model_name="m2"),
        ]
        config = AppConfig(cache_ttl_minutes=90)

        presenter = CachePresenter(mock_view, status, cache_list, config)
        action, ttl, selected = presenter.show()

        # タブ1 の設定確認
        assert mock_view.get_calls("set_cache_name") == [("cache-abc",)]
        assert mock_view.get_calls("set_cache_model") == [
            ("gemini-2.5-flash",)
        ]
        assert mock_view.get_calls("set_cache_token_count") == [(5000,)]
        assert mock_view.get_calls("set_cache_ttl_seconds") == [(1800,)]
        assert mock_view.get_calls("set_cache_expire_time") == [
            ("2026-04-11T12:00:00Z",)
        ]
        assert mock_view.get_calls("set_cache_is_active") == [(True,)]
        assert mock_view.get_calls("set_ttl_spin_value") == [(90,)]

        # タブ2 の設定確認
        list_calls = mock_view.get_calls("set_cache_list")
        assert len(list_calls) == 1
        assert len(list_calls[0][0]) == 2

        # show が呼ばれたこと
        assert len(mock_view.get_calls("show")) == 1

    def test_inactive_cache_uses_defaults(self) -> None:
        """inactive なキャッシュでは "---" がフォールバックされること。"""
        mock_view = MockCacheDialogView()
        status = CacheStatus()
        config = AppConfig()

        presenter = CachePresenter(mock_view, status, [], config)
        presenter.show()

        assert mock_view.get_calls("set_cache_name") == [("---",)]
        assert mock_view.get_calls("set_cache_model") == [("---",)]
        assert mock_view.get_calls("set_cache_is_active") == [(False,)]


class TestShowReturnsAction:
    """show() がダイアログのアクション・TTL・選択名を正しく返すことを検証する。"""

    def test_returns_action_and_ttl(self) -> None:
        """アクション文字列と TTL 値が正しく取得されること。"""
        mock_view = MockCacheDialogView()
        mock_view._show_return = "update_ttl"
        mock_view._ttl_value = 120

        presenter = CachePresenter(
            mock_view, CacheStatus(), [], AppConfig()
        )
        action, ttl, selected = presenter.show()

        assert action == "update_ttl"
        assert ttl == 120
        assert selected is None

    def test_returns_selected_cache_name(self) -> None:
        """テーブルで選択されたキャッシュ名が返されること。"""
        mock_view = MockCacheDialogView()
        mock_view._show_return = "delete_selected"
        mock_view._selected_cache_name = "cache-xyz"

        presenter = CachePresenter(
            mock_view, CacheStatus(), [], AppConfig()
        )
        action, _, selected = presenter.show()

        assert action == "delete_selected"
        assert selected == "cache-xyz"

    def test_close_returns_none(self) -> None:
        """ダイアログを閉じた場合は action=None が返ること。"""
        mock_view = MockCacheDialogView()
        mock_view._show_return = None

        presenter = CachePresenter(
            mock_view, CacheStatus(), [], AppConfig()
        )
        action, _, _ = presenter.show()

        assert action is None


class TestCacheCountdown:
    """Phase 7.5: active キャッシュでカウントダウンが開始されることを検証する。"""

    def test_active_cache_starts_countdown(self) -> None:
        """active + expire_time → start_countdown が呼ばれること。"""
        mock_view = MockCacheDialogView()
        status = CacheStatus(
            is_active=True,
            cache_name="cache-abc",
            expire_time="2026-12-31T23:59:59Z",
        )
        presenter = CachePresenter(
            mock_view, status, [], AppConfig()
        )
        presenter.show()

        cd_calls = mock_view.get_calls("start_countdown")
        assert len(cd_calls) == 1
        assert cd_calls[0] == ("2026-12-31T23:59:59Z",)
