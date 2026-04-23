from __future__ import annotations

import pytest

from desktop_capture.capture.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    parse_hotkey_spec,
)


def test_parse_hotkey_spec_parses_default_shortcut() -> None:
    spec = parse_hotkey_spec("Ctrl+Shift+G")

    assert spec.modifiers == MOD_CONTROL | MOD_SHIFT
    assert spec.virtual_key == ord("G")
    assert spec.normalized_text == "Ctrl+Shift+G"


def test_parse_hotkey_spec_supports_function_keys_and_alt() -> None:
    spec = parse_hotkey_spec("Alt+F8")

    assert spec.modifiers == MOD_ALT
    assert spec.virtual_key == 0x77
    assert spec.normalized_text == "Alt+F8"


@pytest.mark.parametrize(
    "value",
    ["", "G", "Ctrl+Shift", "Ctrl+Shift+Alt+UnknownKey"],
)
def test_parse_hotkey_spec_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_hotkey_spec(value)