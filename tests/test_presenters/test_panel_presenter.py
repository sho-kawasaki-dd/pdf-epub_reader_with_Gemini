"""PanelPresenter の振る舞いを検証するテスト群。

ここでは AI API の結果そのものではなく、PanelPresenter が
適切な AnalysisRequest を組み立て、ローディング表示や結果反映を
正しく制御できるかを確認する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.mocks.mock_models import MockAIModel
from tests.mocks.mock_views import MockSidePanelView

from pdf_epub_reader.dto import AnalysisMode, AnalysisResult, CacheStatus
from pdf_epub_reader.dto.document_dto import RectCoords, SelectionContent
from pdf_epub_reader.interfaces.model_interfaces import IAIModel
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter
from pdf_epub_reader.utils.exceptions import (
    AIAPIError,
    AIKeyMissingError,
    AIRateLimitError,
)


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


class TestSetSelectedContent:
    """Phase 4: マルチモーダルコンテンツの保持と View 反映を検証する。"""

    def test_set_selected_content_updates_preview(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """SelectionContent が View のプレビューに反映されることを確認する。"""
        rect = RectCoords(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        content = SelectionContent(
            page_number=0,
            rect=rect,
            extracted_text="Hello math",
            cropped_image=b"img-data",
            detection_reason="math_font",
        )
        panel_presenter.set_selected_content(content)

        preview_calls = mock_side_panel_view.get_calls(
            "set_selected_content_preview"
        )
        assert len(preview_calls) == 1
        assert preview_calls[0] == ("Hello math", b"img-data")

    def test_set_selected_content_updates_internal_text(
        self,
        panel_presenter: PanelPresenter,
    ) -> None:
        """set_selected_content で内部の _selected_text も更新されることを確認する。"""
        rect = RectCoords(x0=0.0, y0=0.0, x1=50.0, y1=50.0)
        content = SelectionContent(
            page_number=0,
            rect=rect,
            extracted_text="Updated text",
        )
        panel_presenter.set_selected_content(content)
        assert panel_presenter._selected_text == "Updated text"


class TestForceImageToggle:
    """Phase 4: 「画像としても送信」トグルの状態管理を検証する。"""

    def test_initial_force_include_image_is_false(
        self,
        panel_presenter: PanelPresenter,
    ) -> None:
        """初期状態では force_include_image が False であることを確認する。"""
        assert panel_presenter.force_include_image is False

    def test_toggle_updates_state(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """チェックボックスの切り替えが内部状態に反映されることを確認する。"""
        mock_side_panel_view.simulate_force_image_toggled(True)
        assert panel_presenter.force_include_image is True

        mock_side_panel_view.simulate_force_image_toggled(False)
        assert panel_presenter.force_include_image is False


class TestMultimodalAnalysis:
    """Phase 4: AI 解析時の画像添付を検証する。"""

    @pytest.mark.asyncio
    async def test_translate_includes_images_when_cropped(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        """クロップ画像がある場合、AnalysisRequest.images に含まれることを確認する。"""
        rect = RectCoords(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        content = SelectionContent(
            page_number=0,
            rect=rect,
            extracted_text="Math formula",
            cropped_image=b"cropped-png",
        )
        panel_presenter.set_selected_content(content)
        await panel_presenter._do_translate(include_explanation=False)

        analyze_calls = mock_ai_model.get_calls("analyze")
        assert len(analyze_calls) == 1
        request = analyze_calls[0][0]
        assert request.images == [b"cropped-png"]

    @pytest.mark.asyncio
    async def test_translate_no_images_when_text_only(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        """クロップ画像が無い場合、AnalysisRequest.images が空であることを確認する。"""
        rect = RectCoords(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        content = SelectionContent(
            page_number=0,
            rect=rect,
            extracted_text="Plain text",
        )
        panel_presenter.set_selected_content(content)
        await panel_presenter._do_translate(include_explanation=False)

        analyze_calls = mock_ai_model.get_calls("analyze")
        request = analyze_calls[0][0]
        assert request.images == []

    @pytest.mark.asyncio
    async def test_custom_prompt_includes_images(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        """カスタムプロンプトでもクロップ画像が AnalysisRequest に渡ることを確認する。"""
        rect = RectCoords(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        content = SelectionContent(
            page_number=0,
            rect=rect,
            extracted_text="Some content",
            cropped_image=b"image-bytes",
        )
        panel_presenter.set_selected_content(content)
        await panel_presenter._do_custom_prompt("Explain this")

        analyze_calls = mock_ai_model.get_calls("analyze")
        request = analyze_calls[0][0]
        assert request.images == [b"image-bytes"]
        assert request.mode == AnalysisMode.CUSTOM_PROMPT


class TestErrorHandling:
    """Phase 6: AI エラー発生時の View 表示を検証する。"""

    @pytest.mark.asyncio
    async def test_key_missing_shows_error_in_view(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """AIKeyMissingError 発生時にエラーメッセージが表示されること。"""
        mock_ai_model.analyze = AsyncMock(side_effect=AIKeyMissingError())
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selected_text("Hello")
        await presenter._do_translate(include_explanation=False)

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "API キー" in result_calls[0][0]

    @pytest.mark.asyncio
    async def test_rate_limit_shows_error_in_view(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """AIRateLimitError 発生時にレート制限メッセージが表示されること。"""
        mock_ai_model.analyze = AsyncMock(side_effect=AIRateLimitError())
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selected_text("Hello")
        await presenter._do_translate(include_explanation=False)

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "レート制限" in result_calls[0][0]

    @pytest.mark.asyncio
    async def test_api_error_shows_details_in_view(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """AIAPIError 発生時にエラー詳細が表示されること。"""
        mock_ai_model.analyze = AsyncMock(
            side_effect=AIAPIError("Something went wrong", status_code=500)
        )
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selected_text("Hello")
        await presenter._do_translate(include_explanation=False)

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "Something went wrong" in result_calls[0][0]

    @pytest.mark.asyncio
    async def test_custom_prompt_key_missing_shows_error(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """カスタムプロンプトでも AIKeyMissingError がハンドルされること。"""
        mock_ai_model.analyze = AsyncMock(side_effect=AIKeyMissingError())
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selected_text("Hello")
        await presenter._do_custom_prompt("Summarize")

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "API キー" in result_calls[0][0]

    @pytest.mark.asyncio
    async def test_loading_cleared_on_error(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """エラー発生時でもローディングが解除されること。"""
        mock_ai_model.analyze = AsyncMock(side_effect=AIRateLimitError())
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selected_text("Hello")
        await presenter._do_translate(include_explanation=False)

        loading_calls = mock_side_panel_view.get_calls("show_loading")
        assert loading_calls[-1] == (False,)


class TestModelSelection:
    """Phase 6: モデル選択の状態管理と AnalysisRequest 伝播を検証する。"""

    def test_set_available_models_propagates_to_view(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """set_available_models が View に伝播すること。"""
        panel_presenter.set_available_models(["model-a", "model-b"])
        calls = mock_side_panel_view.get_calls("set_available_models")
        assert len(calls) == 1
        assert calls[0] == (["model-a", "model-b"],)

    def test_set_selected_model_propagates_to_view(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """set_selected_model が View に伝播すること。"""
        panel_presenter.set_selected_model("model-x")
        calls = mock_side_panel_view.get_calls("set_selected_model")
        # fixture が初期モデルを設定するため 2 回呼ばれる
        assert calls[-1] == ("model-x",)

    def test_model_changed_updates_internal_state(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """View のモデル変更が内部状態に反映されること。"""
        mock_side_panel_view.simulate_model_changed("new-model")
        assert panel_presenter._current_model == "new-model"

    @pytest.mark.asyncio
    async def test_selected_model_passed_in_request(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """選択されたモデルが AnalysisRequest.model_name に入ること。"""
        mock_side_panel_view.simulate_model_changed("gemini-2.0-pro")
        panel_presenter.set_selected_text("Test text")
        await panel_presenter._do_translate(include_explanation=False)

        analyze_calls = mock_ai_model.get_calls("analyze")
        assert len(analyze_calls) == 1
        assert analyze_calls[0][0].model_name == "gemini-2.0-pro"

    @pytest.mark.asyncio
    async def test_no_model_selected_shows_warning(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """モデル未選択時はガードが作動し、AI 呼び出しが行われないこと。"""
        presenter = PanelPresenter(view=mock_side_panel_view, ai_model=mock_ai_model)
        presenter.set_selected_text("Test text")
        await presenter._do_translate(include_explanation=False)

        analyze_calls = mock_ai_model.get_calls("analyze")
        assert len(analyze_calls) == 0
        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "モデルが未設定" in result_calls[0][0]


class TestCacheHandlers:
    """Phase 7: キャッシュ作成/削除ハンドラの呼出確認を検証する。"""

    def test_cache_create_handler_called(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """キャッシュ作成ボタンで登録ハンドラが呼ばれること。"""
        called = []
        panel_presenter.set_on_cache_create_handler(lambda: called.append("create"))
        mock_side_panel_view.simulate_cache_create_requested()
        assert called == ["create"]

    def test_cache_invalidate_handler_called(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """キャッシュ削除ボタンで登録ハンドラが呼ばれること。"""
        called = []
        panel_presenter.set_on_cache_invalidate_handler(
            lambda: called.append("invalidate")
        )
        # キャッシュ active 状態にして削除ボタンを押す
        panel_presenter.update_cache_status(
            CacheStatus(is_active=True, cache_name="c1", model_name="m1")
        )
        mock_side_panel_view.simulate_cache_invalidate_requested()
        assert called == ["invalidate"]

    def test_update_cache_status_active(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """update_cache_status(active) で View が ON 表示に更新されること。"""
        status = CacheStatus(
            is_active=True, token_count=5000, cache_name="c1"
        )
        panel_presenter.update_cache_status(status)

        active_calls = mock_side_panel_view.get_calls("set_cache_active")
        assert active_calls[-1] == (True,)

        brief_calls = mock_side_panel_view.get_calls(
            "update_cache_status_brief"
        )
        assert "ON" in brief_calls[-1][0]
        assert "5000" in brief_calls[-1][0]

    def test_update_cache_status_inactive(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """update_cache_status(inactive) で View が OFF 表示に更新されること。"""
        panel_presenter.update_cache_status(CacheStatus())

        active_calls = mock_side_panel_view.get_calls("set_cache_active")
        assert active_calls[-1] == (False,)

        brief_calls = mock_side_panel_view.get_calls(
            "update_cache_status_brief"
        )
        assert "OFF" in brief_calls[-1][0]


class TestModelChangeWithCache:
    """Phase 7: キャッシュ active 時のモデル変更確認ダイアログを検証する。"""

    def test_model_change_with_active_cache_confirm_ok(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """キャッシュ active + モデル変更 → OK で invalidate ハンドラ発火。"""
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.update_cache_status(
            CacheStatus(
                is_active=True, cache_name="c1", model_name="model-a"
            )
        )
        invalidated = []
        presenter.set_on_cache_invalidate_handler(
            lambda: invalidated.append(True)
        )
        mock_side_panel_view._confirm_dialog_return = True
        mock_side_panel_view.simulate_model_changed("model-b")

        assert invalidated == [True]
        assert presenter._current_model == "model-b"

    def test_model_change_with_active_cache_confirm_cancel(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """キャッシュ active + モデル変更 → Cancel でモデルがリバートされること。"""
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.update_cache_status(
            CacheStatus(
                is_active=True, cache_name="c1", model_name="model-a"
            )
        )
        mock_side_panel_view._confirm_dialog_return = False
        mock_side_panel_view.simulate_model_changed("model-b")

        # モデルは元に戻される
        revert_calls = mock_side_panel_view.get_calls("set_selected_model")
        assert revert_calls[-1] == ("model-a",)
        # 内部状態は変更されていない
        assert presenter._current_model is None

    def test_model_change_same_model_no_dialog(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """同一モデルへの変更ではダイアログが出ないこと。"""
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.update_cache_status(
            CacheStatus(
                is_active=True, cache_name="c1", model_name="model-a"
            )
        )
        mock_side_panel_view.calls.clear()
        mock_side_panel_view.simulate_model_changed("model-a")

        dialog_calls = mock_side_panel_view.get_calls("show_confirm_dialog")
        assert len(dialog_calls) == 0
        assert presenter._current_model == "model-a"

    def test_model_change_without_cache_no_dialog(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """キャッシュ inactive 時はダイアログなしでモデル切替されること。"""
        mock_side_panel_view.simulate_model_changed("any-model")

        dialog_calls = mock_side_panel_view.get_calls("show_confirm_dialog")
        assert len(dialog_calls) == 0
        assert panel_presenter._current_model == "any-model"


class TestGetCurrentModel:
    """Phase 7 Bugfix: get_current_model() の動作を検証する。"""

    def test_initial_model_is_none(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """初期状態では get_current_model が None を返すこと。"""
        presenter = PanelPresenter(view=mock_side_panel_view, ai_model=mock_ai_model)
        assert presenter.get_current_model() is None

    def test_set_selected_model_updates_getter(
        self,
        panel_presenter: PanelPresenter,
    ) -> None:
        """set_selected_model 後に get_current_model が正しい値を返すこと。"""
        panel_presenter.set_selected_model("gemini-2.0-pro")
        assert panel_presenter.get_current_model() == "gemini-2.0-pro"

    def test_model_changed_via_view_updates_getter(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """View からのモデル変更が get_current_model に反映されること。"""
        mock_side_panel_view.simulate_model_changed("new-model")
        assert panel_presenter.get_current_model() == "new-model"


class TestModelUnsetGuard:
    """Phase 7 Bugfix: モデル未設定時のガードを検証する。"""

    @pytest.mark.asyncio
    async def test_translate_with_no_model_shows_warning(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """モデル未設定時の翻訳要求でエラーメッセージが表示されること。"""
        presenter = PanelPresenter(view=mock_side_panel_view, ai_model=mock_ai_model)
        presenter.set_selected_text("Hello")
        await presenter._do_translate(include_explanation=False)

        # AI は呼ばれない
        assert len(mock_ai_model.get_calls("analyze")) == 0
        # 警告メッセージが表示される
        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "モデルが未設定" in result_calls[0][0]

    @pytest.mark.asyncio
    async def test_custom_prompt_with_no_model_shows_warning(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """モデル未設定時のカスタムプロンプトでエラーメッセージが表示されること。"""
        presenter = PanelPresenter(view=mock_side_panel_view, ai_model=mock_ai_model)
        presenter.set_selected_text("Hello")
        await presenter._do_custom_prompt("Summarize")

        assert len(mock_ai_model.get_calls("analyze")) == 0
        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "モデルが未設定" in result_calls[0][0]

    def test_cache_create_with_no_model_shows_warning(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """モデル未設定時のキャッシュ作成でエラーメッセージが表示されること。"""
        presenter = PanelPresenter(view=mock_side_panel_view, ai_model=mock_ai_model)
        called = []
        presenter.set_on_cache_create_handler(lambda: called.append(True))
        mock_side_panel_view.simulate_cache_create_requested()

        # ハンドラは呼ばれない
        assert called == []
        # 警告メッセージが表示される
        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "モデルが未設定" in result_calls[0][0]

    @pytest.mark.asyncio
    async def test_translate_with_model_set_proceeds(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """モデルが設定されている場合は通常通り翻訳が実行されること。"""
        panel_presenter.set_selected_model("gemini-pro")
        panel_presenter.set_selected_text("Hello")
        await panel_presenter._do_translate(include_explanation=False)

        assert len(mock_ai_model.get_calls("analyze")) == 1


class TestCacheCountdown:
    """Phase 7.5: カウントダウン連携を検証する。"""

    def test_update_cache_status_starts_countdown(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """active + expire_time → start_cache_countdown が呼ばれること。"""
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        status = CacheStatus(
            is_active=True,
            token_count=5000,
            cache_name="c1",
            expire_time="2026-12-31T23:59:59Z",
        )
        presenter.update_cache_status(status)

        cd_calls = mock_side_panel_view.get_calls("start_cache_countdown")
        assert len(cd_calls) == 1
        assert cd_calls[0] == ("2026-12-31T23:59:59Z",)

    def test_update_cache_status_stops_countdown_when_inactive(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """inactive → stop_cache_countdown が呼ばれること。"""
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.update_cache_status(CacheStatus())

        stop_calls = mock_side_panel_view.get_calls("stop_cache_countdown")
        assert len(stop_calls) == 1

    def test_cache_expired_fires_handler(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """simulate_cache_expired → 登録ハンドラが発火すること。"""
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        fired = []
        presenter.set_on_cache_expired_handler(lambda: fired.append(True))
        mock_side_panel_view.simulate_cache_expired()

        assert fired == [True]
