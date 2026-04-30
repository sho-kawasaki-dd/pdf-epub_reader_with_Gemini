# Plan: Plotly Dynamic Visualization (pdf_epub_reader)

Gemini API などから返ってきた数式・グラフ仕様を、手元で Plotly により動的可視化する機能を `pdf_epub_reader` に追加する。LLM 応答からの抽出 → 検証 → 描画を一系統に揃え、複数 spec にも対応する。

## 0. ゴールとスコープ

- 入力: AI サイドパネルの **📊 Plotly トグル** が ON の状態で送信し、**成功した応答**に含まれる Plotly グラフ仕様（fenced code block）。
- 出力: 別ウィンドウ（`QWebEngineView`）で hover/zoom 可能な動的グラフを **自動表示**。
- 対象: 翻訳タブ・カスタムタブいずれのリクエストにも適用できる **サイドパネル常設トグル**。
- **非ゴール（Phase 1）**: 任意 Python コードの実行、PNG/HTML 保存、Markdown export との統合、subplot 自動結合、Visualize 手動ボタン。

## 1. 設計の前提（最重要: セキュリティ）

LLM 応答の Python を直接 `exec` することは、PDF 本文経由の prompt injection を踏む現実的リスクがある。よって本企画では実行方式を以下に固定する。

- **Phase 1 では「Plotly figure JSON のみ」を受け取って `plotly.io.from_json` で復元**する。
- Python 実行が必要な要望が出てきた段階で、Phase 2 として **subprocess sandbox + 出力を Plotly JSON に正規化** する経路を後付けする。描画層は Phase 1 と共通化する。
- トグルはサイドパネルに常設し、**設定として永続化**（`plotly_visualization_enabled: bool = False`）。デフォルト無効。
- トグル ON の状態でリクエストを送信すると、`AnalysisRequest.request_plotly_json = True` が焼き込まれ、`AIModel._build_contents()` がプロンプトヘッダー末尾に Plotly JSON 出力指示を **動的注入** する。注入先は `contents`（プロンプト本文）であり `system_instruction` は変更しないため、既存のキャッシュを無効化しない。
- 注入するプロンプト定型文（英語、`contents` 末尾に追記）:
  > `If the response contains data or formulas that can be visualized, output the Plotly figure specification as a JSON fenced code block (\`\`\`json ... \`\`\`). Provide only the pure JSON; do not include Python execution code.`

## 2. 推奨ロードマップ（Phase 切り）

### Phase 1: JSON-only 可視化（MVP）

1. per-request トグル ON 時にプロンプトヘッダーへ Plotly JSON 出力指示を動的注入（`AIModel._build_contents()` 拡張）。
2. 抽出 service: 応答 markdown から Plotly spec の list を取り出す。
3. 描画 service: spec を `Figure` に復元、`to_html(include_plotlyjs="inline")` で HTML 化。
4. View: サイドパネルに 📊 アイコンのトグルボタンを常設。AI 成功かつ spec 抽出成功時に **自動描画**。
5. PlotWindow: `QWebEngineView` で表示する独立ウィンドウ。
6. PanelPresenter / MainPresenter: AI 成功後に push 型でレンダーハンドラを呼ぶ。
7. 設定: `plotly_visualization_enabled`（トグル永続化）と `plotly_multi_spec_mode` のみ。

### Phase 2: Sandboxed Python（オプション）

- `subprocess` 隔離 runner（`-I -S`、空 env、timeout、import allow-list）。
- runner の出力は `fig.to_json()` を stdout に書く形に固定 → Phase 1 の描画パスを再利用。
- 設定で `plotly_execution_mode = "json_only" | "sandboxed_python"` を切替。

### Phase 3: 機能拡張

- 複数 spec のタブ集約 PlotWindow（QTabWidget）。
- HTML / PNG（kaleido）保存、Markdown export への埋め込み。
- spec 一覧ペイン、再描画、コピー操作。

