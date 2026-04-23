"""Capture stack for desktop_capture Phase 1."""

from desktop_capture.capture.overlay import (
    ScreenScaleContext,
    SelectionOverlay,
    logical_rect_to_physical,
    normalize_drag_rect,
)
from desktop_capture.capture.screenshot import MssCaptureGateway

__all__ = [
    "MssCaptureGateway",
    "ScreenScaleContext",
    "SelectionOverlay",
    "logical_rect_to_physical",
    "normalize_drag_rect",
]