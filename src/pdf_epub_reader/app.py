"""MVP コンポーネントのワイヤリングとアプリケーション起動。

Model, View, Presenter を組み立て、qasync 統合ループで起動する。
各コンポーネントの依存関係はここで解決し、循環参照を防ぐ。
"""

from __future__ import annotations

import dotenv

from pdf_epub_reader.infrastructure.event_loop import run_app
from pdf_epub_reader.models.ai_model import AIModel
from pdf_epub_reader.models.document_model import DocumentModel
from pdf_epub_reader.presenters.main_presenter import MainPresenter
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter
from pdf_epub_reader.utils.config import load_config
from pdf_epub_reader.views.main_window import MainWindow
from pdf_epub_reader.views.side_panel_view import SidePanelView


def main() -> None:
    """Model, View, Presenter を組み立ててアプリケーションを起動する。"""
    dotenv.load_dotenv()
    run_app(_app_main)


async def _app_main() -> None:
    """非同期コンテキスト内で MVP コンポーネントを生成・結合する。"""
    # --- Config ---
    config = load_config()

    # --- Models ---
    document_model = DocumentModel(config=config)
    ai_model = AIModel()

    # --- Views ---
    side_panel_view = SidePanelView()
    main_window = MainWindow(side_panel=side_panel_view)

    # --- Presenters ---
    panel_presenter = PanelPresenter(view=side_panel_view, ai_model=ai_model)
    _main_presenter = MainPresenter(  # noqa: F841
        view=main_window,
        document_model=document_model,
        panel_presenter=panel_presenter,
        config=config,
    )

    main_window.show()
