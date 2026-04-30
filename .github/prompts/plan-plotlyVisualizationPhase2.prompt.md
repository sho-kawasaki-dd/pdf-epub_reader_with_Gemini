# Plan: Plotly Visualization Phase 2 — Sandboxed Python Runner

LLM が返す Python コード（Plotly Figure 生成）を、ホストとは隔離された **専用 venv + subprocess** で実行し、stdout に出力された Plotly JSON を Phase 1 の描画パイプラインで描画する。サイドパネルの 📊 トグルは **OFF / JSON / Python** の 3 状態に拡張する。

## TL;DR

- 隔離レベル: subprocess + `-I -S` + 空 env + timeout、加えて **専用 venv** を `platformdirs.user_data_dir("gem-read")/sandbox-venv` に自動生成し allow-list パッケージのみインストール。
- runner I/O プロトコル: **stdout に Plotly JSON のみ**。stderr は診断ログ。runner 自身が LLM 由来コードを `exec` し、最終 Figure を `fig.to_json()` で stdout に書く。
- UI: サイドパネルの 📊 トグルを 3 状態に拡張（OFF / JSON / Python）。設定永続化は `plotly_visualization_mode: Literal["off","json","python"]`。
- フォールバック: Python モード送信で応答に Python ブロックが無く JSON ブロックがあれば JSON 描画。
- 進捗 UI: status bar に **スピナー + Cancel リンク**。Cancel で subprocess を terminate。
- timeout デフォルト 10 秒（設定で上書き可）。stderr はログファイルに保存し、status bar には要約のみ。

## Phases / Steps

### Phase 2-A: 基盤（venv プロビジョナ + runner script）

1. **Allow-list 定数**: `src/pdf_epub_reader/services/plotly_sandbox/__init__.py` を新設し、以下の allow-list を集中管理する。
   - 必須: `plotly`, `kaleido`
   - 数値: `numpy`, `pandas`, `scipy`, `sympy`
   - 標準（ホスト Python に既存。venv からも `--system-site-packages` ではなく標準ライブラリとして利用可）: `math`, `statistics`, `datetime`, `json`
   - allow-list は `ALLOWED_THIRDPARTY_PACKAGES: tuple[str, ...]` と `ALLOWED_STDLIB_MODULES: frozenset[str]` の 2 系統で持つ。
2. **Sandbox venv プロビジョナ**: `src/pdf_epub_reader/services/plotly_sandbox/venv_provisioner.py` を新設。
   - 公開 API: `class SandboxVenvProvisioner` — `ensure(progress_cb: Callable[[str], None] | None = None) -> Path`（Python 実行可能ファイルのパスを返す）。
   - 配置: `platformdirs.user_data_dir("gem-read", "gem-read") / "sandbox-venv"`（OS 横断）。Windows は `Scripts/python.exe`、POSIX は `bin/python`。
   - 生成手順: `venv` モジュールでベース作成 → `python -m pip install --upgrade pip` → allow-list を一括 `pip install`。
   - **冪等性**: 既存 venv に対し allow-list 全パッケージが import 可能か `python -c "import plotly,numpy,..."` でプリチェック。失敗時のみ再構築または不足パッケージのみ追加。
   - **マニフェスト**: venv ルートに `gem-read-sandbox.json`（schema バージョン、allow-list、Python バージョン）を書き込む。schema/Python バージョン不一致なら丸ごと作り直し。
   - 失敗時は構造化例外 `SandboxProvisioningError` を投げる。pip 失敗時の stderr は logger.warning に出す。
