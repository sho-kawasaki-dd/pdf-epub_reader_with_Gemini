"""MainPresenter の振る舞いを検証するテスト群。

ここで確認したいのは「正しい UI を描けるか」ではなく、
MainPresenter が View と Model の間を正しい順序で仲介できているかである。
"""

from __future__ import annotations

import pytest

from tests.mocks.mock_models import MockDocumentModel
from tests.mocks.mock_views import MockMainView, MockSidePanelView

from pdf_epub_reader.dto import RectCoords
from pdf_epub_reader.interfaces.model_interfaces import IDocumentModel
from pdf_epub_reader.interfaces.view_interfaces import IMainView, ISidePanelView
from pdf_epub_reader.presenters.main_presenter import MainPresenter
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter


class TestProtocolConformance:
    """Mock が Protocol 契約を満たしていることを確認する。

    Phase 1 では継承ベースではなく Protocol ベースの設計を採っているため、
    テストで使う Mock が構造的に適合していること自体が重要な保証になる。
    """

    def test_mock_main_view_satisfies_protocol(
        self, mock_main_view: MockMainView
    ) -> None:
        assert isinstance(mock_main_view, IMainView)

    def test_mock_side_panel_view_satisfies_protocol(
        self, mock_side_panel_view: MockSidePanelView
    ) -> None:
        assert isinstance(mock_side_panel_view, ISidePanelView)

    def test_mock_document_model_satisfies_protocol(
        self, mock_document_model: MockDocumentModel
    ) -> None:
        assert isinstance(mock_document_model, IDocumentModel)


class TestOpenFileFlow:
    """ファイルオープン時の一連の流れを検証する。"""

    @pytest.mark.asyncio
    async def test_open_file_displays_pages(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
        mock_document_model: MockDocumentModel,
    ) -> None:
        """文書を開くとプレースホルダー配置とタイトル更新が行われることを確認する。"""
        await main_presenter.open_file("/fake/doc.pdf")

        # Model 側に open が委譲されていること。
        assert len(mock_document_model.get_calls("open_document")) == 1
        assert mock_document_model.get_calls("open_document")[0] == (
            "/fake/doc.pdf",
            None,
        )
        # ページサイズは DocumentInfo.page_sizes から取得するため、
        # render_page はプレースホルダー配置時には呼ばれない。
        assert len(mock_document_model.get_calls("render_page_range")) == 0

        # 次に、その結果が View に反映されていることを確認する。
        titles = mock_main_view.get_calls("set_window_title")
        assert len(titles) == 1
        assert titles[0] == ("Mock Document",)

        pages_calls = mock_main_view.get_calls("display_pages")
        assert len(pages_calls) == 1
        pages = pages_calls[0][0]
        assert len(pages) == 3  # Mock は 3 ページ文書を返す想定。

        # プレースホルダーの image_data は空 bytes であること。
        for page in pages:
            assert page.image_data == b""

    @pytest.mark.asyncio
    async def test_open_file_shows_status_messages(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
    ) -> None:
        """処理開始前後でユーザー向けステータスメッセージが出ることを確認する。"""
        await main_presenter.open_file("/fake/doc.pdf")

        status_msgs = mock_main_view.get_calls("show_status_message")
        # 開始時と完了時の 2 段階でメッセージが出ることが重要。
        assert len(status_msgs) == 2
        assert "Opening" in status_msgs[0][0]
        assert "3 pages" in status_msgs[1][0]


