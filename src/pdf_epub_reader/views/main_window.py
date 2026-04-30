"""メインウィンドウの PySide6 実装。

IMainView Protocol を満たし、ドキュメント表示・ファイル操作・ズーム・
ステータスバーなどメインウィンドウ全体の UI を担当する。
ビジネスロジックは持たず、操作はすべてコールバック経由で Presenter に伝達する。
"""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import cast

from PIL import Image
from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QRubberBand,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from pdf_epub_reader.dto import (
    MainWindowTexts,
    PageData,
    RectCoords,
    SelectionSlot,
    SelectionSnapshot,
    ToCEntry,
)
from pdf_epub_reader.utils.config import (
    BOOKMARK_PANEL_WIDTH,
    DEFAULT_UI_LANGUAGE,
    DEFAULT_DPI,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MAX_RECENT_FILES,
    PAGE_GAP,
    SPLITTER_RATIO,
    VIEWPORT_BUFFER_PAGES,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_STEP,
)
from pdf_epub_reader.views.bookmark_panel import BookmarkPanelView


class MainWindow(QMainWindow):
    """IMainView Protocol を満たすメインウィンドウ実装。

    外部からしおりパネルと SidePanelView をインジェクトし、
    QSplitter で 3 ペインを横並びに配置する。
    """

    def __init__(
        self,
        side_panel: QWidget,
        bookmark_panel: BookmarkPanelView | None = None,
        ui_language: str = DEFAULT_UI_LANGUAGE,
    ) -> None:
        super().__init__()
        self._ui_texts: MainWindowTexts | None = None
        self.setWindowTitle("")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        # --- コールバック保持 ---
        self._on_file_open_requested: Callable[[], None] | None = None
        self._on_file_dropped: Callable[[str], None] | None = None
        self._on_recent_file_selected: Callable[[str], None] | None = None
        self._on_selection_requested: (
            Callable[[int, RectCoords, bool], None] | None
        ) = None
        self._on_selection_clear_requested: Callable[[], None] | None = None
        self._on_zoom_changed: Callable[[float], None] | None = None
        self._on_bookmark_selected: Callable[[int], None] | None = None
        self._on_cache_management_requested: Callable[[], None] | None = None
        self._on_settings_requested: Callable[[], None] | None = None
        self._on_language_settings_requested: Callable[[], None] | None = None
        self._bookmark_has_entries = False
        self._status_is_default = True
        self._window_title_is_default = True

        # Phase 5 で app.py から注入されるまでの互換用デフォルト。
        self._bookmark_panel = bookmark_panel or BookmarkPanelView(
            ui_language=ui_language
        )

        # --- QSettings で最近のファイルを永続化 ---
        self._settings = QSettings("gem-read", "gem-read")

        # --- ドキュメント表示 ---
        self._doc_view = _DocumentGraphicsView()
        # ページ番号連携用
        self._doc_view._on_visible_page_changed = self._on_visible_page_changed
        # 左ペインへのファイルドロップを MainWindow の共通ハンドラに接続する。
        self._doc_view._on_file_dropped = self._handle_file_drop

        # ドキュメントペインにページ/ズームのオーバーレイを重ねるコンテナ
        doc_pane = QWidget()
        doc_pane_layout = QVBoxLayout(doc_pane)
        doc_pane_layout.setContentsMargins(0, 0, 0, 0)
        doc_pane_layout.setSpacing(0)
        doc_pane_layout.addWidget(self._doc_view)

        # ページ番号・ズーム操作のオーバーレイ（右下に浮かせる）
        self._overlay = _DocOverlayWidget(doc_pane)
        self._overlay.page_spinbox.valueChanged.connect(
            self._handle_page_spinbox_changed
        )
        self._overlay.zoom_spinbox.valueChanged.connect(
            self._handle_zoom_spinbox_changed
        )
        # 便利なエイリアス
        self._page_spinbox = self._overlay.page_spinbox
        self._total_pages_label = self._overlay.total_pages_label
        self._zoom_spinbox = self._overlay.zoom_spinbox

        # --- スプリッター ---
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._bookmark_panel)
        self._splitter.addWidget(doc_pane)
        self._splitter.addWidget(side_panel)
        self._splitter.setCollapsible(0, True)
        self._splitter.setCollapsible(1, False)
        self._splitter.setSizes(
            [
                0,
                DEFAULT_WINDOW_WIDTH * SPLITTER_RATIO[0] // 100,
                DEFAULT_WINDOW_WIDTH * SPLITTER_RATIO[1] // 100,
            ]
        )
        self.setCentralWidget(self._splitter)

        # --- メニューバー ---
        self._build_menu_bar()

        # --- ステータスバー ---
        self._build_status_bar()

        # --- ドラッグ&ドロップ ---
        self.setAcceptDrops(True)

        # --- キーバインド ---
        # Ctrl+H: 現在表示中のページの高さをビューポートにフィットするズーム。
        fit_height_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        fit_height_shortcut.activated.connect(
            self._doc_view.fit_to_page_height
        )

        self._clear_selection_shortcut = QShortcut(
            QKeySequence("Esc"), self
        )
        self._clear_selection_shortcut.activated.connect(
            self._handle_selection_clear_requested
        )

    # =========================================================================
    # メニューバー構築
    # =========================================================================

    def _build_menu_bar(self) -> None:
        """ファイル・表示・編集・キャッシュメニューを構築する。"""
        menubar = self.menuBar()
        self._file_menu = menubar.addMenu("")

        # 開く
        self._open_action = QAction(self)
        self._open_action.setShortcut("Ctrl+O")
        self._open_action.triggered.connect(self._handle_open_action)
        self._file_menu.addAction(self._open_action)

        # 最近開いたファイル
        self._recent_files_menu = QMenu(self)
        self._file_menu.addMenu(self._recent_files_menu)
        self._rebuild_recent_menu()

        self._file_menu.addSeparator()

        # 終了
        self._quit_action = QAction(self)
        self._quit_action.triggered.connect(self.close)
        self._file_menu.addAction(self._quit_action)

        # --- 表示メニュー ---
        self._view_menu = menubar.addMenu("")

        self._bookmark_toggle_action = QAction(self)
        self._bookmark_toggle_action.setShortcut(QKeySequence("Ctrl+B"))
        self._bookmark_toggle_action.setCheckable(True)
        self._bookmark_toggle_action.toggled.connect(
            self._handle_toggle_bookmark
        )
        self._view_menu.addAction(self._bookmark_toggle_action)

        # --- 編集メニュー ---
        self._edit_menu = menubar.addMenu("")

        self._preferences_action = QAction(self)
        self._preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        self._preferences_action.triggered.connect(self._handle_settings_requested)
        self._edit_menu.addAction(self._preferences_action)

        # --- キャッシュメニュー ---
        self._cache_menu = menubar.addMenu("")

        self._cache_mgmt_action = QAction(self)
        self._cache_mgmt_action.setShortcut(QKeySequence("Ctrl+Shift+G"))
        self._cache_mgmt_action.triggered.connect(
            self._handle_cache_management_requested
        )
        self._cache_menu.addAction(self._cache_mgmt_action)

        # --- 言語メニュー ---
        self._language_menu = menubar.addMenu("")

        self._language_settings_action = QAction(self)
        self._language_settings_action.triggered.connect(
            self._handle_language_settings_requested
        )
        self._language_menu.addAction(self._language_settings_action)

    # =========================================================================
    # ステータスバー構築
    # =========================================================================

    def _build_status_bar(self) -> None:
        """ステータスメッセージのみ配置する。ページ/ズームはドキュメントペイン内。"""
        status_bar: QStatusBar = self.statusBar()

        self._status_label = QLabel("")
        status_bar.addWidget(self._status_label, stretch=1)
        self._set_default_status_text()

    # =========================================================================
    # IMainView — Display commands
    # =========================================================================

    def display_pages(self, pages: list[PageData]) -> None:
        """全ページ分のプレースホルダーを配置する。

        PageData.image_data が空の場合はプレースホルダー表示となり、
        実画像は後から update_pages() で供給される。
        """
        self._doc_view.setup_pages(pages)

        # ページスピンボックスの範囲を更新する。
        total = len(pages)
        self._page_spinbox.blockSignals(True)
        self._page_spinbox.setRange(1, max(total, 1))
        self._page_spinbox.setValue(1)
        self._page_spinbox.blockSignals(False)
        self._total_pages_label.setText(f"/ {total}")

    def update_pages(self, pages: list[PageData]) -> None:
        """遅延レンダリング結果を View に供給してプレースホルダーを実画像に差し替える。"""
        self._doc_view.update_page_images(pages)

    def scroll_to_page(self, page_number: int) -> None:
        """指定ページが見えるようにスクロールする。"""
        self._doc_view.scroll_to(page_number)

    def display_toc(self, entries: list[ToCEntry]) -> None:
        """しおりパネルの目次データを更新し、表示状態を同期する。"""
        self._bookmark_panel.set_toc(entries)
        self._bookmark_has_entries = bool(entries)

        self._bookmark_toggle_action.blockSignals(True)
        self._bookmark_toggle_action.setChecked(self._bookmark_has_entries)
        self._bookmark_toggle_action.blockSignals(False)
        self._set_bookmark_panel_visible(self._bookmark_has_entries)

    def set_zoom_level(self, level: float) -> None:
        """ズームスピンボックスの値を更新し、ビュー変換で拡縮する。

        DPI は固定のまま、QGraphicsView の setTransform で拡縮する。
        縮小時 (zoom < 1.0) かつ high_quality_downscale 有効時は、
        可視ページの画像を Pillow LANCZOS でリサイズして差し替える。
        """
        self._zoom_spinbox.blockSignals(True)
        self._zoom_spinbox.setValue(int(level * 100))
        self._zoom_spinbox.blockSignals(False)
        # _DocumentGraphicsView のズーム状態を同期する。
        # DPI は固定のため _current_dpi は変更しない。
        self._doc_view._zoom_level = level
        self._doc_view.resetTransform()
        self._doc_view.scale(level, level)
        # 縮小時は LANCZOS リサイズで画像を差し替える。
        self._doc_view._apply_zoom_resize(level)
        self._doc_view.refresh_selection_overlays()

    def show_selection_highlight(
        self, page_number: int, rect: RectCoords
    ) -> None:
        """指定ページの指定矩形に半透明のハイライトを重ねる。"""
        self._doc_view.add_highlight(page_number, rect)

    def show_selection_highlights(
        self, snapshot: SelectionSnapshot
    ) -> None:
        """複数選択スナップショットを描画に反映する。

        Phase 2 の複数オーバーレイ化までは暫定的に 0 件ならクリア、
        1 件以上なら末尾スロットのみを単一ハイライトとして表示する。
        """
        self._doc_view.set_selection_snapshot(snapshot)

    def clear_selection(self) -> None:
        """選択ハイライトを除去する。"""
        self._doc_view.clear_highlight()

    def set_window_title(self, title: str) -> None:
        """ウィンドウタイトルを更新する。"""
        self._window_title_is_default = False
        self.setWindowTitle(title)

    def show_status_message(self, message: str) -> None:
        """ステータスバーのメッセージを更新する。"""
        self._status_is_default = False
        self._status_label.setText(message)

    def update_recent_files(self, files: list[str]) -> None:
        """最近のファイルリストを差し替えてメニューを再構築する。"""
        self._settings.setValue("recent_files", files[:MAX_RECENT_FILES])
        self._rebuild_recent_menu()

    def get_device_pixel_ratio(self) -> float:
        """画面のデバイスピクセル比を返す。

        Presenter がレンダリング DPI (_render_dpi = _base_dpi × dpr) を
        算出するために使用する。OS のスケーリング設定を Qt が反映した値を返す。
        """
        return self.devicePixelRatio()

    def show_error_dialog(self, title: str, message: str) -> None:
        """重大エラー時にモーダルダイアログを表示する。"""
        QMessageBox.critical(self, title, message)

    def show_password_dialog(self, title: str, message: str) -> str | None:
        """パスワード保護文書の入力ダイアログを表示する。"""
        password, accepted = QInputDialog.getText(
            self,
            title,
            message,
            echo=QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return None
        return password

    def show_plotly_spec_picker(
        self,
        title: str,
        label: str,
        items: list[str],
        cancel_button_text: str,
    ) -> int | None:
        """複数 Plotly 可視化候補から表示対象を選択する。"""
        dialog = QInputDialog(self)
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.setComboBoxEditable(False)
        dialog.setComboBoxItems(items)
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.setOkButtonText(self.tr("OK"))
        dialog.setCancelButtonText(cancel_button_text)

        if dialog.exec() != QInputDialog.DialogCode.Accepted:
            return None
        return dialog.comboBox().currentIndex()

    def set_high_quality_downscale(self, enabled: bool) -> None:
        """高品質縮小 (Pillow LANCZOS) の有効/無効を切り替え、即反映する。"""
        self._doc_view._high_quality_downscale = enabled
        # 現在縮小中なら直ちに画像を差し替えて反映する。
        if self._doc_view._zoom_level < 1.0:
            self._doc_view._apply_zoom_resize(self._doc_view._zoom_level)

    def apply_ui_texts(self, texts: MainWindowTexts) -> None:
        """Presenter が解決済みの UI 文言束を適用する。"""
        self._ui_texts = texts
        if self._window_title_is_default:
            self.setWindowTitle(texts.window_title)
        self._file_menu.setTitle(texts.file_menu_title)
        self._open_action.setText(texts.open_action_text)
        self._recent_files_menu.setTitle(texts.recent_menu_title)
        self._quit_action.setText(texts.quit_action_text)
        self._view_menu.setTitle(texts.view_menu_title)
        self._bookmark_toggle_action.setText(texts.bookmark_toggle_text)
        self._edit_menu.setTitle(texts.edit_menu_title)
        self._preferences_action.setText(texts.preferences_action_text)
        self._cache_menu.setTitle(texts.cache_menu_title)
        self._cache_mgmt_action.setText(texts.cache_management_action_text)
        self._language_menu.setTitle(texts.language_menu_title)
        self._language_settings_action.setText(texts.language_settings_action_text)
        self._bookmark_panel.apply_ui_texts(texts.bookmark_panel)
        self._overlay.set_page_label_text(texts.overlay_page_label)
        if self._status_is_default:
            self._set_default_status_text()
        self._rebuild_recent_menu()

    # =========================================================================
    # IMainView — Callback registration
    # =========================================================================

    def set_on_file_open_requested(self, cb: Callable[[], None]) -> None:
        self._on_file_open_requested = cb

    def set_on_file_dropped(self, cb: Callable[[str], None]) -> None:
        self._on_file_dropped = cb

    def set_on_recent_file_selected(
        self, cb: Callable[[str], None]
    ) -> None:
        self._on_recent_file_selected = cb

    def set_on_area_selected(
        self, cb: Callable[[int, RectCoords], None]
    ) -> None:
        self._doc_view._on_area_selected = cb

    def set_on_selection_requested(
        self, cb: Callable[[int, RectCoords, bool], None]
    ) -> None:
        self._on_selection_requested = cb
        self._doc_view._on_selection_requested = cb

    def set_on_selection_clear_requested(
        self, cb: Callable[[], None]
    ) -> None:
        self._on_selection_clear_requested = cb
        self._doc_view._on_selection_clear_requested = cb

    def set_on_zoom_changed(self, cb: Callable[[float], None]) -> None:
        self._on_zoom_changed = cb
        self._doc_view._on_zoom_changed = cb

    def set_on_bookmark_selected(
        self, cb: Callable[[int], None]
    ) -> None:
        self._on_bookmark_selected = cb
        self._bookmark_panel.set_on_entry_selected(cb)

    def set_on_pages_needed(
        self, cb: Callable[[list[int]], None]
    ) -> None:
        self._doc_view._on_pages_needed = cb

    def set_on_cache_management_requested(
        self, cb: Callable[[], None]
    ) -> None:
        self._on_cache_management_requested = cb

    def set_on_settings_requested(
        self, cb: Callable[[], None]
    ) -> None:
        self._on_settings_requested = cb

    def set_on_language_settings_requested(
        self, cb: Callable[[], None]
    ) -> None:
        self._on_language_settings_requested = cb

    def get_current_page(self) -> int:
        """現在ビューポート上部に最も近いページの 0-indexed 番号を返す。

        設定ダイアログで DPI 変更後のスクロール位置復元に使用する。
        """
        return self._doc_view.get_visible_page()

    # =========================================================================
    # Internal handlers
    # =========================================================================

    def _handle_open_action(self) -> None:
        """ファイル選択ダイアログを開き、選択されたパスをコールバックに渡す。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._ui_texts.open_dialog_title if self._ui_texts else "",
            "",
            self._ui_texts.open_dialog_filter if self._ui_texts else "",
        )
        if file_path and self._on_file_dropped:
            # open と drop を統合し、同一のコールバックでパスを渡す。
            self._add_to_recent(file_path)
            self._on_file_dropped(file_path)

    def _handle_settings_requested(self) -> None:
        """Edit > Preferences / Ctrl+, ハンドラ。コールバック経由で Presenter に通知する。"""
        if self._on_settings_requested:
            self._on_settings_requested()

    def _handle_language_settings_requested(self) -> None:
        """言語メニュー押下時にコールバック経由で Presenter に通知する。"""
        if self._on_language_settings_requested:
            self._on_language_settings_requested()

    def _handle_cache_management_requested(self) -> None:
        """キャッシュ(&C) > キャッシュ管理 / Ctrl+Alt+G ハンドラ。"""
        if self._on_cache_management_requested:
            self._on_cache_management_requested()

    def _handle_selection_clear_requested(self) -> None:
        """Esc による全選択クリア要求を Presenter に通知する。"""
        if self._on_selection_clear_requested:
            self._on_selection_clear_requested()

    def _handle_toggle_bookmark(self, checked: bool) -> None:
        """しおりパネルの表示/非表示を切り替える。"""
        if checked and not self._bookmark_has_entries:
            self._bookmark_toggle_action.blockSignals(True)
            self._bookmark_toggle_action.setChecked(False)
            self._bookmark_toggle_action.blockSignals(False)
            self._set_bookmark_panel_visible(False)
            return

        self._set_bookmark_panel_visible(checked)

    def _handle_page_spinbox_changed(self, value: int) -> None:
        """ページスピンボックスの値変更でスクロールを実行する。"""
        # スピンボックスは 1-indexed、scroll_to は 0-indexed。
        self._doc_view.scroll_to(value - 1)

    def _handle_zoom_spinbox_changed(self, value: int) -> None:
        """ズームスピンボックスの値変更をコールバックに伝達する。"""
        if self._on_zoom_changed:
            self._on_zoom_changed(value / 100.0)

    def _on_visible_page_changed(self, page_number: int) -> None:
        """ドキュメント表示から最も上に見えているページ番号の通知を受け取る。"""
        self._page_spinbox.blockSignals(True)
        self._page_spinbox.setValue(page_number + 1)  # 0-indexed → 1-indexed
        self._page_spinbox.blockSignals(False)

    def _set_bookmark_panel_visible(self, visible: bool) -> None:
        """ドキュメント/AI パネル比率を保ったまましおり幅を調整する。"""
        sizes = self._splitter.sizes()
        if len(sizes) != 3:
            return

        _, doc_size, side_size = sizes
        remaining = doc_size + side_size
        if remaining <= 0:
            doc_ratio = SPLITTER_RATIO[0] / (SPLITTER_RATIO[0] + SPLITTER_RATIO[1])
        else:
            doc_ratio = doc_size / remaining

        total = sum(sizes)
        bookmark_size = min(BOOKMARK_PANEL_WIDTH, total) if visible else 0
        content_total = max(0, total - bookmark_size)
        new_doc_size = int(content_total * doc_ratio)
        new_side_size = max(0, content_total - new_doc_size)
        self._splitter.setSizes([bookmark_size, new_doc_size, new_side_size])

    # =========================================================================
    # ドラッグ&ドロップ
    # =========================================================================

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """MIME が uri-list かつ PDF/EPUB なら受け入れる。"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith((".pdf", ".epub")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """ドロップされたファイルパスをコールバックに渡す。"""
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".pdf", ".epub")):
                self._handle_file_drop(path)
                break

    def _handle_file_drop(self, path: str) -> None:
        """ファイルドロップの共通処理。MainWindow.dropEvent と _DocumentGraphicsView の両方から呼ばれる。"""
        self._add_to_recent(path)
        if self._on_file_dropped:
            self._on_file_dropped(path)

    # =========================================================================
    # 最近開いたファイル管理
    # =========================================================================

    def _add_to_recent(self, file_path: str) -> None:
        """最近のファイルリストの先頭にパスを追加し QSettings に保存する。"""
        recent = cast(list[str], self._settings.value("recent_files", []) or [])
        # 重複を削除して先頭に追加
        if file_path in recent:
            recent.remove(file_path)
        recent.insert(0, file_path)
        recent = recent[:MAX_RECENT_FILES]
        self._settings.setValue("recent_files", recent)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        """最近のファイル用サブメニューを現在のリストで再構築する。"""
        self._recent_files_menu.clear()
        recent = cast(list[str], self._settings.value("recent_files", []) or [])
        if not recent:
            no_items = QAction(
                self._ui_texts.recent_none_text if self._ui_texts else "",
                self,
            )
            no_items.setEnabled(False)
            self._recent_files_menu.addAction(no_items)
            return
        for path in recent:
            action = QAction(Path(path).name, self)
            action.setToolTip(path)
            # ラムダのクロージャ問題を回避するため、デフォルト引数で束縛する。
            action.triggered.connect(
                lambda checked=False, p=path: self._handle_recent_selected(p)
            )
            self._recent_files_menu.addAction(action)

    def _handle_recent_selected(self, path: str) -> None:
        """最近のファイル選択をコールバックに伝達する。"""
        if self._on_file_dropped:
            self._add_to_recent(path)
            self._on_file_dropped(path)

    def _set_default_status_text(self) -> None:
        self._status_is_default = True
        self._status_label.setText(
            self._ui_texts.default_status_text if self._ui_texts else ""
        )


# =============================================================================
# _DocOverlayWidget — ページ番号・ズーム操作のオーバーレイ
# =============================================================================


class _DocOverlayWidget(QWidget):
    """ドキュメントペインの右下に浮かぶページ番号・ズーム操作ウィジェット。

    親ウィジェットの resizeEvent を利用して常に右下に追従させる。
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        # 半透明の背景 + 角丸
        self.setStyleSheet(
            "background-color: rgba(40, 40, 40, 180);"
            "border-radius: 6px;"
            "color: #eee;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # ページナビゲーション
        self._page_label = QLabel("ページ:")
        self._page_label.setStyleSheet("background: transparent; color: #82b1ff;")
        layout.addWidget(self._page_label)

        self.page_spinbox = QSpinBox()
        self.page_spinbox.setMinimum(1)
        self.page_spinbox.setMaximum(1)
        layout.addWidget(self.page_spinbox)

        self.total_pages_label = QLabel("/ 0")
        self.total_pages_label.setStyleSheet("background: transparent; color: #82b1ff;")
        layout.addWidget(self.total_pages_label)

        # セパレータ
        sep = QLabel("|")
        sep.setStyleSheet("background: transparent; color: #888;")
        layout.addWidget(sep)

        # ズーム
        zoom_icon = QLabel("\U0001f50d")
        zoom_icon.setStyleSheet("background: transparent;")
        layout.addWidget(zoom_icon)

        self.zoom_spinbox = QSpinBox()
        self.zoom_spinbox.setRange(int(ZOOM_MIN * 100), int(ZOOM_MAX * 100))
        self.zoom_spinbox.setSingleStep(int(ZOOM_STEP * 100))
        self.zoom_spinbox.setSuffix("%")
        self.zoom_spinbox.setValue(100)
        layout.addWidget(self.zoom_spinbox)

        self.adjustSize()

        # 親の resizeEvent をフックして位置を追従させる。
        parent.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """親ウィジェットのリサイズに追従して右下に再配置する。"""
        from PySide6.QtCore import QEvent

        if watched is self.parent() and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(watched, event)

    def _reposition(self) -> None:
        """親ウィジェットの右下に配置する。"""
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 8
        x = parent.width() - self.width() - margin
        y = parent.height() - self.height() - margin
        self.move(max(0, x), max(0, y))

    def showEvent(self, event) -> None:  # noqa: N802
        """表示時にも位置を合わせる。"""
        super().showEvent(event)
        self._reposition()
        self.raise_()

    def set_page_label_text(self, text: str) -> None:
        self._page_label.setText(text)


# =============================================================================
# _DocumentGraphicsView — ドキュメント表示ウィジェット (MainWindow 内部クラス)
# =============================================================================


class _DocumentGraphicsView(QGraphicsView):
    """QGraphicsView ベースのドキュメント表示。MainWindow の内部に閉じる。

    プレースホルダー配置→ビューポート監視→遅延読み込み→画像差し替え
    というフローでページを表示する。外部からは MainWindow 経由でのみ操作される。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        # 縮小時のジャギーを防ぐためバイリニア補間を有効にする。
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # --- 内部状態 ---
        # ページごとの表示アイテム（プレースホルダーまたは画像）
        self._page_items: list[QGraphicsPixmapItem | QGraphicsRectItem] = []
        # 各ページのシーン上の配置矩形
        self._page_rects: list[QRectF] = []
        # 各ページの (width, height)
        self._page_sizes: list[tuple[int, int]] = []
        # 画像がセット済みのページ番号
        self._rendered_pages: set[int] = set()
        # 複数選択オーバーレイ（selection_id -> items）
        self._selection_overlays: dict[
            str,
            tuple[QGraphicsRectItem, QGraphicsRectItem, QGraphicsTextItem],
        ] = {}
        self._selection_snapshot = SelectionSnapshot()
        self._badge_font = QFont()
        self._badge_font.setPointSize(9)
        self._badge_font.setBold(True)

        # --- コールバック ---
        self._on_area_selected: (
            Callable[[int, RectCoords], None] | None
        ) = None
        self._on_selection_requested: (
            Callable[[int, RectCoords, bool], None] | None
        ) = None
        self._on_selection_clear_requested: Callable[[], None] | None = None
        self._on_zoom_changed: Callable[[float], None] | None = None
        self._on_pages_needed: Callable[[list[int]], None] | None = None
        self._on_visible_page_changed: (
            Callable[[int], None] | None
        ) = None
        self._on_file_dropped: Callable[[str], None] | None = None

        # --- DPI・ズーム ---
        self._current_dpi: int = DEFAULT_DPI
        self._zoom_level: float = 1.0

        # --- Pillow LANCZOS リサイズ ---
        # ズーム縮小時に Pillow LANCZOS でリサイズした画像を使うか。
        self._high_quality_downscale: bool = True
        # 元画像バイト列の保持 (page_number → image_data)。
        # ズーム変更時に LANCZOS リサイズの元データとして使う。
        self._original_images: dict[int, bytes] = {}

        # --- ラバーバンド選択用 ---
        self._rubber_band = QRubberBand(
            QRubberBand.Shape.Rectangle, self.viewport()
        )
        self._rubber_band_active = False
        self._drag_start = None
        self._drag_append_mode = False

        # --- ドラッグ&ドロップ（左ペイン対応） ---
        self.setAcceptDrops(True)

    # =====================================================================
    # プレースホルダー配置
    # =====================================================================

    def setup_pages(self, pages: list[PageData]) -> None:
        """全ページのプレースホルダーをシーンに配置する。

        以前のアイテムをすべてクリアし、各ページのサイズに応じて
        灰色矩形を縦に並べる。配置後にビューポート監視で初期表示分を要求する。
        """
        self._scene.clear()
        self._page_items.clear()
        self._page_rects.clear()
        self._page_sizes.clear()
        self._rendered_pages.clear()
        self._original_images.clear()
        self._selection_overlays.clear()
        self._selection_snapshot = SelectionSnapshot()

        y_offset = 0.0
        for page in pages:
            rect = QRectF(0, y_offset, page.width, page.height)
            item = self._scene.addRect(
                rect,
                QPen(QColor(200, 200, 200)),
                QBrush(QColor(224, 224, 224)),
            )
            self._page_items.append(item)
            self._page_rects.append(rect)
            self._page_sizes.append((page.width, page.height))
            y_offset += page.height + PAGE_GAP

        # シーン全体のサイズを設定。
        if pages:
            max_width = max(p.width for p in pages)
            self._scene.setSceneRect(0, 0, max_width, y_offset - PAGE_GAP)

        # 初期表示分のページ要求を発火する。
        self._check_visible_pages()

    # =====================================================================
    # 画像差し替え
    # =====================================================================

    def update_page_images(self, pages: list[PageData]) -> None:
        """レンダリング済み画像でプレースホルダーを差し替える。"""
        for page in pages:
            idx = page.page_number
            if idx < 0 or idx >= len(self._page_items):
                continue

            # 元画像を保存しておく（ズーム変更時の LANCZOS リサイズ元）。
            self._original_images[idx] = page.image_data

            # 縮小中かつ高品質ダウンスケール有効時は LANCZOS でリサイズした Pixmap を使う。
            if self._zoom_level < 1.0 and self._high_quality_downscale:
                pixmap = self._make_lanczos_pixmap(
                    page.image_data, self._zoom_level
                )
            else:
                pixmap = QPixmap()
                if not pixmap.loadFromData(page.image_data):
                    continue
                pixmap.setDevicePixelRatio(self.devicePixelRatio())

            if pixmap.isNull():
                continue

            # 既存アイテムをシーンから除去する。
            old_item = self._page_items[idx]
            self._scene.removeItem(old_item)

            # 新しい QGraphicsPixmapItem を追加する。
            pix_item = QGraphicsPixmapItem(pixmap)
            pix_item.setPos(
                self._page_rects[idx].x(), self._page_rects[idx].y()
            )
            self._scene.addItem(pix_item)
            self._page_items[idx] = pix_item
            self._rendered_pages.add(idx)

        # ビューポート外の画像を解放する。
        self._release_offscreen_pages()

    # =====================================================================
    # Pillow LANCZOS リサイズ
    # =====================================================================

    def _make_lanczos_pixmap(
        self, image_data: bytes, zoom: float
    ) -> QPixmap:
        """元画像を Pillow LANCZOS でリサイズし QPixmap を返す。

        リサイズ後の QPixmap に ``setDevicePixelRatio(dpr * zoom)`` を設定する。
        Qt はシーン上で ``1/(dpr*zoom)`` 倍に表示し、ビュー変換の ``zoom`` 倍と
        合わせて ``1/dpr`` 倍 = base_dpi 相当に帰着する。
        """
        pil_img = Image.open(io.BytesIO(image_data))
        new_w = max(1, int(pil_img.width * zoom))
        new_h = max(1, int(pil_img.height * zoom))
        resized = pil_img.resize(
            (new_w, new_h), Image.Resampling.LANCZOS
        )

        buf = io.BytesIO()
        resized.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        # 二重スケーリング回避: Qt が論理サイズを 1/(dpr*zoom) にするので、
        # ビュー変換 zoom と合成すると 1/dpr になり base_dpi 相当に帰着する。
        dpr = self.devicePixelRatio()
        pixmap.setDevicePixelRatio(dpr * zoom)
        return pixmap

    def _apply_zoom_resize(self, level: float) -> None:
        """ズーム変更時にレンダリング済みページの画像を差し替える。

        zoom < 1.0 かつ高品質ダウンスケール有効時は LANCZOS リサイズ画像に、
        それ以外は元画像に差し替える。元画像がないページはスキップする。
        """
        for idx in list(self._rendered_pages):
            original = self._original_images.get(idx)
            if original is None:
                continue

            if level < 1.0 and self._high_quality_downscale:
                pixmap = self._make_lanczos_pixmap(original, level)
            else:
                pixmap = QPixmap()
                if not pixmap.loadFromData(original):
                    continue
                pixmap.setDevicePixelRatio(self.devicePixelRatio())

            if pixmap.isNull():
                continue

            old_item = self._page_items[idx]
            self._scene.removeItem(old_item)
            pix_item = QGraphicsPixmapItem(pixmap)
            pix_item.setPos(
                self._page_rects[idx].x(), self._page_rects[idx].y()
            )
            self._scene.addItem(pix_item)
            self._page_items[idx] = pix_item

    # =====================================================================
    # ビューポート監視
    # =====================================================================

    def _check_visible_pages(self) -> None:
        """ビューポート内の可視ページを判定し、未レンダリングなら要求を発火する。"""
        if not self._page_rects:
            return

        # ビューポートのシーン座標を取得する。
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()

        visible_pages: list[int] = []
        top_page: int | None = None

        for i, page_rect in enumerate(self._page_rects):
            if page_rect.intersects(viewport_rect):
                visible_pages.append(i)
                if top_page is None:
                    top_page = i

        # 前後にバッファページを加算する。
        if visible_pages:
            low = max(0, visible_pages[0] - VIEWPORT_BUFFER_PAGES)
            high = min(
                len(self._page_rects) - 1,
                visible_pages[-1] + VIEWPORT_BUFFER_PAGES,
            )
            buffered = list(range(low, high + 1))
        else:
            buffered = []

        # 未レンダリングのページだけをフィルタする。
        needed = [p for p in buffered if p not in self._rendered_pages]

        if needed and self._on_pages_needed:
            self._on_pages_needed(needed)

        # 最も上に見えているページ番号を通知する（ステータスバー連携用）。
        if top_page is not None and self._on_visible_page_changed:
            self._on_visible_page_changed(top_page)

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        """スクロールのたびにビューポート監視を呼ぶ。"""
        super().scrollContentsBy(dx, dy)
        self._check_visible_pages()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """リサイズ時にもビューポート監視を呼ぶ。"""
        super().resizeEvent(event)
        self._check_visible_pages()
        self.refresh_selection_overlays()

    # =====================================================================
    # ビューポート外画像の解放
    # =====================================================================

    def _release_offscreen_pages(self) -> None:
        """ビューポート外の画像をプレースホルダーに差し戻してメモリを解放する。"""
        if not self._page_rects:
            return

        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()

        visible_pages: list[int] = []
        for i, page_rect in enumerate(self._page_rects):
            if page_rect.intersects(viewport_rect):
                visible_pages.append(i)

        if visible_pages:
            low = max(0, visible_pages[0] - VIEWPORT_BUFFER_PAGES)
            high = min(
                len(self._page_rects) - 1,
                visible_pages[-1] + VIEWPORT_BUFFER_PAGES,
            )
            keep = set(range(low, high + 1))
        else:
            keep = set()

        # バッファ外のレンダリング済みページをプレースホルダーに戻す。
        to_release = self._rendered_pages - keep
        for idx in to_release:
            old_item = self._page_items[idx]
            self._scene.removeItem(old_item)
            new_item = self._scene.addRect(
                self._page_rects[idx],
                QPen(QColor(200, 200, 200)),
                QBrush(QColor(224, 224, 224)),
            )
            self._page_items[idx] = new_item
            # 元画像も解放してメモリを節約する。
            self._original_images.pop(idx, None)
        self._rendered_pages -= to_release

    # =====================================================================
    # ドラッグ&ドロップ（左ペインでのファイルオープン対応）
    # =====================================================================

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """MIME が uri-list かつ PDF/EPUB なら受け入れる。"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith((".pdf", ".epub")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        """ドラッグ中も継続的に受け入れる。

        QGraphicsView のデフォルト dragMoveEvent はシーン内アイテムへの
        転送を試み、受理されなければ ignore() してしまう。
        これにより dropEvent が発火しなくなるため、明示的に accept する。
        """
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """ドロップされたファイルパスを MainWindow 経由でコールバックに渡す。"""
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".pdf", ".epub")):
                if self._on_file_dropped:
                    self._on_file_dropped(path)
                break

    # =====================================================================
    # 矩形選択 (Rubber Band)
    # =====================================================================

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """左ボタン押下でラバーバンド選択を開始する。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._rubber_band_active = True
            self._drag_start = event.position().toPoint()
            self._drag_append_mode = bool(
                event.modifiers() & Qt.KeyboardModifier.ControlModifier
            )
            self._rubber_band.setGeometry(
                self._drag_start.x(), self._drag_start.y(), 0, 0
            )
            self._rubber_band.show()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """ドラッグ中に QRubberBand をカーソルに追従させる。"""
        if self._rubber_band_active and self._drag_start is not None:
            from PySide6.QtCore import QRect

            current = event.position().toPoint()
            self._rubber_band.setGeometry(
                QRect(self._drag_start, current).normalized()
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """マウスリリースで選択範囲を確定し、コールバックに通知する。"""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._rubber_band_active
            and self._drag_start is not None
        ):
            self._rubber_band.hide()
            self._rubber_band_active = False
            drag_end = event.position().toPoint()

            # ドラッグ距離が小さすぎる場合は選択とみなさない。
            if (
                abs(drag_end.x() - self._drag_start.x()) < 5
                or abs(drag_end.y() - self._drag_start.y()) < 5
            ):
                self._drag_start = None
                self._drag_append_mode = False
                super().mouseReleaseEvent(event)
                return

            # ビュー座標 → シーン座標
            scene_start = self.mapToScene(self._drag_start)
            scene_end = self.mapToScene(drag_end)
            self._drag_start = None
            append_mode = self._drag_append_mode
            self._drag_append_mode = False

            # どのページ上かを判定する。
            page_number: int | None = None
            for i, page_rect in enumerate(self._page_rects):
                if page_rect.contains(scene_start):
                    page_number = i
                    break

            if page_number is None:
                super().mouseReleaseEvent(event)
                return

            # ページ内のローカル座標に変換する。
            page_rect = self._page_rects[page_number]
            local_x0 = scene_start.x() - page_rect.x()
            local_y0 = scene_start.y() - page_rect.y()
            local_x1 = scene_end.x() - page_rect.x()
            local_y1 = scene_end.y() - page_rect.y()

            # ピクセル座標 → PDF ポイント座標に変換 (72dpi 基準)。
            scale = self._current_dpi / 72.0
            pdf_x0 = local_x0 / scale
            pdf_y0 = local_y0 / scale
            pdf_x1 = local_x1 / scale
            pdf_y1 = local_y1 / scale

            # 座標を正規化（左上→右下の順序を保証）する。
            rect = RectCoords(
                x0=min(pdf_x0, pdf_x1),
                y0=min(pdf_y0, pdf_y1),
                x1=max(pdf_x0, pdf_x1),
                y1=max(pdf_y0, pdf_y1),
            )

            if self._on_selection_requested:
                self._on_selection_requested(page_number, rect, append_mode)
            elif self._on_area_selected:
                self._on_area_selected(page_number, rect)

        super().mouseReleaseEvent(event)

    # =====================================================================
    # ズーム (Ctrl+ホイール)
    # =====================================================================

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Ctrl+ホイールでズーム変更をコールバックに通知する。"""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                new_zoom = min(self._zoom_level + ZOOM_STEP, ZOOM_MAX)
            else:
                new_zoom = max(self._zoom_level - ZOOM_STEP, ZOOM_MIN)
            if new_zoom != self._zoom_level:
                self._zoom_level = new_zoom
                if self._on_zoom_changed:
                    self._on_zoom_changed(new_zoom)
            event.accept()
        else:
            super().wheelEvent(event)

    # =====================================================================
    # 選択ハイライト
    # =====================================================================

    def add_highlight(self, page_number: int, rect: RectCoords) -> None:
        """単一選択 API 互換のため、単独スロットとして描画する。"""
        self.set_selection_snapshot(
            SelectionSnapshot(
                slots=(
                    SelectionSlot(
                        selection_id="legacy-selection",
                        display_number=1,
                        page_number=page_number,
                        rect=rect,
                        read_state="ready",
                    ),
                )
            )
        )

    def clear_highlight(self) -> None:
        """すべての選択ハイライトを除去する。"""
        self.set_selection_snapshot(SelectionSnapshot())

    def set_selection_snapshot(self, snapshot: SelectionSnapshot) -> None:
        """複数選択スナップショットを保持し、全オーバーレイを再同期する。"""
        self._selection_snapshot = snapshot
        self.refresh_selection_overlays()

    def refresh_selection_overlays(self) -> None:
        """保持している全選択オーバーレイの位置と番号を再計算する。"""
        active_ids = {slot.selection_id for slot in self._selection_snapshot.slots}
        stale_ids = [
            selection_id
            for selection_id in self._selection_overlays
            if selection_id not in active_ids
        ]
        for selection_id in stale_ids:
            self._remove_selection_overlay(selection_id)

        for slot in self._selection_snapshot.slots:
            scene_rect = self._make_scene_selection_rect(
                slot.page_number, slot.rect
            )
            if scene_rect is None:
                self._remove_selection_overlay(slot.selection_id)
                continue
            rect_item, badge_item, badge_text_item = (
                self._get_or_create_selection_overlay(slot.selection_id)
            )
            pen, brush, badge_pen, badge_brush = self._selection_style(
                slot.read_state
            )
            rect_item.setPen(pen)
            rect_item.setBrush(brush)
            rect_item.setRect(scene_rect)

            badge_item.setPen(badge_pen)
            badge_item.setBrush(badge_brush)

            badge_text = str(slot.display_number)
            if badge_text_item.toPlainText() != badge_text:
                badge_text_item.setPlainText(badge_text)
            text_rect = badge_text_item.boundingRect()
            badge_width = max(18.0, text_rect.width() + 8.0)
            badge_height = max(18.0, text_rect.height() + 4.0)
            badge_item.setRect(0.0, 0.0, badge_width, badge_height)
            badge_item.setPos(scene_rect.left() + 6.0, scene_rect.top() + 6.0)
            badge_text_item.setPos(
                (badge_width - text_rect.width()) / 2.0,
                (badge_height - text_rect.height()) / 2.0 - 1.0,
            )

    def _make_scene_selection_rect(
        self, page_number: int, rect: RectCoords
    ) -> QRectF | None:
        """選択矩形をページローカル座標からシーン座標へ変換する。"""
        if page_number < 0 or page_number >= len(self._page_rects):
            return None

        scale = self._current_dpi / 72.0
        scene_rect = QRectF(
            rect.x0 * scale,
            rect.y0 * scale,
            (rect.x1 - rect.x0) * scale,
            (rect.y1 - rect.y0) * scale,
        )
        page_rect = self._page_rects[page_number]
        scene_rect.translate(page_rect.x(), page_rect.y())
        return scene_rect

    def _get_or_create_selection_overlay(
        self, selection_id: str
    ) -> tuple[QGraphicsRectItem, QGraphicsRectItem, QGraphicsTextItem]:
        """選択 ID に対応する矩形と番号バッジを生成または再利用する。"""
        overlay = self._selection_overlays.get(selection_id)
        if overlay is not None:
            return overlay

        rect_item = self._scene.addRect(QRectF())
        rect_item.setZValue(10)

        badge_item = QGraphicsRectItem()
        badge_item.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )
        badge_item.setZValue(20)
        self._scene.addItem(badge_item)

        badge_text_item = QGraphicsTextItem(badge_item)
        badge_text_item.setDefaultTextColor(QColor(255, 255, 255))
        badge_text_item.setFont(self._badge_font)
        badge_text_item.setZValue(1)

        overlay = (rect_item, badge_item, badge_text_item)
        self._selection_overlays[selection_id] = overlay
        return overlay

    def _remove_selection_overlay(self, selection_id: str) -> None:
        """指定した選択 ID のオーバーレイをシーンから除去する。"""
        overlay = self._selection_overlays.pop(selection_id, None)
        if overlay is None:
            return

        rect_item, badge_item, _ = overlay
        self._scene.removeItem(rect_item)
        self._scene.removeItem(badge_item)

    def _selection_style(
        self, read_state: str
    ) -> tuple[QPen, QBrush, QPen, QBrush]:
        """読取状態に応じた矩形と番号バッジのスタイルを返す。"""
        if read_state == "error":
            base = QColor(196, 64, 64)
        elif read_state == "pending":
            base = QColor(217, 122, 0)
        else:
            base = QColor(0, 120, 215)

        return (
            QPen(base, 1.2),
            QBrush(QColor(base.red(), base.green(), base.blue(), 48)),
            QPen(QColor(base.red(), base.green(), base.blue(), 220), 1.0),
            QBrush(QColor(base.red(), base.green(), base.blue(), 188)),
        )

    # =====================================================================
    # ページジャンプ
    # =====================================================================

    def scroll_to(self, page_number: int) -> None:
        """指定ページが見えるようにスクロールする。"""
        if 0 <= page_number < len(self._page_rects):
            self.ensureVisible(self._page_rects[page_number], 0, 50)

    def get_visible_page(self) -> int:
        """ビューポート上部に最も近いページの 0-indexed 番号を返す。

        DPI 変更後のスクロール位置復元に使用する。
        ページが存在しない場合は 0 を返す。
        """
        if not self._page_rects:
            return 0
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        for i, page_rect in enumerate(self._page_rects):
            if page_rect.intersects(viewport_rect):
                return i
        return 0

    # =====================================================================
    # 縦フィット (Ctrl+H)
    # =====================================================================

    def fit_to_page_height(self) -> None:
        """現在表示中のページの高さがビューポートに収まるようズームを調整する。

        ビューポートの高さと現在のページのピクセル高さから
        必要なズーム率を算出し、_on_zoom_changed を発火する。
        Presenter が再レンダリングフローを実行する。
        """
        if not self._page_sizes:
            return

        # 現在最も上に見えているページを特定する。
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        top_page = 0
        for i, page_rect in enumerate(self._page_rects):
            if page_rect.intersects(viewport_rect):
                top_page = i
                break

        # シーン上のページ高さは DPI 固定で不変なので直接割るだけでよい。
        _, page_height = self._page_sizes[top_page]
        viewport_height = self.viewport().height()
        new_zoom = viewport_height / page_height

        # ZOOM_MIN 〜 ZOOM_MAX でクランプする。
        new_zoom = max(ZOOM_MIN, min(new_zoom, ZOOM_MAX))

        if new_zoom != self._zoom_level:
            self._zoom_level = new_zoom
            if self._on_zoom_changed:
                self._on_zoom_changed(new_zoom)