3. **Runner script**: `src/pdf_epub_reader/services/plotly_sandbox/runner.py` を新設（**標準ライブラリのみで完結**。venv の Python が `python -I -S runner.py` で起動できる形）。
   - argv: `runner.py --code-path <tmpfile>`（コードはホスト側で書き出して渡す）。
   - 起動時に `sys.modules` をフックし、`__import__` をラップして allow-list 外の import を `ImportError("import 'X' is not allowed in sandbox")` で拒否する。stdlib は `ALLOWED_STDLIB_MODULES` に列挙したもののみ通す。
   - LLM コード実行: `exec(compile(code, "<llm>", "exec"), sandbox_globals)`。
   - 最終 Figure 抽出ルール: 実行後の `globals()` から
     1. `fig` という名前の `plotly.graph_objects.Figure`
     2. それが無ければ最初に見つかった `Figure` インスタンス
   - `plotly.io.to_json(fig)` を **stdout** に書き、改行で締める。それ以外の print は **stderr** にリダイレクトする（`sys.stdout = sys.stderr` を `exec` 直前に差し替え、結果書き出し直前に元に戻す）。
   - 例外時は `sys.exit(2)` し、tracebacks を stderr へ。

### Phase 2-B: 実行 service とプロセス管理

4. **Sandbox executor service**: `src/pdf_epub_reader/services/plotly_sandbox/executor.py` を新設。
   - `class SandboxExecutor` — DI で `SandboxVenvProvisioner` を受け取る。
   - `run(code: str, *, timeout_s: float, cancel_token: CancelToken) -> str`（Plotly JSON 文字列を返す）。
   - フロー: ensure venv → `tempfile.NamedTemporaryFile` にコード書き出し → `subprocess.Popen([python, "-I", "-S", runner_path, "--code-path", tmp])` を `env={}`、`cwd=<tempdir>`、`stdin=DEVNULL`、`stdout=PIPE`、`stderr=PIPE` で起動。
   - timeout 管理: `proc.wait(timeout=timeout_s)`。timeout 時は `proc.terminate()` → 1 秒後に `kill()`。
   - cancel: `CancelToken.cancelled` を別スレッドで監視し、true になったら terminate。
   - 失敗時の構造化例外:
     - `SandboxTimeoutError`
     - `SandboxCancelledError`
     - `SandboxRuntimeError(stderr_summary, stderr_log_path)` — stderr 全文をログファイルに保存し summary のみを保持
     - `SandboxOutputError`（stdout が JSON として parse できない）
5. **CancelToken**: `src/pdf_epub_reader/services/plotly_sandbox/cancel.py` を新設。`threading.Event` ラッパで OK。

### Phase 2-C: DTO / 設定 / プロンプト

6. **DTO 拡張**: `src/pdf_epub_reader/dto/plot_dto.py` を更新。
   - `PlotlySpec.language: Literal["json", "python"]` に拡張。
   - `AnalysisRequest.request_plotly_json: bool` を **`request_plotly_mode: Literal["off","json","python"] = "off"`** にリネーム置換(Phase 1 の bool は廃止)。`AIModel` / `PanelPresenter` の参照点をすべて差し替える。
7. **Config 拡張**: `src/pdf_epub_reader/utils/config.py`。
   - `plotly_visualization_enabled: bool` を **`plotly_visualization_mode: Literal["off","json","python"] = "off"`** に置換。読み込み時に旧キー(bool)が来たら `True → "json"`, `False → "off"` に正規化する移行コードを `AppConfig.from_dict` 系に追加。
   - 追加: `plotly_sandbox_timeout_s: float = 10.0`(範囲 1–120 を SettingsPresenter で clamp)。
   - 追加: `plotly_sandbox_log_dir`(None 時は `platformdirs.user_log_dir("gem-read")` を使用)。
8. **i18n**: `dto/ui_text_dto.py` / `resources/i18n.py` / `services/translation_service.py`。
   - `SidePanelTexts.plotly_toggle_tooltip_off / _json / _python`(3 状態それぞれ)。
   - status bar 文言: `plotly_sandbox_running`, `plotly_sandbox_timeout`, `plotly_sandbox_runtime_error`, `plotly_sandbox_cancelled`, `plotly_sandbox_provisioning`, `plotly_sandbox_provisioning_failed`, `plotly_sandbox_fallback_to_json`。
   - Settings ダイアログ用: `plotly_timeout_label`, `plotly_timeout_suffix_seconds`。
   - Cancel リンク: `plotly_sandbox_cancel_link`。
