"""メイン画面の操作を仲介する Presenter。

MainPresenter の役割は、メインウィンドウで発生したユーザー操作を受け取り、
必要に応じて DocumentModel を呼び出し、その結果を View や SidePanel に渡すこと。

重要なのは、このクラス自身は PySide6 の Widget や描画 API を知らない点である。
あくまで「いつ」「どの Model を呼び」「どの View メソッドを呼ぶか」を決める。
"""

from __future__ import annotations

import asyncio

from pdf_epub_reader.dto import RectCoords
from pdf_epub_reader.interfaces.model_interfaces import IDocumentModel
from pdf_epub_reader.interfaces.view_interfaces import IMainView
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter

DEFAULT_DPI = 144


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

    # --- Public API ---

    async def open_file(self, file_path: str) -> None:
        """文書を開き、必要な初期表示をまとめて行う。

        このメソッドは「ファイルを開く」という 1 つのユーザー操作に対して、
        状態表示、文書オープン、タイトル更新、ページ描画までを一貫して扱う。
        こうしておくと View 側は複数の手順を知らず、単純な受け身でいられる。
        """
        self._view.show_status_message(f"Opening {file_path}...")
        doc_info = await self._document_model.open_document(file_path)
        self._view.set_window_title(doc_info.title or doc_info.file_path)

        # 初回表示では全ページをまとめて取得する。
        # Phase 3 以降で仮想スクロールを導入する場合、この呼び出しは差し替わる。
        pages = await self._document_model.render_page_range(
            0, doc_info.total_pages - 1, self._current_dpi
        )
        self._view.display_pages(pages)
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
        """ズーム率変更に追従してページを再描画する。

        ズーム率そのものは View に通知するが、実際に何 dpi で再レンダリングするかは
        Presenter が判断する。これにより View は「倍率が変わった」という事実だけを知り、
        画像生成の詳細から切り離される。
        """
        self._zoom_level = level
        self._view.set_zoom_level(level)

        # 文書がまだ開かれていない状態では再レンダリングできないため、
        # 何もせず戻る。例外にしないのは UI 操作の自然さを優先するため。
        doc_info = self._document_model.get_document_info()
        if doc_info is None:
            return

        # 基準 DPI にズーム倍率を掛けて「今回必要な見た目の解像度」を計算する。
        # こうしておくと、Model は毎回明示的な DPI を受け取るだけで済む。
        effective_dpi = int(DEFAULT_DPI * level)
        self._current_dpi = effective_dpi
        pages = await self._document_model.render_page_range(
            0, doc_info.total_pages - 1, effective_dpi
        )
        self._view.display_pages(pages)

    def _on_cache_management_requested(self) -> None:
        """キャッシュ管理 UI を開くための拡張ポイント。

        詳細なダイアログや操作は Phase 5 で実装する。
        ここでは「イベントの受け口」を先に置き、将来の接続位置を固定している。
        """
        pass
