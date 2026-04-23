"""Small launcher panel for immediate and delayed desktop capture."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class CaptureTriggerPanel(QWidget):
    """Fallback launcher UI when global hotkeys are unavailable or inconvenient."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_capture_requested: Callable[[], None] | None = None
        self._countdown_seconds_remaining = 0

        self.setWindowTitle("Desktop Capture")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        self._title_label = QLabel("Desktop Capture")
        self._title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(self._title_label)

        self._hotkey_status_label = QLabel("Hotkey not initialized.")
        self._hotkey_status_label.setWordWrap(True)
        layout.addWidget(self._hotkey_status_label)

        self._status_label = QLabel("Choose how to start capture.")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._capture_now_button = QPushButton("Capture now")
        self._capture_now_button.clicked.connect(self._handle_capture_now_clicked)
        layout.addWidget(self._capture_now_button)

        self._capture_in_3s_button = QPushButton("Capture in 3s")
        self._capture_in_3s_button.clicked.connect(lambda: self.start_countdown(3))
        layout.addWidget(self._capture_in_3s_button)

        self._capture_in_5s_button = QPushButton("Capture in 5s")
        self._capture_in_5s_button.clicked.connect(lambda: self.start_countdown(5))
        layout.addWidget(self._capture_in_5s_button)

        layout.addStretch()

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

    def set_on_capture_requested(self, callback: Callable[[], None]) -> None:
        self._on_capture_requested = callback

    def set_hotkey_status(self, message: str) -> None:
        self._hotkey_status_label.setText(message)

    def set_status_text(self, message: str) -> None:
        self._status_label.setText(message)

    def set_busy(self, busy: bool) -> None:
        enabled = not busy and not self.is_countdown_active()
        self._capture_now_button.setEnabled(enabled)
        self._capture_in_3s_button.setEnabled(enabled)
        self._capture_in_5s_button.setEnabled(enabled)

    def start_countdown(self, seconds: int) -> None:
        self._countdown_seconds_remaining = max(0, seconds)
        if self._countdown_seconds_remaining == 0:
            self._trigger_capture()
            return
        self._update_controls_for_countdown()
        self._status_label.setText(
            f"Capture starts in {self._countdown_seconds_remaining}s. Switch to the target app now."
        )
        self._countdown_timer.start()

    def cancel_countdown(self) -> None:
        if self._countdown_timer.isActive():
            self._countdown_timer.stop()
        self._countdown_seconds_remaining = 0
        self._restore_controls()
        self._status_label.setText("Choose how to start capture.")

    def is_countdown_active(self) -> bool:
        return self._countdown_timer.isActive()

    def hotkey_status_text(self) -> str:
        return self._hotkey_status_label.text()

    def status_text(self) -> str:
        return self._status_label.text()

    def _handle_capture_now_clicked(self) -> None:
        self.cancel_countdown()
        self._trigger_capture()

    def _on_countdown_tick(self) -> None:
        self._countdown_seconds_remaining -= 1
        if self._countdown_seconds_remaining <= 0:
            self._countdown_timer.stop()
            self._restore_controls()
            self._trigger_capture()
            return
        self._status_label.setText(
            f"Capture starts in {self._countdown_seconds_remaining}s. Switch to the target app now."
        )

    def _trigger_capture(self) -> None:
        self._restore_controls()
        self._status_label.setText("Opening selection overlay...")
        if self._on_capture_requested is not None:
            self._on_capture_requested()

    def _update_controls_for_countdown(self) -> None:
        self._capture_now_button.setEnabled(False)
        self._capture_in_3s_button.setEnabled(False)
        self._capture_in_5s_button.setEnabled(False)

    def _restore_controls(self) -> None:
        self._capture_now_button.setEnabled(True)
        self._capture_in_3s_button.setEnabled(True)
        self._capture_in_5s_button.setEnabled(True)