以下は **Phase 1 を実装可能な粒度に分解した Steps** を示す。Phase 2 / 3 は別企画書で詳細化する。

## 3. Steps（Phase 1）

1. **DTO の追加**:
   - `src/pdf_epub_reader/dto/` に `plot_dto.py` を新設し、`PlotlySpec`（`index: int`, `language: Literal["json"]`, `source_text: str`, `title: str | None`）を定義する。後の Phase 2 で `language` に `"python"` を足せる形にしておく。
   - 既存の `AnalysisRequest` DTO に `request_plotly_json: bool = False` フィールドを追加する。`PanelPresenter` がリクエスト構築時に `_plotly_enabled` の**送信時点の値**を焼き込む。

2. **i18n / DTO 文言**: `dto/ui_text_dto.py`、`resources/i18n.py`、`services/translation_service.py` に以下を追加する。
   - `SidePanelTexts.plotly_toggle_tooltip`（📊 トグルボタンのツールチップ。`force_include_image` のラベルと同流儀）
   - 複数 spec 選択ダイアログ用の文言一式（タイトル、cancel、各 spec ラベルのフォールバック「Plot {index}」）
   - status bar 通知（描画成功・抽出失敗・復元失敗・JSON 不正）
   - PlotWindow タイトルテンプレート

3. **設定の追加**: `utils/config.py` に以下のフラットフィールドを追加する。既存の永続化形式と SettingsPresenter の populate/read 流儀を崩さない。
   - `plotly_visualization_enabled: bool = False`（サイドパネルトグルの永続化。`False` がデフォルト）
   - `plotly_multi_spec_mode: Literal["prompt", "first_only"] = "prompt"`
   - （Phase 2 用の予約は今回入れない。導入時に追加する。）

4. **設定 UI**: `views/settings_dialog.py`、`interfaces/view_interfaces.py`、`presenters/settings_presenter.py`、`tests/mocks/mock_views.py` を拡張。Markdown export と同様に **Visualization タブ** を新設するが、内容は **`plotly_multi_spec_mode` のラジオのみ**とする（enable トグルはサイドパネルに移ったため、設定ダイアログには置かない）。

5. **サイドパネルトグルボタン**: `views/side_panel_view.py`、`interfaces/view_interfaces.py`、`presenters/panel_presenter.py` を拡張。`force_include_image` チェックボックスと同じパターンで実装する。
   - `ISidePanelView` に `set_on_plotly_toggled(cb: Callable[[bool], None])` と `set_plotly_toggle_checked(checked: bool)` を追加。
   - `SidePanelView` に 📊 アイコン付きツールボタン（`QToolButton`, `setCheckable(True)`）を翻訳・カスタム実行ボタンの近傍に配置する。
   - `PanelPresenter` に `_plotly_enabled: bool` を追加。初期値は起動時に MainPresenter が `set_plotly_enabled(config.plotly_visualization_enabled)` で注入する。
   - トグル変更時に `_on_plotly_toggled(checked)` が `_plotly_enabled` を更新し、`_on_plotly_toggle_changed_handler`（MainPresenter 登録）を呼んで設定を保存させる。
   - `PanelPresenter.set_on_plotly_toggle_changed_handler(cb: Callable[[bool], None])` を MainPresenter に公開する。

6. **AIModel プロンプト注入**: `models/ai_model.py` の `_build_contents()` を拡張する。
   - `request.request_plotly_json` が `True` のとき、プロンプトヘッダー末尾（`<selection>` タグの直前）に以下の英語定型文を追記する:
     > `If the response contains data or formulas that can be visualized, output the Plotly figure specification as a JSON fenced code block (\`\`\`json ... \`\`\`). Provide only the pure JSON; do not include Python execution code.`
   - 追記先は `contents`（プロンプト本文）であり、`system_instruction` は変更しない。キャッシュキーへの影響なし。
   - `False` のときは従来通り、追記なし。

