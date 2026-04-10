"""メインウィンドウの PySide6 実装。

IMainView Protocol を満たし、ドキュメント表示・ファイル操作・ズーム・
ステータスバーなどメインウィンドウ全体の UI を担当する。
ビジネスロジックは持たず、操作はすべてコールバック経由で Presenter に伝達する。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
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

from pdf_epub_reader.dto import PageData, RectCoords
from pdf_epub_reader.utils.config import (
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


class MainWindow(QMainWindow):
    """IMainView Protocol を満たすメインウィンドウ実装。

    外部から SidePanelView (QWidget) をインジェクトし、
    QSplitter で左にドキュメント表示、右にサイドパネルを配置する。
    """

    def __init__(self, side_panel: QWidget) -> None:
        super().__init__()
        self.setWindowTitle("PDF/EPUB Reader")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        # --- コールバック保持 ---
        self._on_file_open_requested: Callable[[], None] | None = None
        self._on_file_dropped: Callable[[str], None] | None = None
        self._on_recent_file_selected: Callable[[str], None] | None = None
        self._on_zoom_changed: Callable[[float], None] | None = None
        self._on_cache_management_requested: Callable[[], None] | None = None
        self._on_settings_requested: Callable[[], None] | None = None

        # --- QSettings で最近のファイルを永続化 ---
        self._settings = QSettings("pdf-epub-reader", "pdf-epub-reader")

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
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(doc_pane)
        splitter.addWidget(side_panel)
        splitter.setSizes(
            [
                DEFAULT_WINDOW_WIDTH * SPLITTER_RATIO[0] // 100,
                DEFAULT_WINDOW_WIDTH * SPLITTER_RATIO[1] // 100,
            ]
        )
        self.setCentralWidget(splitter)

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

    # =========================================================================
    # メニューバー構築
    # =========================================================================

    def _build_menu_bar(self) -> None:
        """ファイルメニュー・編集メニューを構築する。"""
        menubar = self.menuBar()
        file_menu = menubar.addMenu("ファイル(&F)")

        # 開く
        open_action = QAction("開く(&O)...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._handle_open_action)
        file_menu.addAction(open_action)

        # 最近開いたファイル
        self._recent_files_menu = QMenu("最近開いたファイル", self)
        file_menu.addMenu(self._recent_files_menu)
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        # 終了
        quit_action = QAction("終了(&Q)", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # --- 編集メニュー ---
        edit_menu = menubar.addMenu("Edit(&E)")

        preferences_action = QAction("Preferences", self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._handle_settings_requested)
        edit_menu.addAction(preferences_action)

    # =========================================================================
    # ステータスバー構築
    # =========================================================================

    def _build_status_bar(self) -> None:
        """ステータスメッセージのみ配置する。ページ/ズームはドキュメントペイン内。"""
        status_bar: QStatusBar = self.statusBar()

        self._status_label = QLabel("Ready")
        status_bar.addWidget(self._status_label, stretch=1)

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

    def set_zoom_level(self, level: float) -> None:
        """ズームスピンボックスの値を更新し、ビュー変換で拡縮する。

        DPI は固定のまま、QGraphicsView の setTransform で拡縮する。
        これにより再レンダリングなしでズームが即座に反映される。
        """
        self._zoom_spinbox.blockSignals(True)
        self._zoom_spinbox.setValue(int(level * 100))
        self._zoom_spinbox.blockSignals(False)
        # _DocumentGraphicsView のズーム状態を同期する。
        # DPI は固定のため _current_dpi は変更しない。
        self._doc_view._zoom_level = level
        self._doc_view.resetTransform()
        self._doc_view.scale(level, level)

    def show_selection_highlight(
        self, page_number: int, rect: RectCoords
    ) -> None:
        """指定ページの指定矩形に半透明のハイライトを重ねる。"""
        self._doc_view.add_highlight(page_number, rect)

    def clear_selection(self) -> None:
        """選択ハイライトを除去する。"""
        self._doc_view.clear_highlight()

    def set_window_title(self, title: str) -> None:
        """ウィンドウタイトルを更新する。"""
        self.setWindowTitle(title)

    def show_status_message(self, message: str) -> None:
        """ステータスバーのメッセージを更新する。"""
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

    def set_on_zoom_changed(self, cb: Callable[[float], None]) -> None:
        self._on_zoom_changed = cb
        self._doc_view._on_zoom_changed = cb

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
            "ドキュメントを開く",
            "",
            "Documents (*.pdf *.epub)",
        )
        if file_path and self._on_file_dropped:
            # open と drop を統合し、同一のコールバックでパスを渡す。
            self._add_to_recent(file_path)
            self._on_file_dropped(file_path)

    def _handle_settings_requested(self) -> None:
        """Edit > Preferences / Ctrl+, ハンドラ。コールバック経由で Presenter に通知する。"""
        if self._on_settings_requested:
            self._on_settings_requested()

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
            no_items = QAction("(なし)", self)
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
        page_label = QLabel("ページ:")
        page_label.setStyleSheet("background: transparent; color: #82b1ff;")
        layout.addWidget(page_label)

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

        # --- 内部状態 ---
        # ページごとの表示アイテム（プレースホルダーまたは画像）
        self._page_items: list[QGraphicsPixmapItem | QGraphicsRectItem] = []
        # 各ページのシーン上の配置矩形
        self._page_rects: list[QRectF] = []
        # 各ページの (width, height)
        self._page_sizes: list[tuple[int, int]] = []
        # 画像がセット済みのページ番号
        self._rendered_pages: set[int] = set()
        # 選択ハイライトアイテム
        self._highlight_item: QGraphicsRectItem | None = None

        # --- コールバック ---
        self._on_area_selected: (
            Callable[[int, RectCoords], None] | None
        ) = None
        self._on_zoom_changed: Callable[[float], None] | None = None
        self._on_pages_needed: Callable[[list[int]], None] | None = None
        self._on_visible_page_changed: (
            Callable[[int], None] | None
        ) = None
        self._on_file_dropped: Callable[[str], None] | None = None

        # --- DPI・ズーム ---
        self._current_dpi: int = DEFAULT_DPI
        self._zoom_level: float = 1.0

        # --- ラバーバンド選択用 ---
        self._rubber_band = QRubberBand(
            QRubberBand.Shape.Rectangle, self.viewport()
        )
        self._rubber_band_active = False
        self._drag_start = None

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
        self._highlight_item = None

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

            pixmap = QPixmap()
            if not pixmap.loadFromData(page.image_data):
                # 画像データが不正な場合はスキップする。
                continue

            # 高 DPI モニター対応: render_dpi で描画された画像を
            # base_dpi 相当の論理サイズで表示するため dpr を設定する。
            pixmap.setDevicePixelRatio(self.devicePixelRatio())

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
                super().mouseReleaseEvent(event)
                return

            # ビュー座標 → シーン座標
            scene_start = self.mapToScene(self._drag_start)
            scene_end = self.mapToScene(drag_end)
            self._drag_start = None

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

            if self._on_area_selected:
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
        """指定ページの指定矩形に半透明のハイライトを重ねる。"""
        self.clear_highlight()
        if page_number < 0 or page_number >= len(self._page_rects):
            return

        # PDF 座標 → ピクセル座標に逆変換する。
        scale = self._current_dpi / 72.0
        px_rect = QRectF(
            rect.x0 * scale,
            rect.y0 * scale,
            (rect.x1 - rect.x0) * scale,
            (rect.y1 - rect.y0) * scale,
        )
        # ページのシーン上の位置にオフセットする。
        page_rect = self._page_rects[page_number]
        px_rect.translate(page_rect.x(), page_rect.y())
        self._highlight_item = self._scene.addRect(
            px_rect,
            QPen(QColor(0, 120, 215)),
            QBrush(QColor(0, 120, 215, 60)),
        )

    def clear_highlight(self) -> None:
        """選択ハイライトを除去する。"""
        if self._highlight_item:
            self._scene.removeItem(self._highlight_item)
            self._highlight_item = None

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
