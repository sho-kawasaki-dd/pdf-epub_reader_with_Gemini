"""メイン画面の操作を仲介する Presenter。

MainPresenter の役割は、メインウィンドウで発生したユーザー操作を受け取り、
必要に応じて DocumentModel を呼び出し、その結果を View や SidePanel に渡すこと。

重要なのは、このクラス自身は PySide6 の Widget や描画 API を知らない点である。
あくまで「いつ」「どの Model を呼び」「どの View メソッドを呼ぶか」を決める。
"""

from __future__ import annotations

import asyncio

from pdf_epub_reader.dto import PageData, RectCoords
from pdf_epub_reader.interfaces.model_interfaces import IDocumentModel
from pdf_epub_reader.interfaces.view_interfaces import IMainView
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter
from pdf_epub_reader.utils.config import DEFAULT_DPI
from pdf_epub_reader.utils.exceptions import (
    DocumentOpenError,
    DocumentPasswordRequired,
)


class MainPresenter:
    """IMainView と IDocumentModel の調停役。

    MainPresenter はアプリ全体の司令塔ではあるが、AI 解析の詳細までは持たない。
    選択されたテキストを PanelPresenter に引き渡すことで責務を分離している。
    """

    def __init__(
        self,
        view: IMainView,
        document_model: IDocumentModel,
        panel_presenter: PanelPresenter,
    ) -> None:
        """依存オブジェクトを受け取り、View のイベントを購読する。

        なぜ `__init__` でコールバック登録するのか:
        - Presenter の生成完了時点で View と接続された状態を保証したい
        - 接続漏れによる「ボタンを押しても何も起きない」を防ぎたい
        - テスト時に生成直後からイベントをシミュレートできるようにしたい
        """
        self._view = view
        self._document_model = document_model
        self._panel_presenter = panel_presenter
        self._current_dpi: int = DEFAULT_DPI
        self._zoom_level: float = 1.0

        # View は Presenter を知らないため、ここでイベントの受け口を登録する。
        self._view.set_on_file_open_requested(self._on_file_open_requested)
        self._view.set_on_file_dropped(self._on_file_dropped)
        self._view.set_on_recent_file_selected(self._on_recent_file_selected)
        self._view.set_on_area_selected(self._on_area_selected)
        self._view.set_on_zoom_changed(self._on_zoom_changed)
        self._view.set_on_cache_management_requested(
            self._on_cache_management_requested
        )
        self._view.set_on_pages_needed(self._on_pages_needed)

    # --- Public API ---

    async def open_file(self, file_path: str) -> None:
        """文書を開き、必要な初期表示をまとめて行う。

        全ページ分のプレースホルダーを配置し、実画像の読み込みは
        View のビューポート監視による遅延読み込みに委ねる。

        パスワード保護 PDF の場合は View にダイアログを表示させ、
        ユーザーが入力したパスワードで再試行する。
        """
        self._view.show_status_message(f"Opening {file_path}...")
        try:
            doc_info = await self._document_model.open_document(file_path)
        except DocumentPasswordRequired as e:
            # パスワード保護を検出 → View にダイアログを表示させる。
            password = self._view.show_password_dialog(e.file_path)
            if password is None:
                # ユーザーがキャンセルした場合はオープンを中止する。
                self._view.show_status_message("Open cancelled")
                return
            try:
                doc_info = await self._document_model.open_document(
                    file_path, password
                )
            except DocumentOpenError as retry_e:
                self._view.show_error_dialog(
                    "Open Error", str(retry_e)
                )
                self._view.show_status_message("Open failed")
                return
        except DocumentOpenError as e:
            self._view.show_error_dialog("Open Error", str(e))
            self._view.show_status_message("Open failed")
            return

        self._view.set_window_title(doc_info.title or doc_info.file_path)

        # 各ページの PDF ポイントサイズを DPI 換算してプレースホルダーを配置する。
        # 実際の画像は View がビューポートに基づいて後から要求する。
        scale = self._current_dpi / 72.0
        placeholders = [
            PageData(
                page_number=i,
                image_data=b"",
                width=int(pw * scale),
                height=int(ph * scale),
            )
            for i, (pw, ph) in enumerate(doc_info.page_sizes)
        ]
        self._view.display_pages(placeholders)
        self._view.show_status_message(
            f"Loaded {doc_info.total_pages} pages"
        )

    # --- Private callback handlers ---

    def _on_file_open_requested(self) -> None:
        """ファイル選択 UI の起点となるフック。

        Phase 1 では GUI を実装していないため処理本体は持たない。
        ただしイベントの流れを Presenter に確保しておくことで、
        Phase 2 で View 実装を差し込んだときの接続先が明確になる。
        """
        pass

    def _on_file_dropped(self, file_path: str) -> None:
        """ドラッグ&ドロップで渡されたパスから非同期オープンを開始する。"""

        # View のイベントハンドラは同期関数として呼ばれる想定なので、
        # ここではタスクを発行して GUI スレッドを止めないようにする。
        asyncio.ensure_future(self.open_file(file_path))

    def _on_recent_file_selected(self, file_path: str) -> None:
        """最近開いたファイルの選択から非同期オープンを開始する。"""
        asyncio.ensure_future(self.open_file(file_path))

    def _on_area_selected(self, page_number: int, rect: RectCoords) -> None:
        """矩形選択イベントを受け取り、抽出処理を非同期で開始する。"""
        asyncio.ensure_future(self._do_area_selected(page_number, rect))

    async def _do_area_selected(
        self, page_number: int, rect: RectCoords
    ) -> None:
        """選択範囲を強調表示し、その範囲のテキストを抽出してパネルへ渡す。

        まずハイライトを先に出すのは、抽出完了前でもユーザーに
        「選択が受理された」ことを即時に伝えるため。
        """
        self._view.show_selection_highlight(page_number, rect)
        selection = await self._document_model.extract_text(page_number, rect)
        self._panel_presenter.set_selected_text(selection.extracted_text)

    def _on_zoom_changed(self, level: float) -> None:
        """ズーム変更イベントを受け取り、再描画処理を非同期で開始する。"""
        asyncio.ensure_future(self._do_zoom_changed(level))

    async def _do_zoom_changed(self, level: float) -> None:
        """ズーム率変更に追従してプレースホルダーを再配置する。

        ズーム率そのものは View に通知するが、実際に何 dpi で再レンダリングするかは
        Presenter が判断する。再配置後は View のビューポート監視が遅延読み込みを行う。
        """
        self._zoom_level = level
        self._view.set_zoom_level(level)

        # 文書がまだ開かれていない状態では再レンダリングできないため、
        # 何もせず戻る。例外にしないのは UI 操作の自然さを優先するため。
        doc_info = self._document_model.get_document_info()
        if doc_info is None:
            return

        # 基準 DPI にズーム倍率を掛けて「今回必要な見た目の解像度」を計算する。
        effective_dpi = int(DEFAULT_DPI * level)
        self._current_dpi = effective_dpi

        # ズーム変更後も各ページの実サイズでプレースホルダーを再配置し、View に遅延読み込みを任せる。
        scale = effective_dpi / 72.0
        placeholders = [
            PageData(
                page_number=i,
                image_data=b"",
                width=int(pw * scale),
                height=int(ph * scale),
            )
            for i, (pw, ph) in enumerate(doc_info.page_sizes)
        ]
        self._view.display_pages(placeholders)

    def _on_cache_management_requested(self) -> None:
        """キャッシュ管理 UI を開くための拡張ポイント。

        詳細なダイアログや操作は Phase 5 で実装する。
        ここでは「イベントの受け口」を先に置き、将来の接続位置を固定している。
        """
        pass

    def _on_pages_needed(self, page_numbers: list[int]) -> None:
        """View からページ画像の要求を受け取り、非同期レンダリングを開始する。"""
        asyncio.ensure_future(self._do_render_pages(page_numbers))

    async def _do_render_pages(self, page_numbers: list[int]) -> None:
        """要求されたページをレンダリングし、View に供給する。

        View のビューポート監視により呼ばれる。各ページを個別に
        render_page() で取得し、まとめて update_pages() で返す。
        """
        pages: list[PageData] = []
        for num in page_numbers:
            page = await self._document_model.render_page(
                num, self._current_dpi
            )
            pages.append(page)
        self._view.update_pages(pages)
