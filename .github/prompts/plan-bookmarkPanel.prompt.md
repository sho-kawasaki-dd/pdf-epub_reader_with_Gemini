# Plan: しおり（目次）パネルの追加

## TL;DR

PDF/EPUBの目次(ToC)を左側に折りたたみ可能なツリーパネルとして表示し、クリックで該当ページへ移動できるようにする。既存の `DocumentInfo.toc` データを活用し、新規 View + IMainView 拡張 + Presenter 接続 + テストで実装する。

## 決定事項

- レイアウト: 3ペイン QSplitter（しおり | ドキュメント | AI パネル）
- 初期状態: 文書未オープン / 目次なし → しおりパネル幅 0（折りたたみ）
- 目次あり → 自動で 200px 幅で表示
- トグル: 表示メニュー「しおり(&B)」 + Ctrl+B
- しおりパネル初期幅: 200px
- ツリー展開: 第1レベルのみ展開
- 現在ページハイライト: なし（クリックでページ移動のみ）
- スクロール: 既存の `scroll_to_page()` を再利用
- BookmarkPanelView は MainWindow にコンストラクタ引数として注入（既存パターン踏襲）

---

## Phase 1: BookmarkPanelView の新規作成

**ファイル**: `src/pdf_epub_reader/views/bookmark_panel.py` (新規)

- `QWidget` サブクラス、内部に `QTreeWidget` を持つ
- 公開メソッド:
  - `set_toc(entries: list[ToCEntry])` — 目次データからツリーを構築
    - `ToCEntry.level` を使ってスタックベースで親子関係を構築
    - 各 `QTreeWidgetItem` の `UserRole` に `page_number` (0-indexed) を格納
    - 目次が空の場合はツリーを空にする（表示/非表示はMainWindow側が制御）
    - 第1レベルのみ展開: `collapseAll()` → トップレベル項目のみ `setExpanded(True)`
  - `set_on_entry_selected(cb: Callable[[int], None])` — クリック時コールバック登録
- `QTreeWidget.itemClicked` シグナルで `_handle_item_clicked` → `cb(page_number)` を呼ぶ
- ヘッダーラベル: 「しおり」
- 参考パターン: `SidePanelView` のコールバック登録方式

## Phase 2: IMainView Protocol の拡張

**ファイル**: `src/pdf_epub_reader/interfaces/view_interfaces.py`

- `IMainView` に追加:
  - `display_toc(entries: list[ToCEntry]) -> None` — 目次データをしおりパネルに表示
  - `set_on_bookmark_selected(cb: Callable[[int], None]) -> None` — しおりクリック時コールバック登録
- import に `ToCEntry` を追加

## Phase 3: MainWindow の変更

**ファイル**: `src/pdf_epub_reader/views/main_window.py`

### 3a. コンストラクタ変更

- `__init__(self, side_panel: QWidget)` → `__init__(self, side_panel: QWidget, bookmark_panel: QWidget)`
- `self._bookmark_panel = bookmark_panel` を保持
- `self._splitter` をインスタンス変数として保持（トグル用に参照が必要）

### 3b. スプリッター構成を 3 ペインに変更

- `splitter.addWidget(bookmark_panel)` — index 0
- `splitter.addWidget(doc_pane)` — index 1
- `splitter.addWidget(side_panel)` — index 2
- 初期サイズ: `[0, DEFAULT_WINDOW_WIDTH * 70 // 100, DEFAULT_WINDOW_WIDTH * 30 // 100]`
  - しおりは最初は幅 0（折りたたみ状態）
- `splitter.setCollapsible(0, True)` — しおりは折りたたみ可能
- `splitter.setCollapsible(1, False)` — ドキュメントは折りたたみ不可
- config.py の `SPLITTER_RATIO` を `(70, 30)` から 3 値対応に変更するか、しおり表示時に動的計算するか
  → `BOOKMARK_PANEL_WIDTH = 200` を config.py に追加し、表示時に動的に計算する方が既存 SPLITTER_RATIO への影響を最小化

### 3c. 表示メニュー追加 (`_build_menu_bar` 変更)

- 「表示(&V)」メニューを新規作成
- 「しおり(&B)」アクション: `Ctrl+B` ショートカット、チェック可能 (`setCheckable(True)`)
- トグル処理: `_handle_toggle_bookmark(checked: bool)`
  - checked=True → `self._splitter.setSizes([BOOKMARK_PANEL_WIDTH, ...残り計算...])` で表示
  - checked=False → `self._splitter.setSizes([0, ...残り計算...])` で折りたたみ
  - 既存のドキュメントペインと AI パネルの比率はそのまま維持

### 3d. IMainView 新メソッドの実装

- `display_toc(entries: list[ToCEntry])`:
  - `self._bookmark_panel.set_toc(entries)` を呼ぶ
  - 目次がある場合: しおりパネルを表示状態にしてチェックメニューを更新
  - 目次がない場合: しおりパネルを非表示にしてチェックメニューを更新