7. **抽出 service（pure）**: `src/pdf_epub_reader/services/plotly_extraction_service.py` を新設。
   - 入力: AI 応答 markdown 文字列。
   - 出力: `list[PlotlySpec]`。
   - ` ```json … ``` ` を最優先で抽出。言語タグなし fenced block で **先頭バイトが `{` のもの** はフォールバック対象。
   - JSON parse は **ここでは行わない**（spec の保持のみ）。validate は描画 service の責務。
   - title 推測: spec 直前の H2/H3 行、もしくは block 直前 1 行の plain text からトリム。なければ `None`。

8. **描画 service（pure）**: `src/pdf_epub_reader/services/plotly_render_service.py` を新設。
   - `parse_spec(spec: PlotlySpec) -> Figure` … `plotly.io.from_json` を呼ぶ。失敗は構造化 `PlotlyRenderError` を投げる。
   - `figure_to_html(fig: Figure) -> str` … `plotly.io.to_html(fig, include_plotlyjs="inline", full_html=True)`。**`include_plotlyjs="inline"` を強制**してオフライン動作を保証する。

9. **PlotWindow**: `src/pdf_epub_reader/views/plot_window.py` を新設。
   - `QWebEngineView` を内包する独立ウィンドウ（`QWidget`）。`setHtml(html, baseUrl=QUrl())` で読み込み。
   - 親ウィンドウからは `show_figure_html(html: str, title: str)` のみを公開。
   - 既存の `result_window.py`（desktop_capture）に倣ってモードレス、複数同時表示可。
   - 閉じても AI 結果表示には影響しない。

10. **PanelPresenter 拡張**: `presenters/panel_presenter.py`。
    - AI リクエスト構築時（`_do_translate` / `_do_custom_prompt`）に **送信時点の** `self._plotly_enabled` を `AnalysisRequest.request_plotly_json` に焼き込む。
    - AI 成功後、`request.request_plotly_json` が `True` だった場合に抽出 service を呼ぶ。spec が 1 件以上あれば `_on_plotly_render_handler`（MainPresenter 登録）を specs リストを引数に呼ぶ（push 型）。0 件でも失敗扱いにはしない（spec なし通知なし）。
    - AI 失敗時・クリア時・ドキュメント変更時は spec の状態をリセットする（レンダーは呼ばない）。
    - `set_on_plotly_render_handler(cb: Callable[[list[PlotlySpec]], None])` を MainPresenter に公開する。

11. **MainPresenter 拡張**: `presenters/main_presenter.py`。
    - 初期化時に `panel_presenter.set_plotly_enabled(config.plotly_visualization_enabled)` でトグル初期値を注入する。
    - `set_on_plotly_toggle_changed_handler` で `_on_plotly_toggle_changed` を登録し、`config.plotly_visualization_enabled` を更新して `save_config` する。
    - `set_on_plotly_render_handler` で `_on_plotly_render` を登録する。
    - `_on_plotly_render(specs: list[PlotlySpec])`: 1 spec → 即描画。複数 spec かつ `plotly_multi_spec_mode == "prompt"` → View に選択を依頼（`QInputDialog.getItem`）、`first_only` → index 0 を採用。描画 service を呼び、`PlotWindow` を生成して表示。
    - 失敗時は status bar に通知し、AI 結果表示と既存ウィンドウは破壊しない。

