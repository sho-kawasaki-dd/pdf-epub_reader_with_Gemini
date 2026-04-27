"""Capture stack for desktop_capture Phase 1."""

from __future__ import annotations

from importlib import import_module

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

_EXPORTS = {
    "CaptureTriggerPanel": (
        "desktop_capture.capture.trigger_panel",
        "CaptureTriggerPanel",
    ),
    "GlobalHotkeyManager": (
        "desktop_capture.capture.hotkey",
        "GlobalHotkeyManager",
    ),
    "HotkeyRegistrationResult": (
        "desktop_capture.capture.hotkey",
        "HotkeyRegistrationResult",
    ),
    "HotkeySpec": ("desktop_capture.capture.hotkey", "HotkeySpec"),
    "MssCaptureGateway": (
        "desktop_capture.capture.screenshot",
        "MssCaptureGateway",
    ),
    "ScreenScaleContext": (
        "desktop_capture.capture.overlay",
        "ScreenScaleContext",
    ),
    "SelectionOverlay": (
        "desktop_capture.capture.overlay",
        "SelectionOverlay",
    ),
    "logical_rect_to_physical": (
        "desktop_capture.capture.overlay",
        "logical_rect_to_physical",
    ),
    "normalize_drag_rect": (
        "desktop_capture.capture.overlay",
        "normalize_drag_rect",
    ),
    "parse_hotkey_spec": (
        "desktop_capture.capture.hotkey",
        "parse_hotkey_spec",
    ),
}


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value