9. **AIModel プロンプト注入**: `src/pdf_epub_reader/models/ai_model.py` の `_build_contents()` を拡張。
   - `request.request_plotly_mode == "json"` のとき: Phase 1 の英語定型文(JSON のみ要求)を追記。
   - `request.request_plotly_mode == "python"` のとき: 以下の英語定型文を `contents` ヘッダー末尾(`<selection>` 直前)に追記する。
     > `If the response contains data or formulas that can be visualized, output a self-contained Python script in a` ` ```python ` `fenced code block that builds a Plotly figure named` `fig` `and writes` `plotly.io.to_json(fig)` `to standard output. The script must NOT perform any network access or file I/O. Allowed imports are limited to: plotly, numpy, pandas, scipy, sympy, math, statistics, datetime, json.`
   - `"off"` 時は従来通り注入なし。`system_instruction` は引き続き不変(キャッシュ無効化なし)。

### Phase 2-D: 抽出 / 描画 / フォールバック

10. **抽出 service 拡張**: `src/pdf_epub_reader/services/plotly_extraction_service.py` に `python` ブロック対応を追加。
    - ` ```python … ``` ` を `language="python"` で抽出。同応答に json/python が混在している場合は **配列順序を保持**して両方返す(呼び出し側でモードに応じてフィルタ)。
    - 純粋関数のまま。AST 検証等はここでは行わない(runner の責務)。
11. **描画 dispatcher**: `src/pdf_epub_reader/services/plotly_render_service.py` に `render_spec(spec, *, sandbox: SandboxExecutor | None, timeout_s: float, cancel_token: CancelToken) -> Figure` を追加。
    - `language=="json"` → 既存 `from_json` 経路。
    - `language=="python"` → `sandbox.run(spec.source_text, timeout_s=..., cancel_token=...)` で得た JSON を `from_json` に流して Figure 化。
    - `to_html` は Phase 1 と同じ。
12. **PanelPresenter 拡張**: `presenters/panel_presenter.py`。
    - `_plotly_enabled: bool` を `_plotly_mode: Literal["off","json","python"]` に置換。
    - リクエスト構築時に **送信時点の** `_plotly_mode` を `AnalysisRequest.request_plotly_mode` に焼き込む。
    - AI 成功後の抽出ロジックを以下のように分岐:
      - `mode == "python"`: python spec を優先。0 件で json spec が 1 件以上ある場合は **JSON にフォールバック**(status bar に通知)。
      - `mode == "json"`: 従来通り json spec のみ。
      - `mode == "off"`: 何もしない。
    - render ハンドラに渡すペイロードを `PlotlyRenderRequest(specs: list[PlotlySpec], origin_mode: Literal["json","python"])` 形式に拡張(既存ハンドラ署名の breaking change。MainPresenter と mock_views を同時更新)。
13. **MainPresenter 拡張**: `presenters/main_presenter.py`。
    - 起動時に `panel_presenter.set_plotly_mode(config.plotly_visualization_mode)` で 3 状態を注入。
    - `set_on_plotly_mode_changed_handler` で `_on_plotly_mode_changed` を登録し、`config.plotly_visualization_mode` 更新 + 保存。
    - `_on_plotly_render(request: PlotlyRenderRequest)`:
      - python 由来の spec が含まれる場合、`SandboxExecutor` を遅延生成し(初回呼び出し時に `provisioner.ensure` を Qt スレッドで実行する間、status bar に `plotly_sandbox_provisioning` を表示)、`render_spec` を **QThreadPool ワーカー**にディスパッチ。
      - スピナー + Cancel リンクの表示・解除は MainWindow 側のヘルパに委譲(Step 14)。
      - 例外マッピング:
        - `SandboxTimeoutError` → status bar `plotly_sandbox_timeout`、AI 結果は維持
        - `SandboxCancelledError` → status bar `plotly_sandbox_cancelled`
        - `SandboxRuntimeError` → status bar `plotly_sandbox_runtime_error`、ログパスを tooltip に
        - `SandboxOutputError` → 同上、`plotly_sandbox_runtime_error` を流用
        - `SandboxProvisioningError` → status bar `plotly_sandbox_provisioning_failed`
      - 複数 spec は Phase 1 と同じ `plotly_multi_spec_mode` を流用(prompt / first_only)。
14. **MainWindow status-bar スピナー**: `views/main_window.py` / `interfaces/view_interfaces.py`。
    - `IMainWindow.show_plotly_running(cancel_cb: Callable[[], None]) -> None` と `clear_plotly_running()` を追加。
    - 実装: `QStatusBar.addWidget` に `QLabel`(スピナー文言)と `QLabel(html=<a href=#>cancel</a>)` を貼る。クリックで `cancel_cb` を呼ぶ。
    - mock_views にもスタブを追加。

### Phase 2-E: サイドパネル UI 3 状態化

15. **3 状態トグル UI**: `views/side_panel_view.py`。既存の `_plotly_toggle_btn`(Phase 1 の checkable QToolButton)を **クリックで OFF→JSON→Python→OFF を循環**する `QToolButton` に変更。
    - `setCheckable(False)` に変更し、内部状態 `_plotly_mode` を持つ。アイコン・スタイル・ツールチップを状態に応じて切替(OFF=グレー / JSON=青 / Python=緑、文字バッジ「J」「Py」を `setText` で表示)。
    - 右クリックで明示的に状態を選べる `QMenu`(OFF / JSON / Python)も提供。
    - `ISidePanelView`:
      - `set_on_plotly_mode_changed(cb: Callable[[Literal["off","json","python"]], None])` を追加(旧 `set_on_plotly_toggled` を置換)。
      - `set_plotly_mode(mode: Literal["off","json","python"]) -> None`(旧 `set_plotly_toggle_checked` を置換)。
    - mock_views に同じ I/F を実装。

### Phase 2-F: 設定 UI

16. **Visualization タブ拡張**: `views/settings_dialog.py` / `presenters/settings_presenter.py`。
    - 既存の `plotly_multi_spec_mode` ラジオに加え、`plotly_sandbox_timeout_s` を `QDoubleSpinBox`(1.0–120.0、step 1.0)で配置。
    - **`plotly_visualization_mode` はサイドパネルに UI が出ているため設定ダイアログには置かない**(Phase 1 の方針を維持)。
    - presenter 側の populate / read を増設。tests/mocks/mock_views.py も拡張。

### Phase 2-G: テスト

17. **新規・更新するテスト**:
    - `tests/test_services/test_plotly_sandbox_executor.py`(新規): 実 subprocess を使う統合テスト。
      - 正常系: `fig = plotly.graph_objects.Figure(); fig.add_scatter(...)` のスクリプトで JSON を返す。
      - timeout: `while True: pass` を 1.0s で打ち切る。
      - cancel: 別スレッドで `cancel_token.set()` を 0.3s 後に発火。
      - import 拒否: `import os` で `SandboxRuntimeError`。
      - 出力不正: stdout に非 JSON を吐くスクリプトで `SandboxOutputError`。
      - venv プロビジョニング失敗のシミュレーションは provisioner を monkeypatch して `SandboxProvisioningError` を流す。
      - **CI 軽量化のため `@pytest.mark.slow`** を付け、デフォルトは省略可能に。
    - `tests/test_services/test_plotly_sandbox_provisioner.py`(新規): マニフェスト一致・不一致での再構築判定、allow-list import チェックのモック。実 pip は走らせず `subprocess.run` を monkeypatch。
    - `tests/test_services/test_plotly_extraction_service.py`(更新): `python` ブロック抽出、json/python 混在時の順序保持。
    - `tests/test_services/test_plotly_render_service.py`(更新): `language="python"` の dispatcher が executor を呼ぶこと(executor を Mock)。
    - `tests/test_presenters/test_panel_presenter.py`(更新): 3 モード送信時の `request_plotly_mode` 焼き込み、python モードで python spec が無く json spec のみ → fallback 通知 + JSON 描画依頼、AI 失敗時 reset、応答待ち中のモード変更が現リクエストに影響しないこと。
    - `tests/test_presenters/test_main_presenter.py`(更新): provisioning 中の status bar 表示、cancel ハンドラ呼び出しで executor が cancel_token.set すること、各例外の status bar 文言マッピング、複数 spec モード合流、設定保存。
    - `tests/test_presenters/test_settings_presenter.py`(更新): timeout 往復、clamp。
    - `tests/test_views/test_side_panel_view.py`(更新 or 新規): 3 状態循環、右クリックメニュー選択、`set_plotly_mode` での外部反映。
    - `tests/test_models/test_ai_model.py`(更新): `request_plotly_mode == "python"` 時のプロンプト追記文字列スナップショット、`"off"` 時は無追記、`system_instruction` 不変。
    - `tests/mocks/mock_views.py`(更新): 3 状態 API、status bar スピナー、settings 拡張。

## Relevant Files

### 新規

- `src/pdf_epub_reader/services/plotly_sandbox/__init__.py` — allow-list 定数 / 例外型
- `src/pdf_epub_reader/services/plotly_sandbox/venv_provisioner.py`
- `src/pdf_epub_reader/services/plotly_sandbox/runner.py` — venv 内で実行される `-I -S` runner
- `src/pdf_epub_reader/services/plotly_sandbox/executor.py`
- `src/pdf_epub_reader/services/plotly_sandbox/cancel.py`
- 上記対応のテスト群(Step 17)

### 変更

- [src/pdf_epub_reader/dto/plot_dto.py](src/pdf_epub_reader/dto/plot_dto.py) — `language` 拡張、`AnalysisRequest.request_plotly_mode`、`PlotlyRenderRequest`
- [src/pdf_epub_reader/utils/config.py](src/pdf_epub_reader/utils/config.py) — モード移行コード、timeout 追加
- [src/pdf_epub_reader/models/ai_model.py](src/pdf_epub_reader/models/ai_model.py) — Python モード文言注入
- [src/pdf_epub_reader/services/plotly_extraction_service.py](src/pdf_epub_reader/services/plotly_extraction_service.py)
- [src/pdf_epub_reader/services/plotly_render_service.py](src/pdf_epub_reader/services/plotly_render_service.py)
- [src/pdf_epub_reader/views/side_panel_view.py](src/pdf_epub_reader/views/side_panel_view.py) — 3 状態化
- [src/pdf_epub_reader/views/settings_dialog.py](src/pdf_epub_reader/views/settings_dialog.py)
- [src/pdf_epub_reader/views/main_window.py](src/pdf_epub_reader/views/main_window.py) — status bar スピナー
- [src/pdf_epub_reader/interfaces/view_interfaces.py](src/pdf_epub_reader/interfaces/view_interfaces.py)
- [src/pdf_epub_reader/presenters/panel_presenter.py](src/pdf_epub_reader/presenters/panel_presenter.py)
- [src/pdf_epub_reader/presenters/main_presenter.py](src/pdf_epub_reader/presenters/main_presenter.py)
- [src/pdf_epub_reader/presenters/settings_presenter.py](src/pdf_epub_reader/presenters/settings_presenter.py)
- [src/pdf_epub_reader/dto/ui_text_dto.py](src/pdf_epub_reader/dto/ui_text_dto.py)
- [src/pdf_epub_reader/resources/i18n.py](src/pdf_epub_reader/resources/i18n.py)
- [src/pdf_epub_reader/services/translation_service.py](src/pdf_epub_reader/services/translation_service.py)
- [tests/mocks/mock_views.py](tests/mocks/mock_views.py)
- 既存の Phase 1 テスト群(Step 17 参照)

### 依存追加

- `pyproject.toml`: ランタイム依存に `kaleido` を追加(plotly は Phase 1 で追加済前提)。allow-list の `numpy/pandas/scipy/sympy` は **ホスト依存ではなく venv 側だけに必要**(pip install 経由)。`platformdirs` は既存依存。

## Verification

1. **ユニット**: `uv run pytest tests/test_services/test_plotly_sandbox_provisioner.py tests/test_services/test_plotly_extraction_service.py tests/test_services/test_plotly_render_service.py -q`
2. **Sandbox 統合**: `uv run pytest tests/test_services/test_plotly_sandbox_executor.py -q -m slow`(実 subprocess。CI では別ジョブ)
3. **Presenter 回帰**: `uv run pytest tests/test_presenters -q`
4. **全体**: `uv run pytest tests/ -q`
5. **手動確認** (`uv run python -m pdf_epub_reader`):
   - 初回 Python モード送信 → status bar に provisioning メッセージ → venv 構築完了後にスクリプト実行 → 描画
   - 2 回目以降の Python モード送信 → provisioning が走らず即時実行
   - timeout: わざと無限ループの応答(手動で stub)→ 10s で打ち切り、status bar 通知、AI 結果保持
   - Cancel: status bar の cancel リンクをクリック → 即停止、結果ウィンドウ非表示
   - 禁止 import (`import os`) を含む応答 → runtime error 通知、ログパス tooltip
   - Python モードで Python ブロックが無く JSON ブロックがある応答 → JSON にフォールバック描画 + 通知
   - JSON モード(既存挙動)と OFF モードに退行が無いこと
   - Settings の timeout を 5s に変更 → 反映
   - 旧 `plotly_visualization_enabled: true` の設定ファイルから起動 → `mode="json"` に正規化
   - サイドパネル 📊 トグルの 3 状態循環、右クリックメニューでの直接選択、UI 言語切替で文言追従
6. **ネガティブ**: venv 配置先が書き込み不可の状況をシミュレーション(read-only ディレクトリ)→ `SandboxProvisioningError`、アプリは継続。

## Decisions(確定)

| 論点                      | 決定                                                                                              |
| ------------------------- | ------------------------------------------------------------------------------------------------- |
| 隔離レベル                | subprocess + `-I -S` + 空 env + timeout + **専用 venv(allow-list のみ)**                          |
| Allow-list                | plotly, kaleido, numpy, pandas, scipy, sympy, math, statistics, datetime, json                    |
| インタープリタ            | `~/.gem-read/sandbox-venv`(platformdirs ベース)の専用 venv                                        |
| モード切替 UI             | サイドパネルの 📊 を **3 状態トグル**(OFF / JSON / Python)に拡張                                  |
| プロンプト注入(Python)    | 「JSON 出力を含む Python スクリプトのみ」「ネット・ファイル I/O 禁止」「allow-list 列挙」を英語で |
| runner I/O プロトコル     | stdout = Plotly JSON のみ、stderr = 診断ログ                                                      |
| timeout デフォルト        | 10 秒(設定で 1–120 秒に変更可)                                                                    |
| Python ブロック欠落時     | JSON ブロックがあれば JSON にフォールバック、無ければ静かにスキップ                               |
| 複数 spec                 | Phase 1 の `plotly_multi_spec_mode`(prompt/first_only)を流用                                      |
| Cancel UI                 | status bar にスピナー + Cancel リンク。クリックで terminate                                       |
| stderr 露出               | status bar には要約のみ。全文は `platformdirs.user_log_dir/gem-read/plotly-sandbox-*.log` に保存  |
| Phase 1 設定との互換      | 旧 `plotly_visualization_enabled` を `plotly_visualization_mode` に自動移行                       |
| `system_instruction` 改変 | 行わない(キャッシュ温存)                                                                          |

## Further Considerations

1. **kaleido を allow-list に含める意図**: 静的画像エクスポート(PNG/SVG)を sandbox 内で行えるようにする伏線。Phase 3 の保存機能で利用。Phase 2 では実行可能性を担保するためインストールするのみ。
2. **venv プロビジョニングの初回コスト**: 数十秒〜数分かかる可能性がある。初回送信時の体験低下を避けるため、**アプリ起動直後にバックグラウンドで `provisioner.ensure` を投機的実行**する選択肢があるが、ネット帯域・ストレージへの副作用があるため Phase 2 では「必要時にだけ走らせる」とする。設定に `plotly_sandbox_prefetch: bool = False` を後から足す余地あり。
3. **`pip install` 時のネットワーク要件**: オフライン環境では venv 構築が必ず失敗する。エラーメッセージで明示的に「ネット接続が必要」とユーザーに伝える i18n 文言を `plotly_sandbox_provisioning_failed_offline` として用意する。
