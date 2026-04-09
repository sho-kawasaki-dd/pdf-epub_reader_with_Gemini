# Plan: Phase 1 — Interfaces, DTOs, Mock Views, Presenter Skeletons

Phase 1 は、設計書の「GUIなしでロジックの流れを確認する」ゴールを達成するため、全層の契約（Protocol）を定義し、Mock実装でPresenterのフローを検証するところまでを行います。

---

### **Step 1: DTO 定義** (`dto/`) *— 並行作業可*

**document_dto.py:**
- `RectCoords` — x0, y0, x1, y1 (float, PDFポイント座標系)
- `PageData` — page_number, image_data (bytes), width, height
- `TextSelection` — page_number, rect: RectCoords, extracted_text
- `DocumentInfo` — file_path, total_pages, title

**ai_dto.py:**
- `AnalysisMode` (Enum) — TRANSLATION, CUSTOM_PROMPT
- `AnalysisRequest` — text, mode, include_explanation (bool), custom_prompt
- `AnalysisResult` — translated_text, explanation, raw_response
- `CacheStatus` — is_active, ttl_seconds, token_count, cache_name

すべて `frozen=True` の dataclass。

---

### **Step 2: View Protocol 定義** (`interfaces/view_interfaces.py`) *— Step 1に依存*

**IMainView Protocol:**

| 種別 | メソッド | 用途 |
|---|---|---|
| 表示命令 | `display_pages(list[PageData])` | ページ画像の描画 |
| | `scroll_to_page(int)` | 指定ページへスクロール |
| | `set_zoom_level(float)` | ズーム率設定 |
| | `show_selection_highlight(int, RectCoords)` | 選択矩形の強調表示 |
| | `clear_selection()` | 選択クリア |
| | `set_window_title(str)` | タイトルバー更新 |
| | `show_status_message(str)` | ステータスバー表示 |
| | `update_recent_files(list[str])` | 最近のファイルメニュー更新 |
| コールバック | `set_on_file_open_requested(Callable[[], None])` | ファイルダイアログ要求 |
| | `set_on_file_dropped(Callable[[str], None])` | D&D |
| | `set_on_recent_file_selected(Callable[[str], None])` | 履歴選択 |
| | `set_on_area_selected(Callable[[int, RectCoords], None])` | 矩形選択 (page, rect) |
| | `set_on_zoom_changed(Callable[[float], None])` | ズーム変更 |
| | `set_on_cache_management_requested(Callable[[], None])` | キャッシュ管理サブウィンドウ |

**ISidePanelView Protocol:**

| 種別 | メソッド | 用途 |
|---|---|---|
| 表示命令 | `set_selected_text(str)` | 選択テキスト表示 |
| | `update_result_text(str)` | AI結果表示 |
| | `show_loading(bool)` | ローディング状態 |
| | `update_cache_status_brief(str)` | キャッシュ簡易表示 |
| | `set_active_tab(str)` | タブ切替 |
| コールバック | `set_on_translate_requested(Callable[[bool], None])` | 翻訳実行 (解説トグル) |
| | `set_on_custom_prompt_submitted(Callable[[str], None])` | カスタムプロンプト送信 |
| | `set_on_tab_changed(Callable[[str], None])` | タブ変更 |

---

### **Step 3: Model Protocol 定義** (`interfaces/model_interfaces.py` **新規**) *— Step 1に依存*

**IDocumentModel:**
- `async open_document(file_path) -> DocumentInfo`
- `async render_page(page_number, dpi) -> PageData`
- `async render_page_range(start, end, dpi) -> list[PageData]`
- `async extract_text(page_number, rect) -> TextSelection`
- `async extract_all_text() -> str`
- `close_document() -> None`
- `get_document_info() -> DocumentInfo | None`

**IAIModel:**
- `async analyze(request: AnalysisRequest) -> AnalysisResult`
- `async create_cache(full_text: str) -> CacheStatus`
- `async get_cache_status() -> CacheStatus`
- `async invalidate_cache() -> None`
- `async count_tokens(text: str) -> int`

