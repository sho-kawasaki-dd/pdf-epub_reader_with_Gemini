"""Contracts and shared DTOs for the desktop capture Phase 1 flow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from pdf_epub_reader.dto.ai_dto import AnalysisRequest, AnalysisResult, ModelInfo


class CaptureFlowState(Enum):
    """High-level presenter states for the desktop capture flow."""

    IDLE = "idle"
    SELECTING = "selecting"
    CAPTURING = "capturing"
    ANALYZING = "analyzing"
    SHOWING_RESULT = "showing_result"
    SHOWING_ERROR = "showing_error"


@dataclass(frozen=True)
class CaptureRect:
    """A physical-pixel crop rectangle produced after DPI normalization."""

    left: int
    top: int
    width: int
    height: int

    @property
    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0


@dataclass(frozen=True)
class CapturedImage:
    """A cropped image payload ready for AI analysis."""

    image_bytes: bytes
    width: int
    height: int


@runtime_checkable
class ScreenCaptureGateway(Protocol):
    """Service boundary for turning a physical crop rect into image bytes."""

    async def capture(self, rect: CaptureRect) -> CapturedImage: ...


@runtime_checkable
class DesktopCaptureAIGateway(Protocol):
    """Service boundary for sending a prepared analysis request to Gemini."""

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult: ...

    async def list_available_models(self) -> list[ModelInfo]: ...


@runtime_checkable
class DesktopCaptureResultView(Protocol):
    """Minimal result-view surface the presenter can drive without Qt details."""

    def show_status(self, state: CaptureFlowState, message: str) -> None: ...

    def show_result(self, result: AnalysisResult) -> None: ...

    def show_error(self, message: str) -> None: ...