class TestAreaSelectionFlow:
    """矩形選択からテキスト抽出・パネル反映までの流れを検証する。"""

    @pytest.mark.asyncio
    async def test_area_selection_extracts_text(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
        mock_document_model: MockDocumentModel,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """選択領域が正しく Model と SidePanel に伝播することを確認する。"""
        rect = RectCoords(x0=10.0, y0=20.0, x1=200.0, y1=50.0)

        # 非同期の本処理本体を直接呼び、イベント後の流れだけを検証する。
        await main_presenter._do_area_selected(1, rect)

        # 選択範囲がそのまま Model に渡されていること。
        extract_calls = mock_document_model.get_calls("extract_text")
        assert len(extract_calls) == 1
        assert extract_calls[0] == (1, rect)

        # ユーザーへの即時フィードバックとしてハイライトも出ること。
        highlight_calls = mock_main_view.get_calls("show_selection_highlight")
        assert len(highlight_calls) == 1
        assert highlight_calls[0] == (1, rect)

        # 抽出結果が PanelPresenter 経由でサイドパネルまで届くこと。
        text_calls = mock_side_panel_view.get_calls("set_selected_text")
        assert len(text_calls) == 1
        assert "page 1" in text_calls[0][0]


class TestZoomFlow:
    """ズーム変更時の再描画フローを検証する。"""

    @pytest.mark.asyncio
    async def test_zoom_change_rerenders(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
        mock_document_model: MockDocumentModel,
    ) -> None:
        """文書表示中にズームするとプレースホルダーが再配置されることを確認する。"""

        # 先に文書を開いておかないと get_document_info が空のままなので、
        # ズーム時の再描画条件を満たせない。
        await main_presenter.open_file("/fake/doc.pdf")
        mock_main_view.calls.clear()
        mock_document_model.calls.clear()

        await main_presenter._do_zoom_changed(2.0)

        # まず View の倍率表示が更新されること。
        zoom_calls = mock_main_view.get_calls("set_zoom_level")
        assert len(zoom_calls) == 1
        assert zoom_calls[0] == (2.0,)

        # ページサイズは DocumentInfo.page_sizes から DPI 換算するため、
        # render_page はプレースホルダー配置時には呼ばれない。
        assert len(mock_document_model.get_calls("render_page")) == 0
        assert len(mock_document_model.get_calls("render_page_range")) == 0

        # display_pages にプレースホルダー（空 image_data）が渡されること。
        display_calls = mock_main_view.get_calls("display_pages")
        assert len(display_calls) == 1
        for page in display_calls[0][0]:
            assert page.image_data == b""

    @pytest.mark.asyncio
    async def test_zoom_without_document_is_noop(
        self,
        main_presenter: MainPresenter,
        mock_document_model: MockDocumentModel,
    ) -> None:
        """文書未読込状態のズーム変更は安全に無視されることを確認する。"""

        # 例外ではなく no-op で終わることが UI 上の使い勝手として重要。
        await main_presenter._do_zoom_changed(1.5)
        assert len(mock_document_model.get_calls("render_page")) == 0
        assert len(mock_document_model.get_calls("render_page_range")) == 0


class TestLazyLoadingFlow:
    """ビューポート基準の遅延読み込みを検証する。"""

    @pytest.mark.asyncio
    async def test_pages_needed_triggers_render_and_update(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
        mock_document_model: MockDocumentModel,
    ) -> None:
        """View からの要求でページがレンダリングされ update_pages で返ること。"""
        await main_presenter.open_file("/fake/doc.pdf")
        mock_main_view.calls.clear()
        mock_document_model.calls.clear()

        await main_presenter._do_render_pages([0, 1])

        render_calls = mock_document_model.get_calls("render_page")
        assert len(render_calls) == 2
        assert render_calls[0] == (0, 144)     # DEFAULT_DPI
        assert render_calls[1] == (1, 144)


class TestPasswordFlow:
    """パスワード保護 PDF のオープンフローを検証する。"""

    @pytest.mark.asyncio
    async def test_password_success(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
        mock_document_model: MockDocumentModel,
    ) -> None:
        """パスワード入力成功 → 文書が正常にオープンされる。"""
        mock_document_model._should_require_password = True
        mock_main_view._password_dialog_return = "test123"

        await main_presenter.open_file("/fake/protected.pdf")

        # パスワードダイアログが表示されたこと。
        dialog_calls = mock_main_view.get_calls("show_password_dialog")
        assert len(dialog_calls) == 1
        assert dialog_calls[0] == ("/fake/protected.pdf",)

        # 再試行で正しいパスワードが渡されたこと。
        open_calls = mock_document_model.get_calls("open_document")
        assert len(open_calls) == 2
        assert open_calls[0] == ("/fake/protected.pdf", None)
        assert open_calls[1] == ("/fake/protected.pdf", "test123")

        # 文書が正常に表示されたこと。
        assert len(mock_main_view.get_calls("display_pages")) == 1

    @pytest.mark.asyncio
    async def test_password_cancelled(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
        mock_document_model: MockDocumentModel,
    ) -> None:
        """パスワードダイアログをキャンセル → オープン中止。"""
        mock_document_model._should_require_password = True
        mock_main_view._password_dialog_return = None

        await main_presenter.open_file("/fake/protected.pdf")

        # ダイアログは表示されたがキャンセルされた。
        assert len(mock_main_view.get_calls("show_password_dialog")) == 1

        # 再試行はされず、display_pages も呼ばれない。
        open_calls = mock_document_model.get_calls("open_document")
        assert len(open_calls) == 1  # 初回のみ
        assert len(mock_main_view.get_calls("display_pages")) == 0

        # キャンセルメッセージがステータスバーに出る。
        status_msgs = mock_main_view.get_calls("show_status_message")
        assert any("cancelled" in msg[0].lower() for msg in status_msgs)

    @pytest.mark.asyncio
    async def test_wrong_password_shows_error(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
        mock_document_model: MockDocumentModel,
    ) -> None:
        """間違ったパスワード → エラーダイアログが表示される。"""
        mock_document_model._should_require_password = True
        mock_document_model._accepted_password = "correct"
        mock_main_view._password_dialog_return = "wrong"

        await main_presenter.open_file("/fake/protected.pdf")

        # エラーダイアログが表示されたこと。
        error_calls = mock_main_view.get_calls("show_error_dialog")
        assert len(error_calls) == 1
        assert "Open Error" in error_calls[0][0]

        # 文書は表示されない。
        assert len(mock_main_view.get_calls("display_pages")) == 0


class TestDocumentOpenError:
    """DocumentOpenError 発生時のエラーハンドリングを検証する。"""

    @pytest.mark.asyncio
    async def test_open_error_shows_dialog(
        self,
        main_presenter: MainPresenter,
        mock_main_view: MockMainView,
        mock_document_model: MockDocumentModel,
    ) -> None:
        """ファイルオープン失敗 → エラーダイアログが表示される。"""
        from pdf_epub_reader.utils.exceptions import DocumentOpenError

        # open_document が DocumentOpenError を送出するよう差し替える。
        async def _raise_open_error(
            file_path: str, password: str | None = None
        ):
            raise DocumentOpenError(f"Cannot open {file_path}")

        mock_document_model.open_document = _raise_open_error  # type: ignore[assignment]

        await main_presenter.open_file("/fake/broken.pdf")

        error_calls = mock_main_view.get_calls("show_error_dialog")
        assert len(error_calls) == 1
        assert "Open Error" in error_calls[0][0]
        assert len(mock_main_view.get_calls("display_pages")) == 0
