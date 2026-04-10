"""設定ダイアログの PySide6 実装。

ISettingsDialogView Protocol を満たすモーダル QDialog。
OK / Cancel で一括適用し、「Reset to Defaults」でデフォルト復帰する。

2 タブ構成:
- Rendering: Image Format, JPEG Quality, Default DPI, Page Cache Size
- Detection: Auto-detect embedded images, Auto-detect math fonts
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pdf_epub_reader.utils.config import (
    DPI_MAX,
    DPI_MIN,
    JPEG_QUALITY_MAX,
    JPEG_QUALITY_MIN,
    PAGE_CACHE_MAX,
    PAGE_CACHE_MIN,
)


class SettingsDialog(QDialog):
    """ISettingsDialogView Protocol を満たす設定ダイアログ実装。

    モーダルダイアログとして表示し、OK / Cancel で操作結果を返す。
    Presenter がコールバック経由でリセットを指示し、View は表示のみを担当する。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(400)

        self._on_reset_defaults: Callable[[], None] | None = None

        # --- メインレイアウト ---
        layout = QVBoxLayout(self)

        # --- タブウィジェット ---
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # --- Rendering タブ ---
        rendering_tab = QWidget()
        rendering_layout = QFormLayout(rendering_tab)

        self._format_combo = QComboBox()
        self._format_combo.addItems(["png", "jpeg"])
        rendering_layout.addRow("Image Format:", self._format_combo)

        self._jpeg_quality_spin = QSpinBox()
        self._jpeg_quality_spin.setRange(JPEG_QUALITY_MIN, JPEG_QUALITY_MAX)
        rendering_layout.addRow("JPEG Quality:", self._jpeg_quality_spin)

        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(DPI_MIN, DPI_MAX)
        self._dpi_spin.setSingleStep(12)
        rendering_layout.addRow("Default DPI:", self._dpi_spin)

        self._cache_spin = QSpinBox()
        self._cache_spin.setRange(PAGE_CACHE_MIN, PAGE_CACHE_MAX)
        rendering_layout.addRow("Page Cache Size:", self._cache_spin)

        self._tabs.addTab(rendering_tab, "Rendering")

        # --- Detection タブ ---
        detection_tab = QWidget()
        detection_layout = QVBoxLayout(detection_tab)

        self._auto_images_check = QCheckBox(
            "Auto-detect embedded images"
        )
        detection_layout.addWidget(self._auto_images_check)

        self._auto_math_check = QCheckBox("Auto-detect math fonts")
        detection_layout.addWidget(self._auto_math_check)

        detection_layout.addStretch()
        self._tabs.addTab(detection_tab, "Detection")

        # --- ボタン行 ---
        button_layout = QHBoxLayout()

        reset_button = QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self._handle_reset)
        button_layout.addWidget(reset_button)

        button_layout.addStretch()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)

        # --- Image Format が PNG のとき JPEG Quality をグレーアウト ---
        self._format_combo.currentIndexChanged.connect(
            self._update_jpeg_quality_state
        )
        self._update_jpeg_quality_state()

    # =========================================================================
    # ISettingsDialogView — Getters
    # =========================================================================

    def get_render_format(self) -> Literal["png", "jpeg"]:
        text = self._format_combo.currentText()
        if text == "jpeg":
            return "jpeg"
        return "png"

    def get_jpeg_quality(self) -> int:
        return self._jpeg_quality_spin.value()

    def get_default_dpi(self) -> int:
        return self._dpi_spin.value()

    def get_page_cache_max_size(self) -> int:
        return self._cache_spin.value()

    def get_auto_detect_embedded_images(self) -> bool:
        return self._auto_images_check.isChecked()

    def get_auto_detect_math_fonts(self) -> bool:
        return self._auto_math_check.isChecked()

    # =========================================================================
    # ISettingsDialogView — Setters
    # =========================================================================

    def set_render_format(self, value: Literal["png", "jpeg"]) -> None:
        index = self._format_combo.findText(value)
        if index >= 0:
            self._format_combo.setCurrentIndex(index)

    def set_jpeg_quality(self, value: int) -> None:
        self._jpeg_quality_spin.setValue(value)

    def set_default_dpi(self, value: int) -> None:
        self._dpi_spin.setValue(value)

    def set_page_cache_max_size(self, value: int) -> None:
        self._cache_spin.setValue(value)

    def set_auto_detect_embedded_images(self, value: bool) -> None:
        self._auto_images_check.setChecked(value)

    def set_auto_detect_math_fonts(self, value: bool) -> None:
        self._auto_math_check.setChecked(value)

    # =========================================================================
    # ISettingsDialogView — Callback registration
    # =========================================================================

    def set_on_reset_defaults(self, cb: Callable[[], None]) -> None:
        self._on_reset_defaults = cb

    # =========================================================================
    # ISettingsDialogView — Lifecycle
    # =========================================================================

    def exec_dialog(self) -> bool:
        """モーダルダイアログを表示し、OK なら True / Cancel なら False を返す。"""
        return self.exec() == QDialog.DialogCode.Accepted

    # =========================================================================
    # Internal handlers
    # =========================================================================

    def _handle_reset(self) -> None:
        """Reset to Defaults ボタンの押下を Presenter に委譲する。"""
        if self._on_reset_defaults:
            self._on_reset_defaults()

    def _update_jpeg_quality_state(self) -> None:
        """Image Format の選択に応じて JPEG Quality SpinBox を有効/無効化する。

        PNG 選択時は Quality を disabled にするが値はリセットしない。
        PNG → JPEG 切替時に前回の quality 値がそのまま残る。
        """
        is_jpeg = self._format_combo.currentText() == "jpeg"
        self._jpeg_quality_spin.setEnabled(is_jpeg)
