"""PanelPresenter の振る舞いを検証するテスト群。

ここでは AI API の結果そのものではなく、PanelPresenter が
適切な AnalysisRequest を組み立て、ローディング表示や結果反映を
正しく制御できるかを確認する。
"""

from __future__ import annotations

import pytest

from tests.mocks.mock_models import MockAIModel
from tests.mocks.mock_views import MockSidePanelView

from pdf_epub_reader.dto import AnalysisMode
from pdf_epub_reader.interfaces.model_interfaces import IAIModel
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter


class TestProtocolConformance:
    """Mock が AI Model Protocol を満たすことを確認する。"""

    def test_mock_ai_model_satisfies_protocol(
        self, mock_ai_model: MockAIModel
    ) -> None:
        assert isinstance(mock_ai_model, IAIModel)


class TestTranslationFlow:
    """翻訳モードの処理フローを検証する。"""

    @pytest.mark.asyncio
    async def test_translate_calls_analyze_and_updates_view(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """翻訳要求で正しい Request が作られ、結果が View に反映されることを確認する。"""
        panel_presenter.set_selected_text("Hello world")
        await panel_presenter._do_translate(include_explanation=False)

        # Presenter が mode を正しく選び、選択テキストを渡していること。
        analyze_calls = mock_ai_model.get_calls("analyze")
        assert len(analyze_calls) == 1
        request = analyze_calls[0][0]
        assert request.text == "Hello world"
        assert request.mode == AnalysisMode.TRANSLATION
        assert request.include_explanation is False

        # AI の戻り値が View に表示されること。
        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "Hello world" in result_calls[0][0]

    @pytest.mark.asyncio
    async def test_translate_with_explanation(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """解説付き翻訳では explanation が表示文字列に含まれることを確認する。"""
        panel_presenter.set_selected_text("Test text")
        await panel_presenter._do_translate(include_explanation=True)

        analyze_calls = mock_ai_model.get_calls("analyze")
        assert analyze_calls[0][0].include_explanation is True

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        result_text = result_calls[0][0]
        assert "Mock explanation" in result_text

    @pytest.mark.asyncio
    async def test_translate_without_selected_text_is_noop(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        """選択テキストが無い場合は AI を呼ばずに終了することを確認する。"""
        await panel_presenter._do_translate(include_explanation=False)
        assert len(mock_ai_model.get_calls("analyze")) == 0


class TestCustomPromptFlow:
    """カスタムプロンプトモードの処理フローを検証する。"""

    @pytest.mark.asyncio
    async def test_custom_prompt_calls_analyze(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """カスタムプロンプトが Request に正しく入り、解析が実行されることを確認する。"""
        panel_presenter.set_selected_text("Some text")
        await panel_presenter._do_custom_prompt("Summarize this")

        analyze_calls = mock_ai_model.get_calls("analyze")
        assert len(analyze_calls) == 1
        request = analyze_calls[0][0]
        assert request.text == "Some text"
        assert request.mode == AnalysisMode.CUSTOM_PROMPT
        assert request.custom_prompt == "Summarize this"

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1


class TestLoadingState:
    """ローディング表示の開始・終了が必ず行われることを検証する。"""

    @pytest.mark.asyncio
    async def test_loading_shown_during_translation(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """翻訳処理の前後でローディング状態が切り替わることを確認する。"""
        panel_presenter.set_selected_text("Test")
        await panel_presenter._do_translate(include_explanation=False)

        loading_calls = mock_side_panel_view.get_calls("show_loading")
        assert len(loading_calls) == 2
        assert loading_calls[0] == (True,)   # 処理開始時
        assert loading_calls[1] == (False,)  # 処理終了時

    @pytest.mark.asyncio
    async def test_loading_shown_during_custom_prompt(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """カスタムプロンプト処理でも同様にローディングが切り替わることを確認する。"""
        panel_presenter.set_selected_text("Test")
        await panel_presenter._do_custom_prompt("Do something")

        loading_calls = mock_side_panel_view.get_calls("show_loading")
        assert len(loading_calls) == 2
        assert loading_calls[0] == (True,)
        assert loading_calls[1] == (False,)


class TestSetSelectedText:
    """選択テキストの保持と View 反映を検証する。"""

    def test_set_selected_text_updates_view(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """MainPresenter から渡された選択テキストが View に表示されることを確認する。"""
        panel_presenter.set_selected_text("Selected!")

        text_calls = mock_side_panel_view.get_calls("set_selected_text")
        assert len(text_calls) == 1
        assert text_calls[0] == ("Selected!",)