12. **テスト**: 既存パターンに合わせて以下を追加する。
    - `tests/test_services/test_plotly_extraction_service.py`: 単一/複数 block、言語タグ揺らぎ、タイトル推測、空応答、JSON 以外の混在。
    - `tests/test_services/test_plotly_render_service.py`: 正常 JSON、壊れた JSON、必須キー欠落、`include_plotlyjs="inline"` の出力検査。
    - `tests/test_presenters/test_panel_presenter.py`: トグル OFF 送信では render ハンドラが呼ばれないこと、トグル ON 送信かつ spec あり → render ハンドラ呼び出し、AI 失敗時の reset。
    - `tests/test_presenters/test_main_presenter.py`: 1 spec 即描画、複数 spec `prompt` モード選択、複数 spec `first_only` モード、描画失敗時 status bar、トグル変更で設定保存。
    - `tests/test_presenters/test_settings_presenter.py`: `plotly_visualization_enabled` の往復、`plotly_multi_spec_mode` の往復。
    - `tests/mocks/mock_views.py`: `set_on_plotly_toggled`、`set_plotly_toggle_checked`、選択ダイアログのモック、PlotWindow ファクトリのモック。

13. **手動検証**: `uv run python -m pdf_epub_reader` で以下を確認する（Step 7 に詳細）。

## 4. 設計上の決定（Phase 1 で固定）

- LLM 応答の Python は **実行しない**。Plotly JSON のみ受け付ける。
- プロンプト注入は per-request トグル ON 時に **`_build_contents()` の `contents` ヘッダー末尾に追記**する。`system_instruction` は変更しないため、既存キャッシュに影響しない。
- トグルは `plotly_visualization_enabled: bool = False` として設定永続化。サイドパネルの 📊 ツールボタンと双方向同期（設定変更 → ボタン反映、ボタン変更 → 設定保存）。
- **送信時点のトグル状態が優先。** `_plotly_enabled` は `AnalysisRequest.request_plotly_json` に焼き込まれ、応答待ち中にトグルを変更しても現リクエストの挙動は変わらない。
- AI 成功後、`request_plotly_json=True` かつ spec 1 件以上 → **自動描画**。spec 0 件のときは追加 UI なし（注入はしたが LLM がグラフを出さなかった場合として静かにスキップ）。
- spec が複数の場合の挙動は設定で `prompt`（既定）/ `first_only` を選べる。タブ集約は Phase 3。
- PlotWindow は `QWebEngineView` + `include_plotlyjs="inline"` でオフライン動作。
- ファイル保存・Markdown export 統合は今回入れない。
- 成功・失敗通知は MainWindow status bar（Markdown export と同方針）。

## 5. Relevant files

- 既存（変更あり）
  - [src/pdf_epub_reader/models/ai_model.py](src/pdf_epub_reader/models/ai_model.py) — `_build_contents()` に Plotly 注入追記（Step 6）
  - [src/pdf_epub_reader/dto/ui_text_dto.py](src/pdf_epub_reader/dto/ui_text_dto.py) — `AnalysisRequest.request_plotly_json` 追加（Step 1）、`plotly_toggle_tooltip` 追加（Step 2）
  - [src/pdf_epub_reader/presenters/panel_presenter.py](src/pdf_epub_reader/presenters/panel_presenter.py)
  - [src/pdf_epub_reader/presenters/main_presenter.py](src/pdf_epub_reader/presenters/main_presenter.py)
  - [src/pdf_epub_reader/presenters/settings_presenter.py](src/pdf_epub_reader/presenters/settings_presenter.py)
  - [src/pdf_epub_reader/views/side_panel_view.py](src/pdf_epub_reader/views/side_panel_view.py)
  - [src/pdf_epub_reader/views/settings_dialog.py](src/pdf_epub_reader/views/settings_dialog.py)
  - [src/pdf_epub_reader/interfaces/view_interfaces.py](src/pdf_epub_reader/interfaces/view_interfaces.py)
  - [src/pdf_epub_reader/utils/config.py](src/pdf_epub_reader/utils/config.py)
  - [src/pdf_epub_reader/resources/i18n.py](src/pdf_epub_reader/resources/i18n.py)
  - [src/pdf_epub_reader/services/translation_service.py](src/pdf_epub_reader/services/translation_service.py)
  - [tests/mocks/mock_views.py](tests/mocks/mock_views.py)
  - [tests/test_presenters/test_panel_presenter.py](tests/test_presenters/test_panel_presenter.py)
  - [tests/test_presenters/test_main_presenter.py](tests/test_presenters/test_main_presenter.py)
  - [tests/test_presenters/test_settings_presenter.py](tests/test_presenters/test_settings_presenter.py)
