"""設定ダイアログの PySide6 実装。

ISettingsDialogView Protocol を満たすモーダル QDialog。
OK / Cancel で一括適用し、「Reset to Defaults」でデフォルト復帰する。

4 タブ構成:
- Rendering: Image Format, JPEG Quality, Default DPI, Page Cache Size
- Detection: Auto-detect embedded images, Auto-detect math fonts
- AI Models: Default Model, Available Models (Fetch), Output Language,
             System Prompt Translation
- Export: Export folder and Markdown section toggles
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
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pdf_epub_reader.dto import SettingsDialogTexts
from pdf_epub_reader.utils.config import (
    CACHE_TTL_MAX,
    CACHE_TTL_MIN,
    DEFAULT_UI_LANGUAGE,
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

    def __init__(
        self,
        parent: QWidget | None = None,
        ui_language: str = DEFAULT_UI_LANGUAGE,
    ) -> None:
        super().__init__(parent)
        self._texts: SettingsDialogTexts | None = None
        self.setWindowTitle("")
        self.setMinimumWidth(400)

        self._on_reset_defaults: Callable[[], None] | None = None
        self._on_fetch_models_requested: Callable[[], None] | None = None

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
        self._image_format_label = QLabel("")
        rendering_layout.addRow(
            self._image_format_label,
            self._format_combo,
        )

        self._jpeg_quality_spin = QSpinBox()
        self._jpeg_quality_spin.setRange(JPEG_QUALITY_MIN, JPEG_QUALITY_MAX)
        self._jpeg_quality_label = QLabel("")
        rendering_layout.addRow(
            self._jpeg_quality_label,
            self._jpeg_quality_spin,
        )

        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(DPI_MIN, DPI_MAX)
        self._dpi_spin.setSingleStep(12)
        self._default_dpi_label = QLabel("")
        rendering_layout.addRow(
            self._default_dpi_label,
            self._dpi_spin,
        )

        self._cache_spin = QSpinBox()
        self._cache_spin.setRange(PAGE_CACHE_MIN, PAGE_CACHE_MAX)
        self._page_cache_size_label = QLabel("")
        rendering_layout.addRow(
            self._page_cache_size_label,
            self._cache_spin,
        )

        self._hq_downscale_check = QCheckBox("")
        rendering_layout.addRow(self._hq_downscale_check)

        self._tabs.addTab(rendering_tab, "")

        # --- Detection タブ ---
        detection_tab = QWidget()
        detection_layout = QVBoxLayout(detection_tab)

        self._auto_images_check = QCheckBox("")
        detection_layout.addWidget(self._auto_images_check)

        self._auto_math_check = QCheckBox("")
        detection_layout.addWidget(self._auto_math_check)

        detection_layout.addStretch()
        self._tabs.addTab(detection_tab, "")

        # --- AI Models タブ ---
        ai_tab = QWidget()
        ai_layout = QFormLayout(ai_tab)

        # デフォルトモデル
        self._default_model_combo = QComboBox()
        self._default_model_combo.setEditable(True)
        self._default_model_label = QLabel("")
        ai_layout.addRow(
            self._default_model_label,
            self._default_model_combo,
        )

        # 利用可能モデル一覧 (チェックボックス付きリスト + Fetch ボタン)
        self._available_models_label = QLabel("")
        ai_layout.addRow(self._available_models_label)

        self._models_list = QListWidget()
        self._models_list.setMinimumHeight(120)
        ai_layout.addRow(self._models_list)

        fetch_row = QHBoxLayout()
        self._fetch_button = QPushButton("")
        self._fetch_button.clicked.connect(self._handle_fetch_models)
        fetch_row.addWidget(self._fetch_button)
        self._fetch_status_label = QLabel("")
        fetch_row.addWidget(self._fetch_status_label)
        fetch_row.addStretch()
        ai_layout.addRow(fetch_row)

        # 出力言語
        self._output_language_edit = QLineEdit()
        self._output_language_label = QLabel("")
        ai_layout.addRow(
            self._output_language_label,
            self._output_language_edit,
        )

        # 翻訳モード用システムプロンプト
        self._system_prompt_edit = QTextEdit()
        self._system_prompt_edit.setMinimumHeight(80)
        self._system_prompt_edit.setAcceptRichText(False)
        self._translation_prompt_label = QLabel("")
        ai_layout.addRow(
            self._translation_prompt_label,
            self._system_prompt_edit,
        )

        # Context Cache TTL
        self._cache_ttl_spin = QSpinBox()
        self._cache_ttl_spin.setRange(CACHE_TTL_MIN, CACHE_TTL_MAX)
        self._cache_ttl_label = QLabel("")
        ai_layout.addRow(
            self._cache_ttl_label,
            self._cache_ttl_spin,
        )

        self._tabs.addTab(ai_tab, "")

        # --- Export タブ ---
        export_tab = QWidget()
        export_layout = QFormLayout(export_tab)

        self._export_folder_label = QLabel("")
        self._export_folder_edit = QLineEdit()
        self._export_browse_button = QPushButton("")
        self._export_browse_button.clicked.connect(
            self._handle_browse_export_folder
        )
        export_folder_row = QHBoxLayout()
        export_folder_row.addWidget(self._export_folder_edit)
        export_folder_row.addWidget(self._export_browse_button)
        export_layout.addRow(self._export_folder_label, export_folder_row)

        self._export_include_explanation_check = QCheckBox("")
        export_layout.addRow(self._export_include_explanation_check)

        self._export_include_selection_list_check = QCheckBox("")
        export_layout.addRow(self._export_include_selection_list_check)

        self._export_include_raw_response_check = QCheckBox("")
        export_layout.addRow(self._export_include_raw_response_check)

        self._export_include_document_metadata_check = QCheckBox("")
        export_layout.addRow(self._export_include_document_metadata_check)

        self._export_include_usage_metrics_check = QCheckBox("")
        export_layout.addRow(self._export_include_usage_metrics_check)

        self._export_include_yaml_frontmatter_check = QCheckBox("")
        export_layout.addRow(self._export_include_yaml_frontmatter_check)

        self._tabs.addTab(export_tab, "")

        # --- ボタン行 ---
        button_layout = QHBoxLayout()

        self._reset_button = QPushButton("")
        self._reset_button.clicked.connect(self._handle_reset)
        button_layout.addWidget(self._reset_button)

        button_layout.addStretch()

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        button_layout.addWidget(self._button_box)

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

    def get_high_quality_downscale(self) -> bool:
        return self._hq_downscale_check.isChecked()

    # --- Phase 6: AI Models タブ Getters ---

    def get_gemini_model_name(self) -> str:
        return self._default_model_combo.currentText()

    def get_selected_models(self) -> list[str]:
        """チェック済みモデルの model_id リストを返す。"""
        selected: list[str] = []
        for i in range(self._models_list.count()):
            item = self._models_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                # data に model_id を保存している
                model_id = item.data(Qt.ItemDataRole.UserRole)
                if model_id:
                    selected.append(model_id)
        return selected

    def get_output_language(self) -> str:
        return self._output_language_edit.text()

    def get_system_prompt_translation(self) -> str:
        return self._system_prompt_edit.toPlainText()

    def get_cache_ttl_minutes(self) -> int:
        return self._cache_ttl_spin.value()

    # --- Phase 8: Export タブ Getters ---

    def get_export_folder(self) -> str:
        return self._export_folder_edit.text()

    def get_export_include_explanation(self) -> bool:
        return self._export_include_explanation_check.isChecked()

    def get_export_include_selection_list(self) -> bool:
        return self._export_include_selection_list_check.isChecked()

    def get_export_include_raw_response(self) -> bool:
        return self._export_include_raw_response_check.isChecked()

    def get_export_include_document_metadata(self) -> bool:
        return self._export_include_document_metadata_check.isChecked()

    def get_export_include_usage_metrics(self) -> bool:
        return self._export_include_usage_metrics_check.isChecked()

    def get_export_include_yaml_frontmatter(self) -> bool:
        return self._export_include_yaml_frontmatter_check.isChecked()

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

    def set_high_quality_downscale(self, value: bool) -> None:
        self._hq_downscale_check.setChecked(value)

    # --- Phase 6: AI Models タブ Setters ---

    def set_gemini_model_name(self, value: str) -> None:
        index = self._default_model_combo.findText(value)
        if index >= 0:
            self._default_model_combo.setCurrentIndex(index)
        else:
            self._default_model_combo.setEditText(value)

    def set_selected_models(self, value: list[str]) -> None:
        """既に一覧にあるモデルのうち value に含まれるものをチェックする。

        一覧にないモデルはチェックボックス付きアイテムとして追加する。
        """
        # 既存アイテムのチェック状態をリセット
        existing_ids: set[str] = set()
        for i in range(self._models_list.count()):
            item = self._models_list.item(i)
            if item:
                model_id = item.data(Qt.ItemDataRole.UserRole)
                existing_ids.add(model_id)
                if model_id in value:
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)
        # 一覧にないモデルを追加
        for model_id in value:
            if model_id not in existing_ids:
                item = QListWidgetItem(model_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, model_id)
                self._models_list.addItem(item)
        # Default Model コンボも selected_models で更新
        self._sync_default_model_combo()

    def set_output_language(self, value: str) -> None:
        self._output_language_edit.setText(value)

    def set_system_prompt_translation(self, value: str) -> None:
        self._system_prompt_edit.setPlainText(value)

    def set_cache_ttl_minutes(self, value: int) -> None:
        self._cache_ttl_spin.setValue(value)

    # --- Phase 8: Export タブ Setters ---

    def set_export_folder(self, value: str) -> None:
        self._export_folder_edit.setText(value)

    def set_export_include_explanation(self, value: bool) -> None:
        self._export_include_explanation_check.setChecked(value)

    def set_export_include_selection_list(self, value: bool) -> None:
        self._export_include_selection_list_check.setChecked(value)

    def set_export_include_raw_response(self, value: bool) -> None:
        self._export_include_raw_response_check.setChecked(value)

    def set_export_include_document_metadata(self, value: bool) -> None:
        self._export_include_document_metadata_check.setChecked(value)

    def set_export_include_usage_metrics(self, value: bool) -> None:
        self._export_include_usage_metrics_check.setChecked(value)

    def set_export_include_yaml_frontmatter(self, value: bool) -> None:
        self._export_include_yaml_frontmatter_check.setChecked(value)

    def set_available_models_for_selection(
        self, models: list[tuple[str, str]]
    ) -> None:
        """Fetch で取得したモデル一覧をリストに設定する。

        既存のチェック状態を保持したまま一覧を置き換える。
        """
        # 現在チェック済みの model_id を記憶
        checked: set[str] = set()
        for i in range(self._models_list.count()):
            item = self._models_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked.add(item.data(Qt.ItemDataRole.UserRole))

        self._models_list.clear()
        for model_id, display_name in models:
            item = QListWidgetItem(f"{display_name}  ({model_id})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if model_id in checked
                else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, model_id)
            self._models_list.addItem(item)

        self._sync_default_model_combo()

    def set_fetch_models_loading(self, loading: bool) -> None:
        self._fetch_button.setEnabled(not loading)
        self._fetch_status_label.setText(
            self._texts.fetch_models_loading_text
            if loading and self._texts is not None
            else ""
        )

    def show_fetch_models_error(self, message: str) -> None:
        self._fetch_status_label.setText(message)

    # =========================================================================
    # ISettingsDialogView — Callback registration
    # =========================================================================

    def set_on_reset_defaults(self, cb: Callable[[], None]) -> None:
        self._on_reset_defaults = cb

    def set_on_fetch_models_requested(self, cb: Callable[[], None]) -> None:
        self._on_fetch_models_requested = cb

    # =========================================================================
    # ISettingsDialogView — Lifecycle
    # =========================================================================

    def exec_dialog(self) -> bool:
        """モーダルダイアログを表示し、OK なら True / Cancel なら False を返す。"""
        return self.exec() == QDialog.DialogCode.Accepted

    def apply_ui_texts(self, texts: SettingsDialogTexts) -> None:
        self._texts = texts
        self.setWindowTitle(texts.window_title)
        self._image_format_label.setText(texts.image_format_label)
        self._jpeg_quality_label.setText(texts.jpeg_quality_label)
        self._default_dpi_label.setText(texts.default_dpi_label)
        self._page_cache_size_label.setText(texts.page_cache_size_label)
        self._hq_downscale_check.setText(texts.high_quality_downscale_text)
        self._tabs.setTabText(0, texts.rendering_tab_text)
        self._auto_images_check.setText(texts.auto_detect_images_text)
        self._auto_math_check.setText(texts.auto_detect_math_text)
        self._tabs.setTabText(1, texts.detection_tab_text)
        self._default_model_label.setText(texts.default_model_label)
        self._available_models_label.setText(texts.available_models_label)
        self._fetch_button.setText(texts.fetch_models_button_text)
        self._output_language_label.setText(texts.output_language_label)
        self._translation_prompt_label.setText(texts.translation_prompt_label)
        self._cache_ttl_label.setText(texts.cache_ttl_label)
        self._cache_ttl_spin.setSuffix(texts.minutes_suffix)
        self._tabs.setTabText(2, texts.ai_tab_text)
        self._export_folder_label.setText(texts.export_folder_label)
        self._export_browse_button.setText(texts.export_browse_button_text)
        self._export_include_explanation_check.setText(
            texts.export_include_explanation_text
        )
        self._export_include_selection_list_check.setText(
            texts.export_include_selection_list_text
        )
        self._export_include_raw_response_check.setText(
            texts.export_include_raw_response_text
        )
        self._export_include_document_metadata_check.setText(
            texts.export_include_document_metadata_text
        )
        self._export_include_usage_metrics_check.setText(
            texts.export_include_usage_metrics_text
        )
        self._export_include_yaml_frontmatter_check.setText(
            texts.export_include_yaml_frontmatter_text
        )
        self._tabs.setTabText(3, texts.export_tab_text)
        self._reset_button.setText(texts.reset_defaults_button_text)
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setText(
            texts.ok_button_text
        )
        self._button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(
            texts.cancel_button_text
        )

    # =========================================================================
    # Internal handlers
    # =========================================================================

    def _handle_reset(self) -> None:
        """Reset to Defaults ボタンの押下を Presenter に委譲する。"""
        if self._on_reset_defaults:
            self._on_reset_defaults()

    def _handle_fetch_models(self) -> None:
        """Fetch Models ボタンの押下を Presenter に委譲する。"""
        if self._on_fetch_models_requested:
            self._on_fetch_models_requested()

    def _handle_browse_export_folder(self) -> None:
        """Export Folder の参照ボタンでディレクトリピッカーを開く。"""
        selected = QFileDialog.getExistingDirectory(
            self,
            self._texts.export_folder_label if self._texts is not None else "",
            self._export_folder_edit.text(),
        )
        if selected:
            self._export_folder_edit.setText(selected)

    def _sync_default_model_combo(self) -> None:
        """モデルリストの内容を Default Model コンボに同期する。"""
        current = self._default_model_combo.currentText()
        self._default_model_combo.clear()
        for i in range(self._models_list.count()):
            item = self._models_list.item(i)
            if item:
                model_id = item.data(Qt.ItemDataRole.UserRole)
                self._default_model_combo.addItem(model_id)
        # 元の選択を復元
        idx = self._default_model_combo.findText(current)
        if idx >= 0:
            self._default_model_combo.setCurrentIndex(idx)
        elif current:
            self._default_model_combo.setEditText(current)

    def _update_jpeg_quality_state(self) -> None:
        """Image Format の選択に応じて JPEG Quality SpinBox を有効/無効化する。

        PNG 選択時は Quality を disabled にするが値はリセットしない。
        PNG → JPEG 切替時に前回の quality 値がそのまま残る。
        """
        is_jpeg = self._format_combo.currentText() == "jpeg"
        self._jpeg_quality_spin.setEnabled(is_jpeg)

