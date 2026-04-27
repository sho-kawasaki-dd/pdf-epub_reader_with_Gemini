"""Presenter and state machine for the desktop capture Phase 1 flow."""

from __future__ import annotations

import logging

from pdf_epub_reader.dto.ai_dto import AnalysisMode, AnalysisRequest, AnalysisResult

from desktop_capture.config import DesktopCaptureConfig
from desktop_capture.contracts import (
    CaptureFlowState,
    CaptureRect,
    DesktopCaptureAIGateway,
    DesktopCaptureResultView,
    ScreenCaptureGateway,
)

logger = logging.getLogger(__name__)


class DesktopCapturePresenter:
    """Coordinate screen capture, AI analysis, and result rendering."""

    def __init__(
        self,
        view: DesktopCaptureResultView,
        capture_gateway: ScreenCaptureGateway,
        ai_gateway: DesktopCaptureAIGateway,
        config: DesktopCaptureConfig,
    ) -> None:
        self._view = view
        self._capture_gateway = capture_gateway
        self._ai_gateway = ai_gateway
        self._config = config
        self._state = CaptureFlowState.IDLE
        self._last_result: AnalysisResult | None = None
        self._last_error: str | None = None
        self._view.show_status(self._state, "Ready to capture.")

    @property
    def state(self) -> CaptureFlowState:
        """Return the current high-level flow state."""
        return self._state

    @property
    def last_result(self) -> AnalysisResult | None:
        """Return the most recent successful analysis result."""
        return self._last_result

    @property
    def last_error(self) -> str | None:
        """Return the most recent user-facing error string."""
        return self._last_error

    def request_capture(self) -> None:
        """Move the flow into selection mode."""
        self._last_error = None
        self._set_state(
            CaptureFlowState.SELECTING,
            "Select an area to capture.",
        )

    def cancel_capture(self) -> None:
        """Return to idle after the user cancels the selection."""
        self._last_error = None
        self._set_state(CaptureFlowState.IDLE, "Capture cancelled.")

    async def submit_selection(self, rect: CaptureRect) -> AnalysisResult | None:
        """Run capture and AI analysis from a normalized crop rectangle."""
        if rect.is_empty:
            self._show_error("Select a non-empty area before capturing.")
            return None

        selected_model_name = self._config.gemini_model_name.strip()
        if not selected_model_name:
            self._show_error("Select a Gemini model before capturing.")
            return None

        self._last_error = None
        self._set_state(CaptureFlowState.CAPTURING, "Capturing selection...")

        try:
            captured_image = await self._capture_gateway.capture(rect)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Desktop capture failed: %s", exc)
            self._show_error(f"Failed to capture the selected area: {exc}")
            return None

        if not captured_image.image_bytes:
            self._show_error("Capture produced no image data.")
            return None

        self._set_state(CaptureFlowState.ANALYZING, "Analyzing capture...")

        request = AnalysisRequest(
            text="",
            mode=AnalysisMode.TRANSLATION,
            include_explanation=False,
            system_prompt=self._build_system_prompt(),
            images=[captured_image.image_bytes],
            model_name=selected_model_name,
        )

        try:
            result = await self._ai_gateway.analyze(request)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Desktop capture analysis failed: %s", exc)
            self._show_error(f"Failed to analyze the captured image: {exc}")
            return None

        self._last_result = result
        self._set_state(CaptureFlowState.SHOWING_RESULT, "Translation ready.")
        self._view.show_result(result)
        return result

    def _build_system_prompt(self) -> str:
        try:
            return self._config.system_prompt.format(
                output_language=self._config.output_language,
            )
        except (IndexError, KeyError, ValueError):
            return self._config.system_prompt

    def _set_state(self, state: CaptureFlowState, message: str) -> None:
        self._state = state
        self._view.show_status(state, message)

    def _show_error(self, message: str) -> None:
        self._state = CaptureFlowState.SHOWING_ERROR
        self._last_error = message
        self._view.show_error(message)