- 新規
  - `src/pdf_epub_reader/dto/plot_dto.py`
  - `src/pdf_epub_reader/services/plotly_extraction_service.py`
  - `src/pdf_epub_reader/services/plotly_render_service.py`
  - `src/pdf_epub_reader/views/plot_window.py`
  - `tests/test_services/test_plotly_extraction_service.py`
  - `tests/test_services/test_plotly_render_service.py`

## 6. 依存関係（パッケージ）

- `plotly`（必須・新規依存）
- `PyQt*` の `QtWebEngineWidgets`（既存環境にあるか確認。なければ依存追加）
- 数値計算系（`numpy` 等）は **Phase 1 では不要**（JSON 復元のみ）。Phase 2 で sandbox runner 用に検討する。

## 7. Verification

1. pure service の単体テストを先に通す（抽出・描画）。
2. presenter の focused test を通す（panel・main・settings）。
3. `uv run pytest tests/ -q` で全体回帰。
4. `uv run python -m pdf_epub_reader` で手動確認:
   - トグル ON で送信 → JSON 1 件 → 即自動描画
   - トグル ON で送信 → JSON 複数（prompt モード） → 選択ダイアログ → 選択した spec が描画
   - トグル ON で送信 → JSON 複数（first_only モード） → index 0 が自動描画
   - トグル ON で送信 → 壊れた JSON → status bar に失敗通知、AI 結果は維持
   - トグル OFF で送信 → プロンプト注入なし → spec 抽出なし → 描画なし（副作用なし）
   - トグル ON で送信後、応答待ち中にトグル OFF → **現リクエストは ON 扱いで描画される**
   - アプリ再起動後もトグルの状態が保持される（設定永続化の確認）
   - トグル ON で送信 → AI 応答に Plotly block が無い → 描画なし、副作用なし
   - UI 言語切替後にトグルのツールチップ・ダイアログ文言が追従
5. 負ケース: `QtWebEngine` が未インストールの場合に適切なエラーメッセージを出し、アプリがクラッシュしないこと。

## 8. 決定済み論点

| 論点                     | 決定                                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| AI へのプロンプト注入    | ✓ **per-request toggle ON 時に `_build_contents()` の contents ヘッダーへ動的注入**。`system_instruction` は変更しない。 |
| 注入の発動条件           | ✓ **サイドパネルの 📊 トグルボタンが ON の状態で送信**                                                                   |
| 自動描画 vs 手動ボタン   | ✓ **自動描画**。Visualize 手動ボタンは持たない。                                                                         |
| トグルの永続性           | ✓ **設定として保存**（`plotly_visualization_enabled: bool = False`）。アプリ再起動後も状態を保持する。                   |
| トグルの UI 種別         | ✓ **📊 アイコン付き `QToolButton`（checkable）**。翻訳・カスタム実行ボタンの近傍に配置。                                 |
| 送信中のトグル変更       | ✓ **送信時点の状態が優先**。`AnalysisRequest.request_plotly_json` に焼き込まれ、応答受信まで変更が反映されない。         |
| 複数 spec 時の既定モード | ✓ **`prompt`**（選択ダイアログを表示）。設定で `first_only` に変更可。                                                   |
| spec 0 件の挙動          | ✓ **追加 UI なし・副作用なし**（LLM がグラフを出力しなかった場合として静かにスキップ）。                                 |

## 9. 未解決の論点（実装着手前に確定したい）

- `QtWebEngineWidgets` 依存追加の可否（既存依存状況を要確認。代替として `QTextBrowser` + 静的 SVG 出力も検討余地あり）。
