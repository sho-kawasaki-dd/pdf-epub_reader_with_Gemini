## Plan: GUI 操作改善 4 件 (View 層のみ)

DnD が左ペインで効かない・Ctrl+H 縦フィット未実装・ラバーバンド非表示・ズーム時の座標ずれの 4 件を修正する。すべて View 層 (`main_window.py`) 内で完結し、**Protocol / Presenter / Model / テストの変更は不要**。

---

### Phase A: DPI/ズーム同期修正 (Issue 4) — 他の修正の前提

**Step 1.** `MainWindow.set_zoom_level()` で `_DocumentGraphicsView` の内部状態を同期

- 対象: `src/pdf_epub_reader/views/main_window.py` の `set_zoom_level()` メソッド
- 追加: `self._doc_view._current_dpi = int(DEFAULT_DPI * level)` と `self._doc_view._zoom_level = level`
- **根本原因:** Presenter が `set_zoom_level(level)` を呼んでもスピンボックスだけ更新し、`_DocumentGraphicsView._current_dpi` が初期値 144 のまま。座標変換 (`mouseReleaseEvent` / `add_highlight`) が常に zoom=100% の DPI で計算されていた

---

### Phase B: ラバーバンド表示 (Issue 3)

**Step 2.** インポートに `QRubberBand` を追加

**Step 3.** `_DocumentGraphicsView.__init__` に `QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())` を生成

**Step 4.** `mousePressEvent` で `self._rubber_band.setGeometry(...)` + `show()`

**Step 5.** `mouseMoveEvent` でドラッグ中に `setGeometry(QRect(start, current).normalized())` でリサイズ

**Step 6.** `mouseReleaseEvent` 冒頭で `self._rubber_band.hide()`

---

### Phase C: DnD を両ペインで有効化 (Issue 1)

**Step 7.** `_DocumentGraphicsView` にファイルドロップ用コールバック `_on_file_dropped` を追加 + `setAcceptDrops(True)`

**Step 8.** `_DocumentGraphicsView` に `dragEnterEvent` / `dropEvent` をオーバーライド（`MainWindow` の既存ロジックと同パターン）

**Step 9.** `MainWindow` 側で DnD ハンドラを共通メソッド `_handle_file_drop(path)` に抽出し、`MainWindow.dropEvent` と `_DocumentGraphicsView` のコールバックの両方から呼ぶ

---

### Phase D: Ctrl+H 縦フィット (Issue 2)

**Step 10.** `MainWindow.__init__` で `QShortcut(QKeySequence("Ctrl+H"), self)` を登録 → `_doc_view.fit_to_page_height()` を呼ぶ。MainWindow レベル登録でフォーカス位置に関係なく動作

**Step 11.** `_DocumentGraphicsView.fit_to_page_height()` メソッドを新設:

- 現在最上部に見えているページを特定
- 計算: `new_zoom = viewport_height / page_sizes[top_page][1] * current_zoom_level`
- `ZOOM_MIN` ～ `ZOOM_MAX` でクランプ
- 既存の `_on_zoom_changed(new_zoom)` を発火（Presenter 側の再レンダリングフローに乗る）

---

### Relevant files

- `src/pdf_epub_reader/views/main_window.py` — **全修正がこのファイルに集中**。`_DocumentGraphicsView` と `MainWindow` の両クラスを編集

### 変更不要

- `interfaces/view_interfaces.py`, `presenters/`, `models/`, `tests/` — 影響なし

### Verification

1. ズーム 200%/50% で矩形選択 → 正しいテキストが抽出される (Issue 4)
2. ドラッグ中に青い矩形がカーソルに追従 → リリースで消える (Issue 3)
3. 左ペインに PDF/EPUB をドラッグ → ファイルが開く。右ペインでも動作 (Issue 1)
4. Ctrl+H → 現在のページが縦にフィット。スピンボックスも追従 (Issue 2)
5. `pytest tests/` 全パス
