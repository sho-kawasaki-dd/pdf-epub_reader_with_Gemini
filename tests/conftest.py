"""pytest 全体で共有するフィクスチャ定義。

このファイルでは Phase 1 の Presenter テストで繰り返し必要になる
Mock View / Mock Model / Presenter の組み立てを共通化する。
各テストが「何を検証したいか」に集中できるように、準備コードはここへ寄せる。
"""

from __future__ import annotations

import pytest

from tests.mocks.mock_models import MockAIModel, MockDocumentModel
from tests.mocks.mock_views import MockMainView, MockSidePanelView

from pdf_epub_reader.presenters.main_presenter import MainPresenter
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter


@pytest.fixture
def mock_main_view() -> MockMainView:
    """メイン画面の Mock View を毎テストごとに新しく返す。"""
    return MockMainView()


@pytest.fixture
def mock_side_panel_view() -> MockSidePanelView:
    """サイドパネルの Mock View を毎テストごとに新しく返す。"""
    return MockSidePanelView()


@pytest.fixture
def mock_document_model() -> MockDocumentModel:
    """文書処理用の Mock Model を返す。"""
    return MockDocumentModel()


@pytest.fixture
def mock_ai_model() -> MockAIModel:
    """AI 解析用の Mock Model を返す。"""
    return MockAIModel()


@pytest.fixture
def panel_presenter(
    mock_side_panel_view: MockSidePanelView,
    mock_ai_model: MockAIModel,
) -> PanelPresenter:
    """依存を注入済みの PanelPresenter を返す。

    サイドパネル単体の振る舞いを確認したいテストでは、
    このフィクスチャを使うことで毎回同じ構成を簡単に再利用できる。
    """
    return PanelPresenter(view=mock_side_panel_view, ai_model=mock_ai_model)


@pytest.fixture
def main_presenter(
    mock_main_view: MockMainView,
    mock_document_model: MockDocumentModel,
    panel_presenter: PanelPresenter,
) -> MainPresenter:
    """依存を注入済みの MainPresenter を返す。

    MainPresenter は PanelPresenter に依存するため、
    テストでも本番と同じ依存関係を保った構成にしている。
    """
    return MainPresenter(
        view=mock_main_view,
        document_model=mock_document_model,
        panel_presenter=panel_presenter,
    )