- `set_on_bookmark_selected(cb: Callable[[int], None])`:
  - `self._bookmark_panel.set_on_entry_selected(cb)` を呼ぶ

### 3e. コールバック保持フィールドの追加

- `self._on_bookmark_selected: Callable[[int], None] | None = None` (他のコールバックと同じパターン)

## Phase 4: MainPresenter の変更

**ファイル**: `src/pdf_epub_reader/presenters/main_presenter.py`

### 4a. コンストラクタでコールバック登録

- `self._view.set_on_bookmark_selected(self._on_bookmark_selected)` を追加

### 4b. `open_file()` に目次表示を追加

- `self._view.display_pages(placeholders)` の後に:
  ```
  self._view.display_toc(doc_info.toc)
  ```

### 4c. しおりクリックハンドラ追加

- `_on_bookmark_selected(self, page_number: int) -> None`:
  - `self._view.scroll_to_page(page_number)` を呼ぶ

## Phase 5: app.py のワイヤリング変更

**ファイル**: `src/pdf_epub_reader/app.py`

- `from pdf_epub_reader.views.bookmark_panel import BookmarkPanelView` を追加
- `bookmark_panel = BookmarkPanelView()` を生成
- `MainWindow(side_panel=side_panel_view, bookmark_panel=bookmark_panel)` に変更

## Phase 6: config.py に定数追加

**ファイル**: `src/pdf_epub_reader/utils/config.py`

- `BOOKMARK_PANEL_WIDTH = 200` を追加

## Phase 7: テスト更新

### 7a. MockMainView の更新

**ファイル**: `tests/mocks/mock_views.py`

- `display_toc(entries)` — calls に記録
- `set_on_bookmark_selected(cb)` — コールバック保持
- `simulate_bookmark_selected(page_number)` — テスト用シミュレーション

### 7b. conftest.py の更新は不要

- `main_presenter` フィクスチャは MockMainView を使うので、MockMainView が Protocol を満たせば自動的にテスト可能

### 7c. 新規テスト追加

**ファイル**: `tests/test_presenters/test_main_presenter.py` に追記

- `test_open_file_displays_toc`: 文書を開くと `display_toc` が呼ばれることを検証
- `test_bookmark_selected_scrolls_to_page`: しおりクリック → `scroll_to_page` が呼ばれることを検証
- `test_open_file_empty_toc`: 目次なし文書でも `display_toc([])` が呼ばれることを検証

### 7d. Protocol 適合性テスト

- 既存の `test_mock_main_view_satisfies_protocol` が `display_toc` / `set_on_bookmark_selected` を追加後も通ることを確認

---

## 変更ファイル一覧

| ファイル                                            | 操作     | 変更内容                                                    |
| --------------------------------------------------- | -------- | ----------------------------------------------------------- |
| `src/pdf_epub_reader/views/bookmark_panel.py`       | **新規** | QTreeWidget ベースのしおりパネル                            |
| `src/pdf_epub_reader/interfaces/view_interfaces.py` | 変更     | IMainView に `display_toc`, `set_on_bookmark_selected` 追加 |
| `src/pdf_epub_reader/views/main_window.py`          | 変更     | 3ペインスプリッター、表示メニュー、トグル、display_toc 実装 |
| `src/pdf_epub_reader/presenters/main_presenter.py`  | 変更     | open_file に目次表示追加、しおりクリックハンドラ            |
| `src/pdf_epub_reader/app.py`                        | 変更     | BookmarkPanelView 生成・注入                                |
| `src/pdf_epub_reader/utils/config.py`               | 変更     | BOOKMARK_PANEL_WIDTH 定数追加                               |
| `tests/mocks/mock_views.py`                         | 変更     | MockMainView に新メソッド追加                               |
| `tests/test_presenters/test_main_presenter.py`      | 変更     | しおり関連テスト追加                                        |

## 検証手順

1. `pytest tests/` — 既存テスト + 新規テストがすべて通ること
2. `python -m pdf_epub_reader` で起動、目次付き PDF を開き:
   - しおりパネルが自動表示されること
   - 階層構造が正しくツリー表示されること（第1レベルのみ展開）
   - 項目クリックで該当ページにスクロールすること
   - Ctrl+B でしおりパネルの表示/非表示が切り替わること
   - 表示メニューの「しおり」のチェック状態が同期すること
3. 目次を持たない PDF を開き、しおりパネルが非表示のままであること
4. 文書未オープン状態でしおりパネルが非表示であること

## スコープ外

- しおりパネル上での現在ページのハイライト/自動追従
- しおりパネルの検索機能
- しおりの編集・追加機能
- ToCEntry へのリンク先座標の追加（精密スクロール）
