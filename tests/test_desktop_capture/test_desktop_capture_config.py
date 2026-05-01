from __future__ import annotations

import json

from desktop_capture.config import (
    DEFAULT_DELAYED_CAPTURE_SECONDS,
    DEFAULT_HOTKEY,
    DEFAULT_OUTPUT_LANGUAGE,
    DesktopCaptureConfig,
    load_config,
    save_config,
)


def test_missing_config_returns_defaults(tmp_path) -> None:
    config_path = tmp_path / "config.json"

    config = load_config(config_path)

    assert config == DesktopCaptureConfig()


def test_load_config_ignores_unknown_fields_and_normalizes_values(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "capture_backend": "mss",
                "delayed_capture_seconds": -5,
                "output_language": "   ",
                "hotkey": "   ",
                "unknown_field": "ignored",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.capture_backend == "mss"
    assert config.delayed_capture_seconds == DEFAULT_DELAYED_CAPTURE_SECONDS
    assert config.output_language == DEFAULT_OUTPUT_LANGUAGE
    assert config.hotkey == DEFAULT_HOTKEY


def test_invalid_config_falls_back_to_defaults(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{invalid json", encoding="utf-8")

    config = load_config(config_path)

    assert config == DesktopCaptureConfig()


def test_save_config_round_trips_and_creates_parent_dir(tmp_path) -> None:
    config_path = tmp_path / "nested" / "capture-config.json"
    config = DesktopCaptureConfig(
        ocr_backend="rapidocr",
        capture_backend="wgc",
        delayed_capture_seconds=5,
        gemini_model_name="gemini-2.5-flash",
        output_language="English",
        system_prompt="Prompt for {output_language}",
        hotkey="Ctrl+Alt+G",
    )

    save_config(config, config_path)
    loaded = load_config(config_path)

    assert config_path.exists()
    assert loaded == config