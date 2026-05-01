"""PanelPresenter の振る舞いを検証するテスト群。

ここでは AI API の結果そのものではなく、PanelPresenter が
適切な AnalysisRequest を組み立て、ローディング表示や結果反映を
正しく制御できるかを確認する。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.mocks.mock_models import MockAIModel
from tests.mocks.mock_views import MockSidePanelView

from pdf_epub_reader.dto import (
    AnalysisMode,
    AnalysisResult,
    CacheStatus,
    PlotlyRenderRequest,
)
from pdf_epub_reader.dto.document_dto import (
    RectCoords,
    SelectionContent,
    SelectionSlot,
    SelectionSnapshot,
)
from pdf_epub_reader.interfaces.model_interfaces import IAIModel
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter
from pdf_epub_reader.utils.exceptions import (
    AIAPIError,
    AIKeyMissingError,
    AIRateLimitError,
)


def _make_slot(
    number: int,
    page_number: int,
    text: str,
    *,
    selection_id: str | None = None,
    read_state: str = "ready",
    cropped_image: bytes | None = None,
) -> SelectionSlot:
    content = None
    if read_state == "ready":
        content = SelectionContent(
            page_number=page_number,
            rect=RectCoords(0.0, 0.0, 100.0, 100.0),
            extracted_text=text,
            cropped_image=cropped_image,
        )

    return SelectionSlot(
        selection_id=selection_id or f"selection-{number}",
        display_number=number,
        page_number=page_number,
        rect=RectCoords(0.0, 0.0, 100.0, 100.0),
        read_state=read_state,
        extracted_text=text,
        has_thumbnail=cropped_image is not None,
        content=content,
    )


def _make_snapshot(*slots: SelectionSlot) -> SelectionSnapshot:
    return SelectionSnapshot(slots=slots)


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
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello world"))
        )
        await panel_presenter._do_translate(include_explanation=False)

        # Presenter が mode を正しく選び、選択テキストを渡していること。
        analyze_calls = mock_ai_model.get_calls("analyze")
        assert len(analyze_calls) == 1
        request = analyze_calls[0][0]
        assert request.text == "選択 1 / ページ 1\n\nHello world"
        assert request.mode == AnalysisMode.TRANSLATION
        assert request.include_explanation is False

        # AI の戻り値が View に表示されること。
        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "Hello world" in result_calls[0][0]
        assert panel_presenter.export_state is not None
        assert panel_presenter.export_state.action_mode == AnalysisMode.TRANSLATION
        assert panel_presenter.export_state.include_explanation is False
        assert mock_side_panel_view.get_calls("set_export_enabled")[-1] == (True,)

    @pytest.mark.asyncio
    async def test_translate_with_explanation(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """解説付き翻訳では explanation が表示文字列に含まれることを確認する。"""
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Test text"))
        )
        await panel_presenter._do_translate(include_explanation=True)

        analyze_calls = mock_ai_model.get_calls("analyze")
        assert analyze_calls[0][0].include_explanation is True

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        result_text = result_calls[0][0]
        assert "Mock explanation" in result_text
        assert panel_presenter.export_state is not None
        assert panel_presenter.export_state.include_explanation is True

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
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Some text"))
        )
        await panel_presenter._do_custom_prompt("Summarize this")

        analyze_calls = mock_ai_model.get_calls("analyze")
        assert len(analyze_calls) == 1
        request = analyze_calls[0][0]
        assert request.text == "選択 1 / ページ 1\n\nSome text"
        assert request.mode == AnalysisMode.CUSTOM_PROMPT
        assert request.custom_prompt == "Summarize this"

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert panel_presenter.export_state is not None
        assert panel_presenter.export_state.action_mode == AnalysisMode.CUSTOM_PROMPT


class TestLoadingState:
    """ローディング表示の開始・終了が必ず行われることを検証する。"""

    @pytest.mark.asyncio
    async def test_loading_shown_during_translation(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """翻訳処理の前後でローディング状態が切り替わることを確認する。"""
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Test"))
        )
        await panel_presenter._do_translate(include_explanation=False)

        loading_calls = mock_side_panel_view.get_calls("show_loading")
        running_calls = mock_side_panel_view.get_calls("show_ai_request_running")
        clear_running_calls = mock_side_panel_view.get_calls("clear_ai_request_running")
        assert len(loading_calls) == 2
        assert loading_calls[0] == (True,)   # 処理開始時
        assert loading_calls[1] == (False,)  # 処理終了時
        assert running_calls == [(
            "Gemini request を実行中...",
            "キャンセル",
        )]
        assert clear_running_calls == [()]

    @pytest.mark.asyncio
    async def test_loading_shown_during_custom_prompt(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """カスタムプロンプト処理でも同様にローディングが切り替わることを確認する。"""
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Test"))
        )
        await panel_presenter._do_custom_prompt("Do something")

        loading_calls = mock_side_panel_view.get_calls("show_loading")
        running_calls = mock_side_panel_view.get_calls("show_ai_request_running")
        clear_running_calls = mock_side_panel_view.get_calls("clear_ai_request_running")
        assert len(loading_calls) == 2
        assert loading_calls[0] == (True,)
        assert loading_calls[1] == (False,)
        assert running_calls == [(
            "Gemini request を実行中...",
            "キャンセル",
        )]
        assert clear_running_calls == [()]


class TestRequestLifecycle:
    """Phase 1: active request tracking と cancel を検証する。"""

    @pytest.mark.asyncio
    async def test_translate_request_can_be_cancelled_via_active_task(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        panel_presenter.set_available_models(["models/gemini-2.0-flash"])
        panel_presenter.set_selected_model("models/gemini-2.0-flash")
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Test"))
        )

        started = asyncio.Event()

        async def _analyze(request):
            started.set()
            await asyncio.Event().wait()

        mock_ai_model.analyze = AsyncMock(side_effect=_analyze)

        panel_presenter._on_translate_requested(include_explanation=False)
        await started.wait()

        active_task = panel_presenter._active_analysis_task
        assert active_task is not None
        assert not active_task.done()

        panel_presenter.cancel_active_request()

        with pytest.raises(asyncio.CancelledError):
            await active_task

        assert panel_presenter._active_analysis_task is None
        assert mock_side_panel_view.get_calls("show_loading") == [(True,), (False,)]
        assert mock_side_panel_view.get_calls("show_ai_request_running") == [(
            "Gemini request を実行中...",
            "キャンセル",
        )]
        assert mock_side_panel_view.get_calls("clear_ai_request_running") == [()]
        assert mock_side_panel_view.get_calls("update_result_text") == []


class TestSelectionSnapshot:
    """複数選択スナップショットの保持と View 反映を検証する。"""

    def test_set_selection_snapshot_updates_view(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """snapshot が一覧表示と連結プレビューの両方に反映されることを確認する。"""
        snapshot = _make_snapshot(_make_slot(1, 1, "Selected!"))
        panel_presenter.set_selection_snapshot(snapshot)

        snapshot_calls = mock_side_panel_view.get_calls("set_selection_snapshot")
        assert len(snapshot_calls) == 1
        assert snapshot_calls[0][0].slots[0].extracted_text == "Selected!"

        combined_calls = mock_side_panel_view.get_calls(
            "set_combined_selection_preview"
        )
        assert len(combined_calls) == 1
        assert combined_calls[0][0] == "選択 1 / ページ 2\n\nSelected!"
        assert mock_side_panel_view.get_calls("set_export_enabled")[-1] == (False,)

    def test_set_selection_snapshot_renumbers_after_deletion(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """表示番号に欠番がある snapshot を受けても 1,2,... に詰め直すこと。"""
        snapshot = _make_snapshot(
            _make_slot(1, 0, "First", selection_id="a"),
            _make_slot(3, 2, "Third", selection_id="c"),
        )
        panel_presenter.set_selection_snapshot(snapshot)

        normalized = mock_side_panel_view.get_calls("set_selection_snapshot")[0][0]
        assert [slot.display_number for slot in normalized.slots] == [1, 2]

        combined = mock_side_panel_view.get_calls(
            "set_combined_selection_preview"
        )[0][0]
        assert combined == (
            "選択 1 / ページ 1\n\nFirst\n\n"
            "選択 2 / ページ 3\n\nThird"
        )

    def test_apply_ui_language_updates_preview_language(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        snapshot = _make_snapshot(_make_slot(1, 1, "Selected!"))
        panel_presenter.set_selection_snapshot(snapshot)

        mock_side_panel_view.calls.clear()
        panel_presenter.apply_ui_language("en")

        texts = mock_side_panel_view.get_calls("apply_ui_texts")[-1][0]
        assert texts.translation_tab_text == "Translation"
        assert mock_side_panel_view.get_calls("set_combined_selection_preview")[-1][0] == (
            "Selection 1 / Page 2\n\nSelected!"
        )


class TestSetSelectedContent:
    """Phase 4: マルチモーダルコンテンツの保持と View 反映を検証する。"""

    def test_set_selected_content_updates_snapshot_preview(
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

        snapshot_calls = mock_side_panel_view.get_calls("set_selection_snapshot")
        assert len(snapshot_calls) == 1
        slot = snapshot_calls[0][0].slots[0]
        assert slot.extracted_text == "Hello math"
        assert slot.content is not None
        assert slot.content.cropped_image == b"img-data"


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


class TestPlotlyToggle:
    """Step 5: Plotly 可視化モードの状態管理を検証する。"""

    def test_initial_plotly_mode_is_off(
        self,
        panel_presenter: PanelPresenter,
    ) -> None:
        assert panel_presenter._plotly_mode == "off"

    def test_set_plotly_mode_propagates_to_view(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        panel_presenter.set_plotly_mode("python")

        assert panel_presenter._plotly_mode == "python"
        assert mock_side_panel_view.get_calls("set_plotly_mode")[-1] == (
            "python",
        )

    def test_mode_change_updates_state_and_notifies_handler(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        observed: list[str] = []
        panel_presenter.set_on_plotly_mode_changed_handler(observed.append)

        mock_side_panel_view.simulate_plotly_mode_changed("json")
        mock_side_panel_view.simulate_plotly_mode_changed("python")

        assert panel_presenter._plotly_mode == "python"
        assert observed == ["json", "python"]


class TestPlotlyRenderFlow:
    """Step 10: Plotly spec 抽出と render handler push を検証する。"""

    @pytest.mark.asyncio
    async def test_translate_with_plotly_disabled_does_not_emit_render_request(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello world"))
        )
        mock_ai_model.analyze = AsyncMock(
            return_value=AnalysisResult(
                translated_text="done",
                raw_response=(
                    "## Plot\n\n"
                    "```json\n"
                    '{"data": [], "layout": {}}\n'
                    "```"
                ),
            )
        )
        rendered: list[PlotlyRenderRequest] = []
        panel_presenter.set_on_plotly_render_handler(rendered.append)

        await panel_presenter._do_translate(include_explanation=False)

        request = mock_ai_model.analyze.await_args.args[0]
        assert request.request_plotly_mode == "off"
        assert rendered == []
        assert panel_presenter._latest_plotly_specs == []

    @pytest.mark.asyncio
    async def test_translate_with_plotly_json_mode_emits_render_request(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
        mock_side_panel_view: MockSidePanelView,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello world"))
        )
        mock_side_panel_view.simulate_plotly_mode_changed("json")
        mock_ai_model.analyze = AsyncMock(
            return_value=AnalysisResult(
                translated_text="done",
                raw_response=(
                    "## Velocity Plot\n\n"
                    "```json\n"
                    '{"data": [{"type": "scatter"}], "layout": {}}\n'
                    "```"
                ),
            )
        )
        rendered: list[PlotlyRenderRequest] = []
        panel_presenter.set_on_plotly_render_handler(rendered.append)
        elapsed_values = iter([10.0, 10.5])
        monkeypatch.setattr(
            "pdf_epub_reader.presenters.panel_presenter.time.perf_counter",
            lambda: next(elapsed_values),
        )

        finished: list[float] = []
        panel_presenter.set_on_ai_request_finished_handler(finished.append)

        await panel_presenter._do_translate(include_explanation=False)

        request = mock_ai_model.analyze.await_args.args[0]
        assert request.request_plotly_mode == "json"
        assert len(rendered) == 1
        assert rendered[0].origin_mode == "json"
        assert rendered[0].ai_response_elapsed_s == pytest.approx(0.5)
        assert len(rendered[0].specs) == 1
        assert rendered[0].specs[0].title == "Velocity Plot"
        assert panel_presenter._latest_plotly_specs == rendered[0].specs
        assert finished == [0.5]

    @pytest.mark.asyncio
    async def test_translate_with_python_plotly_mode_requests_python(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello world"))
        )
        panel_presenter.set_plotly_mode("python")
        mock_ai_model.analyze = AsyncMock(
            return_value=AnalysisResult(translated_text="done", raw_response="done")
        )

        await panel_presenter._do_translate(include_explanation=False)

        request = mock_ai_model.analyze.await_args.args[0]
        assert request.request_plotly_mode == "python"

    @pytest.mark.asyncio
    async def test_python_mode_prefers_python_specs_over_json_specs(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello world"))
        )
        panel_presenter.set_plotly_mode("python")
        mock_ai_model.analyze = AsyncMock(
            return_value=AnalysisResult(
                translated_text="done",
                raw_response=(
                    "## Python Plot\n\n"
                    "```python\n"
                    "print(fig.to_json())\n"
                    "```\n\n"
                    "```json\n"
                    '{"data": [], "layout": {}}\n'
                    "```"
                ),
            )
        )
        rendered: list[PlotlyRenderRequest] = []
        panel_presenter.set_on_plotly_render_handler(rendered.append)

        await panel_presenter._do_translate(include_explanation=False)

        assert rendered[0].origin_mode == "python"
        assert [spec.language for spec in rendered[0].specs] == ["python"]

    @pytest.mark.asyncio
    async def test_python_mode_falls_back_to_json_when_python_block_missing(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello world"))
        )
        panel_presenter.set_plotly_mode("python")
        mock_ai_model.analyze = AsyncMock(
            return_value=AnalysisResult(
                translated_text="done",
                raw_response=(
                    "## Json Plot\n\n"
                    "```json\n"
                    '{"data": [], "layout": {}}\n'
                    "```"
                ),
            )
        )
        rendered: list[PlotlyRenderRequest] = []
        panel_presenter.set_on_plotly_render_handler(rendered.append)

        await panel_presenter._do_translate(include_explanation=False)

        assert rendered[0].origin_mode == "python"
        assert [spec.language for spec in rendered[0].specs] == ["json"]

    @pytest.mark.asyncio
    async def test_ai_failure_resets_plotly_specs(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_available_models(["models/gemini-2.0-flash"])
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
        presenter.set_plotly_mode("json")
        presenter._latest_plotly_specs = [object()]  # type: ignore[list-item]
        mock_ai_model.analyze = AsyncMock(
            side_effect=AIAPIError("Something went wrong", status_code=500)
        )

        await presenter._do_translate(include_explanation=False)

        assert presenter._latest_plotly_specs == []

    def test_selection_snapshot_reset_clears_plotly_specs(
        self,
        panel_presenter: PanelPresenter,
    ) -> None:
        panel_presenter._latest_plotly_specs = [object()]  # type: ignore[list-item]

        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Changed"))
        )

        assert panel_presenter._latest_plotly_specs == []


class TestMultimodalAnalysis:
    """Phase 4: AI 解析時の画像添付を検証する。"""

    @pytest.mark.asyncio
    async def test_translate_includes_images_when_cropped(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        """クロップ画像がある場合、AnalysisRequest.images に含まれることを確認する。"""
        panel_presenter.set_selection_snapshot(
            _make_snapshot(
                _make_slot(1, 0, "Math formula", cropped_image=b"cropped-png")
            )
        )
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
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Plain text"))
        )
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
        panel_presenter.set_selection_snapshot(
            _make_snapshot(
                _make_slot(1, 0, "Some content", cropped_image=b"image-bytes")
            )
        )
        await panel_presenter._do_custom_prompt("Explain this")

        analyze_calls = mock_ai_model.get_calls("analyze")
        request = analyze_calls[0][0]
        assert request.images == [b"image-bytes"]
        assert request.mode == AnalysisMode.CUSTOM_PROMPT


class TestTranslatedDialogs:
    def test_model_change_confirm_is_translated_after_language_switch(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        panel_presenter.apply_ui_language("en")
        panel_presenter.set_available_models(["model-a", "model-b"])
        panel_presenter.set_selected_model("model-a")
        panel_presenter.update_cache_status(
            CacheStatus(is_active=True, model_name="model-a")
        )

        mock_side_panel_view.simulate_model_changed("model-b")

        confirm_calls = mock_side_panel_view.get_calls("show_confirm_dialog")
        assert confirm_calls[-1] == (
            "Confirm Model Change",
            "The cache is tied to the current model. Changing the model will delete the cache.\nContinue?",
        )

    @pytest.mark.asyncio
    async def test_multiple_selection_text_and_images_preserve_order(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        """複数選択の本文と画像配列が選択順で組み立てられることを確認する。"""
        panel_presenter.set_selection_snapshot(
            _make_snapshot(
                _make_slot(1, 1, "First chunk", cropped_image=b"img-1"),
                _make_slot(2, 3, "Second chunk"),
                _make_slot(3, 5, "Third chunk", cropped_image=b"img-3"),
            )
        )

        await panel_presenter._do_translate(include_explanation=False)

        request = mock_ai_model.get_calls("analyze")[0][0]
        assert request.text == (
            "選択 1 / ページ 2\n\nFirst chunk\n\n"
            "選択 2 / ページ 4\n\nSecond chunk\n\n"
            "選択 3 / ページ 6\n\nThird chunk"
        )
        assert request.images == [b"img-1", b"img-3"]

    @pytest.mark.asyncio
    async def test_pending_slots_are_excluded_from_request_text(
        self,
        panel_presenter: PanelPresenter,
        mock_ai_model: MockAIModel,
    ) -> None:
        """pending スロットは連結本文と画像配列に含めない。"""
        panel_presenter.set_selection_snapshot(
            _make_snapshot(
                _make_slot(1, 0, "ready text", cropped_image=b"img-1"),
                _make_slot(2, 1, "still pending", read_state="pending"),
            )
        )

        await panel_presenter._do_translate(include_explanation=False)

        request = mock_ai_model.get_calls("analyze")[0][0]
        assert request.text == "選択 1 / ページ 1\n\nready text"
        assert request.images == [b"img-1"]


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
        presenter.set_available_models(["models/gemini-2.0-flash"])
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
        await presenter._do_translate(include_explanation=False)

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "API キー" in result_calls[0][0]
        assert presenter.export_state is None

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
        presenter.set_available_models(["models/gemini-2.0-flash"])
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
        await presenter._do_translate(include_explanation=False)

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "レート制限" in result_calls[0][0]
        assert presenter.export_state is None

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
        presenter.set_available_models(["models/gemini-2.0-flash"])
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
        await presenter._do_translate(include_explanation=False)

        result_calls = mock_side_panel_view.get_calls("update_result_text")
        assert len(result_calls) == 1
        assert "Something went wrong" in result_calls[0][0]
        assert presenter.export_state is None

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
        presenter.set_available_models(["models/gemini-2.0-flash"])
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
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
        presenter.set_available_models(["models/gemini-2.0-flash"])
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
        await presenter._do_translate(include_explanation=False)

        loading_calls = mock_side_panel_view.get_calls("show_loading")
        assert loading_calls[-1] == (False,)

    @pytest.mark.asyncio
    async def test_cancel_active_request_emits_cancel_handler(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_available_models(["models/gemini-2.0-flash"])
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )

        started = asyncio.Event()

        async def _analyze(request):
            started.set()
            await asyncio.Event().wait()

        mock_ai_model.analyze = AsyncMock(side_effect=_analyze)

        cancelled: list[bool] = []
        presenter.set_on_ai_request_cancelled_handler(
            lambda: cancelled.append(True)
        )

        presenter._on_translate_requested(include_explanation=False)
        await started.wait()

        active_task = presenter._active_analysis_task
        assert active_task is not None

        presenter.cancel_active_request()

        with pytest.raises(asyncio.CancelledError):
            await active_task

        assert cancelled == [True]
        assert mock_side_panel_view.get_calls("update_result_text") == []
        assert mock_ai_model.get_calls("invalidate_cache") == []

    @pytest.mark.asyncio
    async def test_unexpected_exception_emits_failed_handler(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_available_models(["models/gemini-2.0-flash"])
        presenter.set_selected_model("models/gemini-2.0-flash")
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
        mock_ai_model.analyze = AsyncMock(side_effect=RuntimeError("boom"))

        failed: list[bool] = []
        presenter.set_on_ai_request_failed_handler(lambda: failed.append(True))

        with pytest.raises(RuntimeError, match="boom"):
            await presenter._do_translate(include_explanation=False)

        assert failed == [True]
        assert mock_side_panel_view.get_calls("update_result_text") == []


class TestModelSelection:
    """Phase 6: モデル選択の状態管理と AnalysisRequest 伝播を検証する。"""

    def test_set_available_models_propagates_to_view(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """set_available_models が View に伝播すること。"""
        mock_side_panel_view.calls.clear()
        panel_presenter.set_available_models(["model-a", "model-b"])
        calls = mock_side_panel_view.get_calls("set_available_models")
        assert len(calls) == 1
        assert calls[0] == (["model-a", "model-b"],)
        assert mock_side_panel_view.get_calls("set_selected_model")[-1] == ("",)
        assert mock_side_panel_view.get_calls("set_model_combo_enabled")[-1] == (False,)

    def test_set_selected_model_propagates_to_view(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """set_selected_model が View に伝播すること。"""
        panel_presenter.set_available_models(["model-x"])
        mock_side_panel_view.calls.clear()
        panel_presenter.set_selected_model("model-x")
        calls = mock_side_panel_view.get_calls("set_selected_model")
        assert calls[-1] == ("model-x",)
        assert mock_side_panel_view.get_calls("set_model_combo_enabled")[-1] == (True,)

    def test_model_changed_updates_internal_state(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """View のモデル変更が内部状態に反映されること。"""
        panel_presenter.set_available_models(["models/gemini-2.0-flash", "new-model"])
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
        panel_presenter.set_available_models([
            "models/gemini-2.0-flash",
            "gemini-2.0-pro",
        ])
        mock_side_panel_view.simulate_model_changed("gemini-2.0-pro")
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Test text"))
        )
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
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Test text"))
        )
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


class TestSelectionHandlers:
    """Phase 6: SidePanel の削除・全消去イベント中継を検証する。"""

    def test_selection_delete_handler_called(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """個別削除ボタンで登録ハンドラが呼ばれること。"""
        called: list[str] = []
        panel_presenter.set_on_selection_delete_handler(called.append)

        mock_side_panel_view.simulate_selection_delete_requested("selection-2")

        assert called == ["selection-2"]

    def test_clear_selections_handler_called(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """全消去ボタンで登録ハンドラが呼ばれること。"""
        called: list[str] = []
        panel_presenter.set_on_clear_selections_handler(
            lambda: called.append("cleared")
        )

        mock_side_panel_view.simulate_clear_selections_requested()

        assert called == ["cleared"]


class TestExportState:
    def test_export_button_stays_disabled_until_success(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        assert panel_presenter.export_state is None
        assert mock_side_panel_view.get_calls("set_export_enabled")[-1] == (False,)

    @pytest.mark.asyncio
    async def test_active_tab_controls_shared_export_button(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello world"))
        )
        await panel_presenter._do_translate(include_explanation=False)

        assert panel_presenter.export_state is not None
        assert panel_presenter.export_state.action_mode == AnalysisMode.TRANSLATION

        mock_side_panel_view.simulate_tab_changed("custom_prompt")

        assert panel_presenter.export_state is None
        assert mock_side_panel_view.get_calls("set_export_enabled")[-1] == (False,)

        mock_side_panel_view.simulate_tab_changed("translation")

        assert panel_presenter.export_state is not None
        assert panel_presenter.export_state.action_mode == AnalysisMode.TRANSLATION
        assert mock_side_panel_view.get_calls("set_export_enabled")[-1] == (True,)

    @pytest.mark.asyncio
    async def test_selection_change_invalidates_export_state(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello world"))
        )
        await panel_presenter._do_translate(include_explanation=False)

        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 1, "Changed selection"))
        )

        assert panel_presenter.export_state is None
        assert mock_side_panel_view.get_calls("set_export_enabled")[-1] == (False,)

    def test_export_request_handler_called_only_when_active_state_exists(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        called: list[str] = []
        panel_presenter.set_on_export_requested_handler(
            lambda: called.append("export")
        )

        mock_side_panel_view.simulate_export_requested()
        assert called == []

        panel_presenter._store_export_state(
            action_mode=AnalysisMode.TRANSLATION,
            result=AnalysisResult(translated_text="Done", raw_response="Done"),
            include_explanation=False,
        )
        mock_side_panel_view.simulate_export_requested()

        assert called == ["export"]

    def test_update_cache_status_active(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """update_cache_status(active) で View が有効表示に更新されること。"""
        status = CacheStatus(
            is_active=True, token_count=5000, cache_name="c1"
        )
        panel_presenter.update_cache_status(status)

        active_calls = mock_side_panel_view.get_calls("set_cache_active")
        assert active_calls[-1] == (True,)

        brief_calls = mock_side_panel_view.get_calls(
            "update_cache_status_brief"
        )
        assert "有効" in brief_calls[-1][0]
        assert "5000" in brief_calls[-1][0]

    def test_update_cache_status_inactive(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """update_cache_status(inactive) で View が無効表示に更新されること。"""
        panel_presenter.update_cache_status(CacheStatus())

        active_calls = mock_side_panel_view.get_calls("set_cache_active")
        assert active_calls[-1] == (False,)

        brief_calls = mock_side_panel_view.get_calls(
            "update_cache_status_brief"
        )
        assert "無効" in brief_calls[-1][0]


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
        presenter.set_available_models(["model-a", "model-b"])
        presenter.set_selected_model("model-a")
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
        presenter.set_available_models(["model-a", "model-b"])
        presenter.set_selected_model("model-a")
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
        assert presenter._current_model == "model-a"
        assert mock_side_panel_view.get_calls("set_model_combo_enabled")[-1] == (True,)

    def test_model_change_same_model_no_dialog(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """同一モデルへの変更ではダイアログが出ないこと。"""
        presenter = PanelPresenter(
            view=mock_side_panel_view, ai_model=mock_ai_model
        )
        presenter.set_available_models(["model-a", "model-b"])
        presenter.set_selected_model("model-a")
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
        panel_presenter.set_available_models(["models/gemini-2.0-flash", "any-model"])
        mock_side_panel_view.simulate_model_changed("any-model")

        dialog_calls = mock_side_panel_view.get_calls("show_confirm_dialog")
        assert len(dialog_calls) == 0
        assert panel_presenter._current_model == "any-model"


class TestGetCurrentModel:
    """Phase 7 Bugfix: get_current_model() の動作を検証する。"""

    def test_initial_model_is_empty_string(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        """初期状態では get_current_model が空文字を返すこと。"""
        presenter = PanelPresenter(view=mock_side_panel_view, ai_model=mock_ai_model)
        assert presenter.get_current_model() == ""

    def test_set_selected_model_updates_getter(
        self,
        panel_presenter: PanelPresenter,
    ) -> None:
        """set_selected_model 後に get_current_model が正しい値を返すこと。"""
        panel_presenter.set_available_models(["gemini-2.0-pro"])
        panel_presenter.set_selected_model("gemini-2.0-pro")
        assert panel_presenter.get_current_model() == "gemini-2.0-pro"

    def test_model_changed_via_view_updates_getter(
        self,
        panel_presenter: PanelPresenter,
        mock_side_panel_view: MockSidePanelView,
    ) -> None:
        """View からのモデル変更が get_current_model に反映されること。"""
        panel_presenter.set_available_models(["models/gemini-2.0-flash", "new-model"])
        mock_side_panel_view.simulate_model_changed("new-model")
        assert panel_presenter.get_current_model() == "new-model"

    def test_available_models_without_selection_disables_combo(
        self,
        mock_side_panel_view: MockSidePanelView,
        mock_ai_model: MockAIModel,
    ) -> None:
        presenter = PanelPresenter(view=mock_side_panel_view, ai_model=mock_ai_model)

        presenter.set_available_models(["model-a", "model-b"])

        assert presenter.get_current_model() == ""
        assert mock_side_panel_view.get_calls("set_selected_model")[-1] == ("",)
        assert mock_side_panel_view.get_calls("set_model_combo_enabled")[-1] == (False,)


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
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
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
        presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
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
        panel_presenter.set_available_models(["gemini-pro"])
        panel_presenter.set_selected_model("gemini-pro")
        panel_presenter.set_selection_snapshot(
            _make_snapshot(_make_slot(1, 0, "Hello"))
        )
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
