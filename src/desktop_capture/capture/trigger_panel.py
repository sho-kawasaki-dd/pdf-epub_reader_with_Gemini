"""Small launcher panel for immediate and delayed desktop capture."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class CaptureTriggerPanel(QWidget):
    """Fallback launcher UI when global hotkeys are unavailable or inconvenient."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_capture_requested: Callable[[], None] | None = None
        self._on_model_changed: Callable[[str], None] | None = None
        self._on_fetch_models_requested: Callable[[], None] | None = None
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

        model_row = QHBoxLayout()
        self._model_label = QLabel("Model")
        model_row.addWidget(self._model_label)

        self._model_combo = QComboBox()
        self._model_combo.currentIndexChanged.connect(self._handle_model_changed)
        model_row.addWidget(self._model_combo, stretch=1)

        self._fetch_models_button = QPushButton("Fetch models")
        self._fetch_models_button.clicked.connect(self._handle_fetch_models_clicked)
        model_row.addWidget(self._fetch_models_button)
        layout.addLayout(model_row)

        self._model_error_label = QLabel("")
        self._model_error_label.setWordWrap(True)
        self._model_error_label.setStyleSheet("color: #b3261e;")
        self._model_error_label.hide()
        layout.addWidget(self._model_error_label)

        self.set_model_options([], "")

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

    def set_on_model_changed(self, callback: Callable[[str], None]) -> None:
        self._on_model_changed = callback

    def set_on_fetch_models_requested(self, callback: Callable[[], None]) -> None:
        self._on_fetch_models_requested = callback

    def set_hotkey_status(self, message: str) -> None:
        self._hotkey_status_label.setText(message)

    def set_status_text(self, message: str) -> None:
        self._status_label.setText(message)

    def set_model_options(
        self,
        model_names: list[str],
        selected_model_name: str,
    ) -> None:
        selected = selected_model_name.strip()
        unique_names: list[str] = []
        for model_name in model_names:
            normalized = model_name.strip()
            if normalized and normalized not in unique_names:
                unique_names.append(normalized)
        if selected and selected not in unique_names:
            unique_names.insert(0, selected)

        blocker = QSignalBlocker(self._model_combo)
        self._model_combo.clear()
        self._model_combo.addItem("Select a Gemini model", "")
        for model_name in unique_names:
            self._model_combo.addItem(model_name, model_name)

        selected_index = self._model_combo.findData(selected)
        self._model_combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        del blocker

    def set_model_error_text(self, message: str) -> None:
        text = message.strip()
        self._model_error_label.setText(text)
        self._model_error_label.setVisible(bool(text))

    def set_model_fetch_in_progress(self, in_progress: bool) -> None:
        self._fetch_models_button.setEnabled(not in_progress)
        self._fetch_models_button.setText(
            "Fetching..." if in_progress else "Fetch models"
        )

    def selected_model_name(self) -> str:
        selected = self._model_combo.currentData()
        return selected if isinstance(selected, str) else ""

    def available_model_names(self) -> list[str]:
        return [
            self._model_combo.itemData(index)
            for index in range(self._model_combo.count())
            if isinstance(self._model_combo.itemData(index), str)
            and self._model_combo.itemData(index)
        ]

    def model_error_text(self) -> str:
        return self._model_error_label.text()

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

    def _handle_model_changed(self, index: int) -> None:
        if index < 0 or self._on_model_changed is None:
            return
        self._on_model_changed(self.selected_model_name())

    def _handle_fetch_models_clicked(self) -> None:
        if self._on_fetch_models_requested is not None:
            self._on_fetch_models_requested()

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