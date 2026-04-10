## Plan: KaTeX fix + Collapsible panel + Explanation prompt

3つの修正を View/Model 層中心に行う。Protocol・Presenter の変更は最小限。

---

### Phase A: KaTeX レンダリング修正 (1ファイル)

**原因:** `QWebEngineView.setHtml(html)` に `baseUrl` が渡されていないため、Chromium が `about:blank` オリジンから `file:///` リソース読み込みをブロック → KaTeX の CSS/JS/fonts が一切ロードされない。

**手順:**
1. `SidePanelView.__init__` で KaTeX ディレクトリの `QUrl` を算出し `self._katex_base_url` に保持
2. 全5箇所の `setHtml()` 呼び出しに第二引数として `self._katex_base_url` を追加
   - L224–226, L249–251（プレースホルダー初期HTML×2）
   - L305, L307（`update_result_text` の結果反映×2）

**対象ファイル:**
- `src/pdf_epub_reader/views/side_panel_view.py` — `QUrl` import 追加、`_katex_base_url` 保持、全 `setHtml` 呼び出し修正

---

### Phase B: 選択プレビュー折りたたみ (1ファイル, View限定)

**方式:** `CollapsibleSection` カスタムウィジェット。`▶ 選択テキスト` / `▼ 選択テキスト` のクリック可能ヘッダーで子要素の表示/非表示を切替。初期状態: **展開**。

**手順:**
1. `side_panel_view.py` 内に `CollapsibleSection` ヘルパークラスを追加
   - ヘッダー: フラット `QPushButton`（`▶`/`▼` プレフィックス切替）
   - コンテンツ: `QWidget` コンテナの `setVisible()` をトグル
2. 以下4ウィジェットを `CollapsibleSection` 内に移動:
   - `QLabel("選択テキスト:")` → ヘッダーテキストに統合
   - `_selected_text_edit`, `_thumbnail_label`, `_force_image_checkbox`
3. レイアウト上の位置はモデルコンボの直後、プログレスバーの直前（変更なし）
4. Protocol / Presenter の変更 **不要** — View 内部のレイアウトリファクタのみ

**対象ファイル:**
- `src/pdf_epub_reader/views/side_panel_view.py`

---

### Phase C: 解説付き翻訳プロンプト + パース (4ファイル + テスト)

**方式:** `include_explanation=True` 時にシステムプロンプトへ解説要求を追記。AI は翻訳 + `---` 区切り + 解説を返す。Model が `---` でパースし DTO に分離。

**手順:**

**C1. config に解説追記用定数を追加**
- `src/pdf_epub_reader/utils/config.py` に `DEFAULT_EXPLANATION_ADDENDUM` を追加:
  - 内容:「翻訳の後に「---」区切り線を入れ、その下に専門用語・概念・背景知識の解説を付けてください。」
  - `AppConfig` フィールドは追加しない（設定ダイアログ対象外）

**C2. `_build_system_instruction` を更新**
- `src/pdf_epub_reader/models/ai_model.py` のシグネチャに `include_explanation: bool = False` を追加
- `mode == TRANSLATION` かつ `include_explanation` のとき、展開済みプロンプトに `DEFAULT_EXPLANATION_ADDENDUM` を追記
- `analyze()` の呼び出し箇所で `request.include_explanation` を渡す

**C3. `_parse_response` を更新**
- `src/pdf_epub_reader/models/ai_model.py`: `include_explanation=True` かつ TRANSLATION モード時に `raw_text` を `---` で分割
  - 前半 → `translated_text`、後半 → `explanation`
  - 区切りが見つからない場合 → 全体を `translated_text`、`explanation=None`

**C4. テスト追加**
- `tests/test_models/test_ai_model.py` — 3件追加:
  - 解説モードでシステム指示に addendum が含まれること
  - `_parse_response` が `---` で正しく分割すること
  - 区切りなしで graceful に動作すること
- `tests/test_presenters/test_panel_presenter.py` — 既存の `test_translate_with_explanation` がパスすることを確認（MockAIModel は既に `explanation` を返すためモック変更不要）

---

### Verification

1. **KaTeX:** アプリ起動 → テキスト選択 → 翻訳 → `$x^2$` が数式としてレンダリングされることを確認
2. **折りたたみ:** ヘッダークリックでセクション開閉。テキスト・サムネイル・チェックボックスがまとめて表示/非表示
3. **解説:** `pytest tests/test_models/test_ai_model.py tests/test_presenters/test_panel_presenter.py -v` — 全パス
4. **回帰:** `pytest tests/ -v` — 全パス

### Decisions
- 折りたたみ: カスタムウィジェット（▶/▼ヘッダー）、初期展開
- プロンプト: 既存翻訳プロンプトへの追記方式（別テンプレート新設なし）
- パース: `---` 区切りで `translated_text` / `explanation` に分離。Presenter の既存結合ロジック（L118–119）をそのまま活用
- `DEFAULT_EXPLANATION_ADDENDUM` はモジュール定数。設定ダイアログ対象外（スコープ最小化）

### Scope boundaries
- **含む:** 上記3修正
- **含まない:** 設定ダイアログへの解説プロンプト編集UI追加、`_render_markdown_html` の HTML テンプレート変更、Protocol インターフェース変更
