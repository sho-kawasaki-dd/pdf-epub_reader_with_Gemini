# **Phase 4: マルチモーダル矩形選択 — 実装プロンプト**

## **概要**

矩形選択機能を拡張し、テキストだけでなく数式・画像を含む領域にも対応する。
選択領域のコンテンツ種別を自動判定し、必要に応じてクロップ画像を Gemini API にマルチモーダル入力として送信する。テキストのみの場合は従来どおりテキストだけを送信し、トークンを節約する。

AI 回答欄は Markdown + 数式レンダリングに対応させる。

---

## **背景と動機**

PDF 内の数式は以下の格納形式を取りうる:

| 格納形式                               | `get_text("text")` の結果          | 頻度     |
| -------------------------------------- | ---------------------------------- | -------- |
| LaTeX コンパイル済グリフ (pdflatex 等) | 構造が壊れる（上付き・分数が消失） | **最多** |
| 画像として埋め込み                     | テキスト取得不可                   | 多い     |
| Tagged PDF / ActualText                | 比較的良好                         | 少ない   |
| MathML 埋め込み                        | 部分的                             | 稀       |

テキスト抽出だけでは数式の意味が壊れるケースが大半であり、**クロップ画像を Gemini Vision に送信する**ことで正確な認識が可能になる。

---

## **設計方針**

### **3段階のクロップ画像送信判定**

| 優先度 | 判定条件                                               | クロップ画像                    |
| ------ | ------------------------------------------------------ | ------------------------------- |
| 1      | ユーザーが「画像としても送信」トグル ON                | **常に送る**                    |
| 2      | `auto_detect_embedded_images` ON かつ 埋め込み画像検出 | **自動で送る** + ステータス通知 |
| 2      | `auto_detect_math_fonts` ON かつ 数式フォント検出      | **自動で送る** + ステータス通知 |
| 3      | いずれも該当しない & トグル OFF                        | **送らない（テキストのみ）**    |

### **トークン最適化**

- テキストのみの場合: `generate_content(text)` — テキストトークンのみ消費
- 画像付きの場合: `generate_content([text, image_part, ...])` — テキスト＋画像トークン消費

### **AI 回答欄の Markdown レンダリング**

Gemini の応答は Markdown（見出し、箇条書き、コードブロック、LaTeX 数式 `$...$`）で返るため、`QWebEngineView` + KaTeX で描画する。Markdown→HTML 変換は View 層の責務とし、Presenter は生の Markdown 文字列を渡すだけとする。

---

## **MVP 各層の変更仕様**

### **1. DTO 層**

#### `dto/document_dto.py` — `SelectionContent` 新設

```python
@dataclass(frozen=True)
class SelectionContent:
    """矩形選択から抽出されたマルチモーダルコンテンツ。"""
    page_number: int
    rect: RectCoords
    extracted_text: str
    cropped_image: bytes | None = None
    embedded_images: list[bytes] = field(default_factory=list)
    detection_reason: str | None = None  # "embedded_image" / "math_font" / None
```

- `cropped_image`: 選択矩形をページ画像からクロップした PNG バイト列。自動検出またはユーザートグルにより付与。
- `embedded_images`: PDF 内にオブジェクトとして埋め込まれた画像を個別に抽出したバイト列リスト。
- `detection_reason`: 自動検出時の理由。ステータス通知に使用。ユーザートグル強制時は `None`。

既存の `TextSelection` は後方互換のため残すが、新規フローでは `SelectionContent` を使用する。

#### `dto/ai_dto.py` — `AnalysisRequest` 拡張

```python
@dataclass(frozen=True)
class AnalysisRequest:
    text: str
    mode: AnalysisMode
    include_explanation: bool = False
    custom_prompt: str | None = None
    images: list[bytes] = field(default_factory=list)  # 追加
```

### **2. Model 層 — `document_model.py`**

#### 新規メソッド: `extract_content`