---

### **Step 4: Presenter 実装** (`presenters/`) *— Step 2, 3に依存*

**MainPresenter:**
- `__init__(view: IMainView, document_model: IDocumentModel, panel_presenter: PanelPresenter)`
- `__init__` 内でコールバック登録
- `open_file(path)` → `await document_model.open_document` → `view.display_pages`
- `_on_area_selected(page, rect)` → `await document_model.extract_text` → `panel_presenter.set_selected_text(text)` + `view.show_selection_highlight`
- `_on_zoom_changed(level)` → ページ再レンダリング + `view.set_zoom_level`
- `_on_cache_management_requested()` → キャッシュ管理の起点

**PanelPresenter:**
- `__init__(view: ISidePanelView, ai_model: IAIModel)`
- `set_selected_text(text)` → 保持 + `view.set_selected_text`
- `_on_translate_requested(include_explanation)` → `view.show_loading(True)` → `await ai_model.analyze` → `view.update_result_text` → `view.show_loading(False)`
- `_on_custom_prompt_submitted(prompt)` → 同上（mode=CUSTOM_PROMPT）

---

### **Step 5: Mock 実装** (`tests/mocks/` **新規**) *— Step 2, 3と並行可*

| ファイル | 内容 |
|---|---|
| `mock_views.py` | `MockMainView`, `MockSidePanelView` — コールバック保持 + `simulate_*` メソッド + print |
| `mock_models.py` | `MockDocumentModel`, `MockAIModel` — ダミーデータを返す async スタブ |

---

### **Step 6: フロー検証テスト** (`tests/test_presenters/`) *— Step 4, 5に依存*

**test_main_presenter.py:**
- `test_open_file_flow` — ファイルオープン → `display_pages` が正しいデータで呼ばれる
- `test_area_selection_flow` — 矩形選択 → テキスト抽出 → `panel_presenter.set_selected_text` が呼ばれる
- `test_zoom_change` — ズーム変更 → `set_zoom_level` が呼ばれる

**test_panel_presenter.py:**
- `test_translation_flow` — 選択テキスト設定 → 翻訳実行 → `analyze` 呼び出し → `update_result_text`
- `test_custom_prompt_flow` — カスタムプロンプト送信 → mode=CUSTOM_PROMPT で `analyze`
- `test_loading_state` — `show_loading(True)` → 処理 → `show_loading(False)` の順序確認

---

### **Relevant files**

| ファイル | 操作 |
|---|---|
| `src/pdf_epub_reader/dto/document_dto.py` | 修正 |
| `src/pdf_epub_reader/dto/ai_dto.py` | 修正 |
| `src/pdf_epub_reader/interfaces/view_interfaces.py` | 修正 |
| `src/pdf_epub_reader/interfaces/model_interfaces.py` | **新規** |
| `src/pdf_epub_reader/presenters/main_presenter.py` | 修正 |
| `src/pdf_epub_reader/presenters/panel_presenter.py` | 修正 |
| `tests/mocks/__init__.py` | **新規** |
| `tests/mocks/mock_views.py` | **新規** |
| `tests/mocks/mock_models.py` | **新規** |
| `tests/test_presenters/test_main_presenter.py` | 修正 |
| `tests/test_presenters/test_panel_presenter.py` | 修正 |

### **Verification**

1. `uv run pytest tests/` — 全テストがパス
2. Mock View が Protocol を構造的に満たすことを `runtime_checkable` + `isinstance` で検証
3. エンドツーエンドのフロー: ファイルオープン → ページ表示 → 矩形選択 → テキスト抽出 → サイドパネル表示 → 翻訳実行 → 結果表示

### **Decisions**

- 座標系: PDFページ座標（ポイント）で統一。View側でDPI/ズーム変換してからPresenterに渡す
- キャッシュ管理サブウィンドウの詳細 Protocol は Phase 1 のスコープ外（Phase 5 で定義）
- `dto/` の `__init__.py` で主要な型を re-export し、import を簡潔にする
