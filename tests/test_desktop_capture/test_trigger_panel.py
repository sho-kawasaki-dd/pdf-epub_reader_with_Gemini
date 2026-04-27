from __future__ import annotations

import os
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop_capture.capture.trigger_panel import CaptureTriggerPanel


def _get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return cast(QApplication, app)


def test_capture_now_invokes_callback() -> None:
    _get_app()
    calls: list[str] = []
    panel = CaptureTriggerPanel()
    panel.set_on_capture_requested(lambda: calls.append("capture"))

    panel._handle_capture_now_clicked()

    assert calls == ["capture"]
    assert panel.status_text() == "Opening selection overlay..."


def test_start_countdown_updates_status_and_triggers_callback() -> None:
    _get_app()
    calls: list[str] = []
    panel = CaptureTriggerPanel()
    panel.set_on_capture_requested(lambda: calls.append("capture"))

    panel.start_countdown(2)
    assert panel.is_countdown_active() is True
    assert panel.status_text() == "Capture starts in 2s. Switch to the target app now."

    panel._on_countdown_tick()
    assert panel.status_text() == "Capture starts in 1s. Switch to the target app now."

    panel._on_countdown_tick()
    assert calls == ["capture"]
    assert panel.is_countdown_active() is False


def test_cancel_countdown_restores_idle_status() -> None:
    _get_app()
    panel = CaptureTriggerPanel()

    panel.start_countdown(3)
    panel.cancel_countdown()

    assert panel.is_countdown_active() is False
    assert panel.status_text() == "Choose how to start capture."


def test_model_selection_shows_initial_config_value() -> None:
    _get_app()
    panel = CaptureTriggerPanel()

    panel.set_model_options([], "models/gemini-2.5-flash")

    assert panel.selected_model_name() == "models/gemini-2.5-flash"
    assert panel.available_model_names() == ["models/gemini-2.5-flash"]


def test_model_error_text_can_be_shown_without_modal_dialog() -> None:
    _get_app()
    panel = CaptureTriggerPanel()

    panel.set_model_error_text("Could not fetch Gemini models: missing API key")

    assert panel.model_error_text() == "Could not fetch Gemini models: missing API key"