```python
async def extract_content(
    self, page_number: int, rect: RectCoords, dpi: int,
    force_include_image: bool = False,
    auto_detect_embedded_images: bool = True,
    auto_detect_math_fonts: bool = True,
) -> SelectionContent:
```

内部の同期処理 `_extract_content_sync` で以下を実行:

1. **テキスト抽出** (常に実行): `page.get_text("text", clip=clip)`
2. **埋め込み画像検出** (`auto_detect_embedded_images` が True の場合):
   - `page.get_images(full=True)` で画像オブジェクト一覧を取得
   - 各画像の表示位置 `page.get_image_rects(xref)` が選択矩形と交差するか判定
3. **数式フォント検出** (`auto_detect_math_fonts` が True の場合):
   - `page.get_text("dict", clip=clip)` でフォント情報付きブロックを取得
   - 数式フォント名 (`cmmi`, `cmsy`, `cmr`, `cmex`, `math`, `symbol`, `stix` 等) を検出
   - 数学記号の Unicode 範囲 (Mathematical Operators U+2200–U+22FF, Greek U+0391–U+03C9 等) を検出
4. **クロップ画像生成** (`force_include_image` が True、または自動検出ヒットの場合):
   - `page.get_pixmap(matrix=matrix, clip=clip, alpha=False)` でクロップ画像を PNG バイト列化
5. **埋め込み画像の個別抽出** (画像検出時):
   - `doc.extract_image(xref)` で個別画像バイト列を取得

#### 判定フロー (疑似コード)

```python
has_images = auto_detect_embedded_images and _check_embedded_images(page, clip)
has_math = auto_detect_math_fonts and _has_math_content(page, clip)

detection_reason = None
if has_images:
    detection_reason = "embedded_image"
elif has_math:
    detection_reason = "math_font"

if force_include_image or has_images or has_math:
    cropped = _crop_page_image(page, clip, dpi)
else:
    cropped = None
```

### **3. Model 層 — `ai_model.py`**

`analyze` メソッドで `request.images` の有無により API 呼び出しを分岐:

- `images` が空: テキストのみで `generate_content(prompt_text)`
- `images` あり: `generate_content([prompt_text, {"mime_type": "image/png", "data": img}, ...])` でマルチモーダル送信

### **4. Interface 層**

#### `model_interfaces.py` — `IDocumentModel` に追加

```python
async def extract_content(
    self, page_number: int, rect: RectCoords, dpi: int,
    force_include_image: bool = False,
    auto_detect_embedded_images: bool = True,
    auto_detect_math_fonts: bool = True,
) -> SelectionContent: ...
```

#### `view_interfaces.py` — `ISidePanelView` に追加

```python
def set_selected_content_preview(self, text: str, thumbnail: bytes | None) -> None: ...
def set_on_force_image_toggled(self, cb: Callable[[bool], None]) -> None: ...
```

### **5. Presenter 層**

#### `main_presenter.py` — `_do_area_selected` 変更

```python
async def _do_area_selected(self, page_number: int, rect: RectCoords) -> None:
    self._view.show_selection_highlight(page_number, rect)
    config = self._document_model._config  # or pass through constructor
    content = await self._document_model.extract_content(
        page_number, rect, self._current_dpi,
        force_include_image=self._panel_presenter.force_include_image,
        auto_detect_embedded_images=config.auto_detect_embedded_images,
        auto_detect_math_fonts=config.auto_detect_math_fonts,
    )
    if content.cropped_image and content.detection_reason:
        reason_label = {"embedded_image": "画像", "math_font": "数式"}[content.detection_reason]
        self._view.show_status_message(f"{reason_label}を検出 — 画像付きで送信します")
    self._panel_presenter.set_selected_content(content)
```

#### `panel_presenter.py` — マルチモーダル対応

