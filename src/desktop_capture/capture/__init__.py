"""Capture stack for desktop_capture Phase 1."""

from desktop_capture.capture.overlay import (
    ScreenScaleContext,
    SelectionOverlay,
    logical_rect_to_physical,
    normalize_drag_rect,
)
from desktop_capture.capture.hotkey import GlobalHotkeyManager, HotkeyRegistrationResult, HotkeySpec, parse_hotkey_spec
from desktop_capture.capture.screenshot import MssCaptureGateway
from desktop_capture.capture.trigger_panel import CaptureTriggerPanel

__all__ = [
    "CaptureTriggerPanel",
    "GlobalHotkeyManager",
    "HotkeyRegistrationResult",
    "HotkeySpec",
    "MssCaptureGateway",
    "ScreenScaleContext",
    "SelectionOverlay",
    "logical_rect_to_physical",
    "normalize_drag_rect",
    "parse_hotkey_spec",
]