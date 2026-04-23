"""Windows global hotkey support for desktop_capture Phase 1."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


@dataclass(frozen=True)
class HotkeySpec:
    modifiers: int
    virtual_key: int
    normalized_text: str


@dataclass(frozen=True)
class HotkeyRegistrationResult:
    success: bool
    message: str


def parse_hotkey_spec(spec: str) -> HotkeySpec:
    """Parse a simple hotkey string like Ctrl+Shift+G into Win32 values."""
    if not spec.strip():
        raise ValueError("Hotkey cannot be empty.")

    modifiers = 0
    key_token: str | None = None
    normalized_parts: list[str] = []

    for token in (part.strip() for part in spec.split("+")):
        if not token:
            continue
        token_upper = token.upper()
        if token_upper in {"CTRL", "CONTROL"}:
            modifiers |= MOD_CONTROL
            normalized_parts.append("Ctrl")
            continue
        if token_upper == "SHIFT":
            modifiers |= MOD_SHIFT
            normalized_parts.append("Shift")
            continue
        if token_upper == "ALT":
            modifiers |= MOD_ALT
            normalized_parts.append("Alt")
            continue
        if token_upper in {"WIN", "META"}:
            modifiers |= MOD_WIN
            normalized_parts.append("Win")
            continue
        if key_token is not None:
            raise ValueError("Hotkey must contain exactly one non-modifier key.")
        key_token = token_upper

    if modifiers == 0:
        raise ValueError("Hotkey must include at least one modifier key.")
    if key_token is None:
        raise ValueError("Hotkey is missing a key.")

    virtual_key = _parse_virtual_key(key_token)
    normalized_parts.append(key_token if len(key_token) > 1 else key_token.upper())
    return HotkeySpec(
        modifiers=modifiers,
        virtual_key=virtual_key,
        normalized_text="+".join(normalized_parts),
    )


def _parse_virtual_key(token: str) -> int:
    if len(token) == 1 and token.isalnum():
        return ord(token.upper())
    if token.startswith("F") and token[1:].isdigit():
        index = int(token[1:])
        if 1 <= index <= 24:
            return 0x70 + index - 1
    raise ValueError(f"Unsupported hotkey key: {token}")


class GlobalHotkeyManager(QAbstractNativeEventFilter):
    """Register and listen for one global Windows hotkey."""

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback
        self._registered = False
        self._spec: HotkeySpec | None = None
        self._hotkey_id = 0xBEEF

    def register(self, spec_text: str) -> HotkeyRegistrationResult:
        if not hasattr(ctypes, "windll"):
            return HotkeyRegistrationResult(False, "Global hotkeys are only supported on Windows.")

        try:
            spec = parse_hotkey_spec(spec_text)
        except ValueError as exc:
            return HotkeyRegistrationResult(False, str(exc))

        self.unregister()
        registered = bool(
            ctypes.windll.user32.RegisterHotKey(
                None,
                self._hotkey_id,
                spec.modifiers,
                spec.virtual_key,
            )
        )
        if not registered:
            return HotkeyRegistrationResult(
                False,
                f"Failed to register hotkey {spec.normalized_text}. It may already be in use.",
            )

        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self)

        self._registered = True
        self._spec = spec
        return HotkeyRegistrationResult(True, f"Hotkey ready: {spec.normalized_text}")

    def unregister(self) -> None:
        if not self._registered or not hasattr(ctypes, "windll"):
            self._registered = False
            self._spec = None
            return

        app = QApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self)
        ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
        self._registered = False
        self._spec = None

    def nativeEventFilter(self, eventType, message):
        if not self._registered or eventType != "windows_generic_MSG":
            return False, 0

        msg = MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and int(msg.wParam) == self._hotkey_id:
            self._callback()
            return True, 0
        return False, 0