```python
# 新しい内部状態
self._force_include_image: bool = False
self._selected_content: SelectionContent | None = None

# 公開プロパティ
@property
def force_include_image(self) -> bool:
    return self._force_include_image

# コールバック登録
self._view.set_on_force_image_toggled(self._on_force_image_toggled)

def set_selected_content(self, content: SelectionContent) -> None:
    """MainPresenter から呼ばれる。テキスト＋サムネイルを View に反映。"""
    self._selected_content = content
    self._selected_text = content.extracted_text
    self._view.set_selected_content_preview(
        content.extracted_text,
        content.cropped_image,
    )

# analyze 呼び出し時に画像を添付
images_to_send = []
if self._selected_content and self._selected_content.cropped_image:
    images_to_send.append(self._selected_content.cropped_image)

request = AnalysisRequest(
    text=self._selected_text,
    mode=...,
    images=images_to_send,
)
```

### **6. View 層**

#### `side_panel_view.py` — UI 変更

1. **「画像としても送信」チェックボックス** を選択テキスト欄の下に追加（デフォルト OFF）
2. **選択範囲プレビュー**: 既存の `QTextEdit` (テキスト表示) + `QLabel` (サムネイル表示、`thumbnail` が `None` なら非表示)
3. **AI 回答欄**: `QTextEdit` → `QWebEngineView` に差し替え
   - Markdown → HTML 変換は `markdown` ライブラリ (`fenced_code`, `tables` extensions)
   - 数式レンダリングは KaTeX (ローカルバンドル推奨、`resources/katex/` に配置)
   - `_render_markdown_html(md_text: str) -> str` メソッドを View 内に実装（表示形式の責務）

### **7. 設定 — `utils/config.py`**

`AppConfig` に以下を追加:

```python
# 選択領域の自動検出設定
auto_detect_embedded_images: bool = True
auto_detect_math_fonts: bool = True
```

- JSON 永続化は既存の `save_config` / `load_config` がそのまま対応
- Phase 5 (設定ダイアログ) で GUI から変更可能にする

---

## **追加依存パッケージ**

| パッケージ          | 用途                                                   |
| ------------------- | ------------------------------------------------------ |
| `PySide6-WebEngine` | AI 回答欄の HTML/Markdown/数式レンダリング             |
| `markdown`          | Python 側 Markdown → HTML 変換                         |
| KaTeX (JS/CSS)      | LaTeX 数式のブラウザ内レンダリング（ローカルバンドル） |

---

## **テスト方針**

### Model 層テスト (`test_document_model.py` に追加)

- `extract_content` がテキストのみの領域で `cropped_image=None` を返すこと
- `force_include_image=True` で常に `cropped_image` が付くこと
- 数式フォント検出ロジックの単体テスト（CMR/CMMI 等のフォント名マッチ）
- 埋め込み画像検出ロジックの単体テスト（矩形交差判定）
- `auto_detect_embedded_images=False` で画像検出がスキップされること
- `auto_detect_math_fonts=False` で数式検出がスキップされること

### Presenter 層テスト

- `force_include_image` トグルの状態が `extract_content` に正しく渡ること
- 自動検出時に `show_status_message` が呼ばれること
- `SelectionContent.images` が `AnalysisRequest.images` に正しくマッピングされること
- 画像なし時に `AnalysisRequest.images` が空であること

---

## **実装順序**

1. `dto/document_dto.py` に `SelectionContent` を追加
2. `dto/ai_dto.py` の `AnalysisRequest` に `images` フィールドを追加
3. `utils/config.py` の `AppConfig` に自動検出トグルを追加
4. `model_interfaces.py` に `extract_content` を追加
5. `document_model.py` に `extract_content` + 検出ロジックを実装
6. `ai_model.py` のスタブに `images` 対応を追加
7. `view_interfaces.py` に新規メソッドを追加
8. `main_presenter.py` の `_do_area_selected` を `extract_content` に切替
9. `panel_presenter.py` にマルチモーダル対応を追加
10. `side_panel_view.py` にチェックボックス + `QWebEngineView` を導入
11. テスト追加・実行
