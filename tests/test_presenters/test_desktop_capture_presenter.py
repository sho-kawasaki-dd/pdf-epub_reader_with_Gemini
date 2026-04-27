from __future__ import annotations

from pdf_epub_reader.dto.ai_dto import AnalysisResult

from desktop_capture.config import DesktopCaptureConfig
from desktop_capture.contracts import CaptureFlowState, CapturedImage, CaptureRect
from desktop_capture.presenter import DesktopCapturePresenter


class MockDesktopCaptureView:
    def __init__(self) -> None:
        self.status_calls: list[tuple[CaptureFlowState, str]] = []
        self.result_calls: list[AnalysisResult] = []
        self.error_calls: list[str] = []

    def show_status(self, state: CaptureFlowState, message: str) -> None:
        self.status_calls.append((state, message))

    def show_result(self, result: AnalysisResult) -> None:
        self.result_calls.append(result)

    def show_error(self, message: str) -> None:
        self.error_calls.append(message)


class FakeCaptureGateway:
    def __init__(self, image: CapturedImage | None = None) -> None:
        self.calls: list[CaptureRect] = []
        self._image = image or CapturedImage(b"image-bytes", width=120, height=40)

    async def capture(self, rect: CaptureRect) -> CapturedImage:
        self.calls.append(rect)
        return self._image


class FakeAIGateway:
    def __init__(self, result: AnalysisResult | None = None) -> None:
        self.calls = []
        self._result = result or AnalysisResult(
            translated_text="translated",
            raw_response="translated",
        )

    async def analyze(self, request):
        self.calls.append(request)
        return self._result


class RaisingCaptureGateway:
    async def capture(self, rect: CaptureRect) -> CapturedImage:
        raise RuntimeError("capture failed")


class RaisingAIGateway:
    async def analyze(self, request):
        raise RuntimeError("analysis failed")


def test_initial_state_is_idle() -> None:
    view = MockDesktopCaptureView()
    presenter = DesktopCapturePresenter(
        view=view,
        capture_gateway=FakeCaptureGateway(),
        ai_gateway=FakeAIGateway(),
        config=DesktopCaptureConfig(),
    )

    assert presenter.state is CaptureFlowState.IDLE
    assert view.status_calls == [
        (CaptureFlowState.IDLE, "Ready to capture."),
    ]


def test_request_capture_sets_selecting_state() -> None:
    view = MockDesktopCaptureView()
    presenter = DesktopCapturePresenter(
        view=view,
        capture_gateway=FakeCaptureGateway(),
        ai_gateway=FakeAIGateway(),
        config=DesktopCaptureConfig(gemini_model_name="models/gemini-2.5-flash"),
    )

    presenter.request_capture()

    assert presenter.state is CaptureFlowState.SELECTING
    assert view.status_calls[-1] == (
        CaptureFlowState.SELECTING,
        "Select an area to capture.",
    )


async def test_submit_selection_builds_translation_only_request() -> None:
    view = MockDesktopCaptureView()
    capture_gateway = FakeCaptureGateway()
    ai_gateway = FakeAIGateway()
    presenter = DesktopCapturePresenter(
        view=view,
        capture_gateway=capture_gateway,
        ai_gateway=ai_gateway,
        config=DesktopCaptureConfig(
            gemini_model_name="models/gemini-2.5-flash",
            output_language="English",
        ),
    )

    result = await presenter.submit_selection(CaptureRect(10, 20, 300, 120))

    assert result is not None
    assert presenter.state is CaptureFlowState.SHOWING_RESULT
    assert capture_gateway.calls == [CaptureRect(10, 20, 300, 120)]
    request = ai_gateway.calls[0]
    assert request.text == ""
    assert request.mode.value == "translation"
    assert request.include_explanation is False
    assert request.images == [b"image-bytes"]
    assert request.model_name == "models/gemini-2.5-flash"
    assert "Translate the given text into English" in request.system_prompt
    assert view.result_calls == [result]
    assert view.error_calls == []
    assert view.status_calls == [
        (CaptureFlowState.IDLE, "Ready to capture."),
        (CaptureFlowState.CAPTURING, "Capturing selection..."),
        (CaptureFlowState.ANALYZING, "Analyzing capture..."),
        (CaptureFlowState.SHOWING_RESULT, "Translation ready."),
    ]


async def test_submit_selection_rejects_zero_sized_rect() -> None:
    view = MockDesktopCaptureView()
    capture_gateway = FakeCaptureGateway()
    ai_gateway = FakeAIGateway()
    presenter = DesktopCapturePresenter(
        view=view,
        capture_gateway=capture_gateway,
        ai_gateway=ai_gateway,
        config=DesktopCaptureConfig(gemini_model_name="models/gemini-2.5-flash"),
    )

    result = await presenter.submit_selection(CaptureRect(0, 0, 0, 10))

    assert result is None
    assert presenter.state is CaptureFlowState.SHOWING_ERROR
    assert capture_gateway.calls == []
    assert ai_gateway.calls == []
    assert view.error_calls == ["Select a non-empty area before capturing."]


async def test_submit_selection_surfaces_capture_errors() -> None:
    view = MockDesktopCaptureView()
    presenter = DesktopCapturePresenter(
        view=view,
        capture_gateway=RaisingCaptureGateway(),
        ai_gateway=FakeAIGateway(),
        config=DesktopCaptureConfig(gemini_model_name="models/gemini-2.5-flash"),
    )

    result = await presenter.submit_selection(CaptureRect(0, 0, 10, 10))

    assert result is None
    assert presenter.state is CaptureFlowState.SHOWING_ERROR
    assert view.error_calls == [
        "Failed to capture the selected area: capture failed",
    ]


async def test_submit_selection_surfaces_analysis_errors() -> None:
    view = MockDesktopCaptureView()
    presenter = DesktopCapturePresenter(
        view=view,
        capture_gateway=FakeCaptureGateway(),
        ai_gateway=RaisingAIGateway(),
        config=DesktopCaptureConfig(gemini_model_name="models/gemini-2.5-flash"),
    )

    result = await presenter.submit_selection(CaptureRect(0, 0, 10, 10))

    assert result is None
    assert presenter.state is CaptureFlowState.SHOWING_ERROR
    assert view.status_calls == [
        (CaptureFlowState.IDLE, "Ready to capture."),
        (CaptureFlowState.CAPTURING, "Capturing selection..."),
        (CaptureFlowState.ANALYZING, "Analyzing capture..."),
    ]
    assert view.error_calls == [
        "Failed to analyze the captured image: analysis failed",
    ]


async def test_submit_selection_requires_model_name_before_capture() -> None:
    view = MockDesktopCaptureView()
    capture_gateway = FakeCaptureGateway()
    ai_gateway = FakeAIGateway()
    presenter = DesktopCapturePresenter(
        view=view,
        capture_gateway=capture_gateway,
        ai_gateway=ai_gateway,
        config=DesktopCaptureConfig(gemini_model_name=""),
    )

    result = await presenter.submit_selection(CaptureRect(0, 0, 10, 10))

    assert result is None
    assert presenter.state is CaptureFlowState.SHOWING_ERROR
    assert capture_gateway.calls == []
    assert ai_gateway.calls == []
    assert view.error_calls == ["Select a Gemini model before capturing."]