# Plan: Plotly Visualization Phase 3

Phase 1 (JSON-only) と Phase 2 (sandboxed Python) の実装完了を前提に、UX 拡張機能（タブ集約 PlotWindow、保存、Markdown export 統合、spec 一覧、再描画、コピー）を追加する。

## TL;DR

- 現行の「spec ごとに別ウィンドウ」を **「リクエスト 1 回 = PlotWindow 1 つ・複数 spec はタブ」** へ転換。
- `plotly_multi_spec_mode` を `prompt | first_only | all_tabs (新・既定)` の 3 値へ拡張。
- PlotWindow に **左側 spec 一覧ペイン（Splitter, トグルで開閉）** とタブごとのツールバー（再描画・コピー・保存）を追加。
- kaleido を使う PNG コピー / PNG・SVG 保存 / Markdown export 用画像書き出しは **GUI スレッドを塞がない非同期処理** とする。
- **非同期ワーカーの実装要件 (PySide6)**:
  - kaleido による画像生成など、UIをブロックする処理は `QThreadPool.globalInstance()` と `QRunnable` を用いたタスクベースの非同期処理として実装すること。
  - ワーカーからメインスレッドへの完了/エラー通知は、必ず `QObject` を継承した専用のシグナルクラス（例: `WorkerSignals`）を定義し、シグナル・スロット機構を介した完全なイベント駆動で行うこと。
  - 処理待ちのために `time.sleep()` やローカルの `QEventLoop.exec()` などを用いた同期的（ブロック的）な待機処理を実装することは **厳禁** とする。
  - Markdown export の処理フローは、画像書き出しタスクをワーカーに投げ、その「全完了シグナル」を受け取るスロット内で Markdown 本文の構築と保存を実行するステートマシン的な流れとすること。
- 保存形式は HTML / JSON は必須、PNG / SVG は **`gem-read[plotly-export]` extras** の kaleido が入っている時のみ有効化。
- Markdown export に Plotly を **PNG として並置埋め込み**。kaleido 不在ならスキップ + status bar 通知。設定 `export_include_plotly_visualizations: bool = True` を新設。

## Phases & Steps

### Phase 3A: PlotWindow タブ化 + spec 一覧ペイン

1. **DTO 整理**: `dto/plot_dto.py` の `PlotlyRenderRequest` を踏襲しつつ、PlotWindow が表示時点で持つべき **タブ単位の状態** を表す内部値オブジェクト（必要なら presenter 内 dataclass）を追加。`AnalysisResult` への spec 永続化は Phase 3B で行うため、3A では現行の push 経路のみ。
2. **PlotWindow 構造変更** ([views/plot_window.py](src/pdf_epub_reader/views/plot_window.py)):
   - `QSplitter`(Horizontal): 左 = `QListWidget` (spec 一覧)、右 = `QTabWidget`。
   - 左ペインは `QToolButton` のトグルで折りたたみ可能（既定で展開）。状態は Phase 3 ではウィンドウ寿命のみ保持し、アプリ横断の永続化は Optional な Phase 3.1 で検討する。
   - 各タブは `QWidget` ラッパ: 上部 `QToolBar`（再描画・コピー・保存）+ 下部 `QWebEngineView`。
   - 公開 API を `show_figure_html(html, title)` から **`show_figures(tab_payloads: list[PlotTabPayload])`** に変更。`PlotTabPayload(title, html, spec_source_text, spec_language, spec_index, render_error)` を `dto/plot_dto.py` に追加。
   - 既存の一時ファイル方式は維持（タブ × spec ごとに 1 ファイル）。`TemporaryDirectory` をウィンドウ単位で 1 つ持ち、**初回表示・再描画のたびに新しいファイル名を発行**して `QWebEngineView` のローカルファイルキャッシュを回避する。
   - 一覧クリックで `setCurrentIndex` 同期、タブ切替時も一覧選択を同期（双方向）。
3. **PlotWindow ツールバー（再描画・コピー）**:
   - **再描画**: 現タブの `spec_source_text` / `spec_language` を `MainPresenter` に渡して再パース・再描画。Phase 2 sandbox を踏襲（Python 時のみ sandbox 経由）。再描画結果は**毎回別ファイル名の HTML**として書き出して同一タブへ再ロードする。
   - **コピー > spec source**: `QApplication.clipboard().setText(spec_source_text)`。
   - **コピー > PNG**: kaleido 不在時はメニュー項目を `setEnabled(False)` + ツールチップで理由表示。利用可なら `pio.to_image(format="png", scale=2)` の bytes を **background worker で生成**し、完了後に `QImage` に変換して `clipboard.setImage()`。処理中は当該タブのツールバーまたは status bar に進行中表示を出す。
   - 再描画ハンドラは `PlotWindow` から **コールバック注入**（`set_on_rerender_requested(cb)`）でテスト容易性を確保。`MainPresenter` が登録。
4. **multi_spec_mode 既定変更** ([utils/config.py](src/pdf_epub_reader/utils/config.py)):
   - `Literal["prompt", "first_only", "all_tabs"]`、`DEFAULT_PLOTLY_MULTI_SPEC_MODE = "all_tabs"`。
   - `normalize_plotly_multi_spec_mode` が新値を許容。未知値は既定にフォールバック。
   - 既存 config（`prompt` 値で永続化済み）は移行不要：`prompt` 値はそのまま動作し続ける。
5. **MainPresenter.\_on_plotly_render 改修** ([presenters/main_presenter.py](src/pdf_epub_reader/presenters/main_presenter.py)):
   - 旧来の「spec ごと独立 PlotWindow を生成して `_plot_windows` に積む」ロジックを廃止。
   - 新ロジック: モード分岐後の対象 spec(s) を **1 つの新 PlotWindow にタブ集約** で渡す。`prompt`/`first_only` でも常にタブ化（タブ 1 個でも一覧ペインは出す）。
   - `_plot_windows` は引き続き弱参照なしリストで保持（ライフサイクル「ユーザーが閉じるまで残る」維持）。
   - 個別タブの再描画失敗は当該タブだけエラー HTML を表示し、他タブは無事に表示。
6. **設定 UI 拡張** ([views/settings_dialog.py](src/pdf_epub_reader/views/settings_dialog.py), [presenters/settings_presenter.py](src/pdf_epub_reader/presenters/settings_presenter.py), [interfaces/view_interfaces.py](src/pdf_epub_reader/interfaces/view_interfaces.py)):
   - Visualization タブの既存ラジオに `all_tabs` を追加（既定）。
   - 表記は i18n に追加（`plotly_multi_spec_mode_all_tabs_label` 等）。
7. **i18n 追加** ([resources/i18n.py](src/pdf_epub_reader/resources/i18n.py), [services/translation_service.py](src/pdf_epub_reader/services/translation_service.py), [dto/ui_text_dto.py](src/pdf_epub_reader/dto/ui_text_dto.py)):
   - PlotWindow 用 `PlotWindowTexts` を新設: `spec_list_pane_title`, `toolbar_rerender`, `toolbar_copy_source`, `toolbar_copy_png`, `toolbar_save`, `kaleido_unavailable_tooltip`, `rerender_failed_status`, `copy_png_failed_status`, `tab_title_template`。
   - 既存パターン（`MarkdownExportTexts` と同流儀）に揃える。

### Phase 3B: 保存機能（HTML / JSON 必須・PNG / SVG extras）

8. **kaleido 可用性検出ユーティリティ** (`services/plotly_export_service.py` 新規):
   - `is_kaleido_available() -> bool`: 起動時 1 回 import 試行、結果をモジュール変数にキャッシュ。
   - `export_figure(fig, *, format, path)`: format ごとに分岐し `pio.to_image` / `pio.to_html` / `json.dumps` を呼ぶ pure 関数。format は `Literal["html", "png", "svg", "json"]`。
   - 入力 figure ではなく、`PlotlySpec` + 既復元 figure の両方を扱える形に: `export_spec(spec, fig, format, path)`。JSON は `spec.source_text` を使い round-trip ノイズを避ける（Python spec の場合は sandbox 結果 figure の `to_json()`）。
   - `kaleido` を要する処理自体は同期 pure 関数のままとし、GUI 側では `MainPresenter` / `PlotWindow` が worker 経由で呼び出して UI スレッドを塞がない。
9. **保存ダイアログ統合** (PlotWindow ツールバーの「保存」ボタン):
   - `QFileDialog.getSaveFileName` で format を拡張子から推定。filter は `"HTML (*.html);;PNG (*.png);;SVG (*.svg);;JSON (*.json)"`。
   - 初期ディレクトリは `config.export_folder`（Markdown export 流用）。空ならホームディレクトリ。
   - 既定ファイル名: `f"{タブタイトル}_{YYYYMMDDTHHMMSS}.{ext}"`（既存 `_format_filename_timestamp` を流用）。
   - kaleido 不在時は filter から PNG/SVG を除外。
   - PNG / SVG 保存は worker で実行し、完了または失敗時にのみ UI を更新する。HTML / JSON 保存は軽量なため同期のままでよい。
10. **pyproject.toml extras 追加**:

- `[project.optional-dependencies]` に `plotly-export = ["kaleido>=1.3.0"]` を追加。現在の `plotly>=6.1.1` と整合する Kaleido v1 系を前提とする。
- Kaleido v1 は Chrome / Chromium を同梱しないため、実行環境に既存ブラウザが必要であること、未導入時の導入手順を README に注記する。
- 既定インストールでは kaleido は入らない。

11. **PlotWindow 起動時の能力検出**:
    - `MainPresenter` で `is_kaleido_available()` を 1 回呼び、`PlotWindow` に `set_kaleido_available(bool)` で注入。PlotWindow はそれに従い PNG コピー / PNG・SVG 保存項目を有効/無効化。

### Phase 3C: Markdown export への Plotly 埋め込み

12. **AnalysisResult への spec 保持**:
    - 現状 `AnalysisResult` は spec を持たない。Markdown export 時に再現するため、`PanelPresenter.export_state` の経路に `plotly_specs: list[PlotlySpec]` を **追加情報として持たせる**（DTO 拡張ではなく presenter の `ExportState` 側へ。PR 影響範囲を絞る）。
    - `_on_plotly_render` 直前の抽出結果を `PanelPresenter` が保持し、`export_state` 取得時に同梱する。
13. **MarkdownExportPayload 拡張** ([services/markdown_export_service.py](src/pdf_epub_reader/services/markdown_export_service.py)):
    - `MarkdownExportPayload` に `plotly_specs: list[PlotlySpec] = field(default_factory=list)` を追加。
    - `build_markdown_export_document` に **新セクション `## Visualizations`** を追加。`config.export_include_plotly_visualizations` が True かつ specs が 1 件以上の時のみ。

- 各 spec を `![alt]({markdown_stem}_plots/plot_{idx}.png)\n` の Markdown 画像として埋め込む。alt は spec.title or `f"Plot {idx+1}"`。

14. **画像書き出し**:

- `MainPresenter._do_export_markdown` で Markdown 本文書き出しの前に、`config.export_include_plotly_visualizations` かつ kaleido 利用可能なら **最終的に書き出す Markdown ファイル名の stem を基準に** **`{export_dir}/{markdown_stem}_plots/plot_{idx}.png`** を書き出す。
- asset ディレクトリは export 実行単位で Markdown 本体と 1:1 に対応させ、画像ファイル名はディレクトリ内で `plot_{idx}.png` の固定命名とする。これにより過去 export の画像混入を避けつつ、追加のクリーンアップ処理を不要にする。
- PNG 書き出しは worker でまとめて実行し、完了後に Markdown 本文を書き出す。重い figure が含まれても GUI スレッドをブロックしないことを優先する。
- kaleido 不在 → 画像書き出しをスキップし、Markdown には Visualizations セクションを **書かない**（リンク切れ防止）。同時に status bar に「Plotly 可視化はスキップされました（kaleido 未インストール）」を **副メッセージとして** 通知。export 自体は成功扱い。
- Python spec で sandbox 失敗した spec はその spec のみスキップ。

15. **設定追加** ([utils/config.py](src/pdf_epub_reader/utils/config.py)):
    - `export_include_plotly_visualizations: bool = True`。
    - 設定 UI: Markdown export タブに既存トグル群と同列のチェックボックスを追加。
16. **i18n 追加**: `MarkdownExportTexts` に `visualizations_section_title`, `plotly_skipped_kaleido_unavailable_message` を追加。

### Phase 3D: テスト

17. **既存テストの修復**:
    - `tests/test_presenters/test_main_presenter.py`: `_on_plotly_render` の挙動が「spec ごと独立 PlotWindow」から「タブ集約 1 ウィンドウ」に変わるため、関連テストを更新。
    - `tests/mocks/mock_views.py`: `MockPlotWindow` の API を `show_figures(tab_payloads)` に変更し、再描画・コピー・保存の呼び出し記録を追加。
18. **新規テスト**:
    - `tests/test_services/test_plotly_export_service.py`: format ごとの分岐、JSON は spec.source_text パススルー、kaleido 不在時の例外型。

- `tests/test_presenters/test_main_presenter.py` 追加ケース: `all_tabs` モード、再描画ハンドラ呼び出し、再描画時に新しい HTML ファイル名が使われること、PNG コピー/PNG・SVG 保存が worker 経由で起動されること、PNG コピー時に kaleido 不在ならエラー status、Markdown export 時に Plotly セクションが入る/入らない条件、kaleido 不在時の skip 通知。
- `tests/test_services/test_markdown_export_service.py`: `plotly_specs` 入りの Visualizations セクションレンダリング、設定 OFF / specs 空 / kaleido 不在パスでセクション省略。
- `tests/test_presenters/test_settings_presenter.py`: `all_tabs` モード往復、`export_include_plotly_visualizations` 往復。
- `tests/test_presenters/test_panel_presenter.py`: `export_state.plotly_specs` の同梱と reset。

19. **PlotWindow 単体テスト**:
    - 既存に PlotWindow のテストファイルが無ければ `tests/test_views/test_plot_window.py` を新設。Qt 依存のためヘッドレス化に注意（既存テスト群と同パターンで `QApplication` fixture を再利用）。一覧/タブ同期、ツールバーボタンの enabled 状態（kaleido フラグ別）を検証。

## Relevant files

### 変更

- [src/pdf_epub_reader/views/plot_window.py](src/pdf_epub_reader/views/plot_window.py) — Splitter + List + TabWidget 化、ツールバー追加（Step 2-3）
- [src/pdf_epub_reader/presenters/main_presenter.py](src/pdf_epub_reader/presenters/main_presenter.py) — `_on_plotly_render` 改修、再描画/保存ハンドラ、Markdown export に画像書き出しを追加（Step 5, 11, 14）
- [src/pdf_epub_reader/presenters/panel_presenter.py](src/pdf_epub_reader/presenters/panel_presenter.py) — `export_state.plotly_specs` 同梱、reset 経路（Step 12）
- [src/pdf_epub_reader/presenters/settings_presenter.py](src/pdf_epub_reader/presenters/settings_presenter.py) — `all_tabs` ラジオ、`export_include_plotly_visualizations` 往復（Step 6, 15）
- [src/pdf_epub_reader/services/markdown_export_service.py](src/pdf_epub_reader/services/markdown_export_service.py) — Visualizations セクション追加（Step 13）
- [src/pdf_epub_reader/utils/config.py](src/pdf_epub_reader/utils/config.py) — `all_tabs` リテラル、`export_include_plotly_visualizations`（Step 4, 15）
- [src/pdf_epub_reader/dto/plot_dto.py](src/pdf_epub_reader/dto/plot_dto.py) — `PlotTabPayload` 追加（Step 2）
- [src/pdf_epub_reader/dto/ui_text_dto.py](src/pdf_epub_reader/dto/ui_text_dto.py) — `PlotWindowTexts` 追加 + Markdown export texts 拡張（Step 7, 16）
- [src/pdf_epub_reader/resources/i18n.py](src/pdf_epub_reader/resources/i18n.py), [services/translation_service.py](src/pdf_epub_reader/services/translation_service.py) — 新文言（Step 7, 16）
- [src/pdf_epub_reader/interfaces/view_interfaces.py](src/pdf_epub_reader/interfaces/view_interfaces.py) — `IPlotWindow` プロトコル拡張、設定ダイアログのアクセサ追加（Step 2, 15）
- [src/pdf_epub_reader/views/settings_dialog.py](src/pdf_epub_reader/views/settings_dialog.py) — Visualization タブ + Markdown export タブにチェックボックス（Step 6, 15）
- [pyproject.toml](pyproject.toml) — `[project.optional-dependencies]` に `plotly-export = ["kaleido>=0.2"]`（Step 10）
- [tests/mocks/mock_views.py](tests/mocks/mock_views.py) — `MockPlotWindow` 改修（Step 17）
- [tests/test_presenters/test_main_presenter.py](tests/test_presenters/test_main_presenter.py), [test_panel_presenter.py](tests/test_presenters/test_panel_presenter.py), [test_settings_presenter.py](tests/test_presenters/test_settings_presenter.py) — 既存ケース更新 + 追加（Step 17-18）
- [tests/test_services/test_markdown_export_service.py](tests/test_services/test_markdown_export_service.py) — Visualizations セクション（Step 18）

### 新規

- `src/pdf_epub_reader/services/plotly_export_service.py` — format 抽象化と kaleido 検出（Step 8）
- `tests/test_services/test_plotly_export_service.py`（Step 18）
- `tests/test_views/test_plot_window.py`（Step 19）

## Verification

1. **pure service 単体**: `uv run pytest tests/test_services/test_plotly_export_service.py tests/test_services/test_markdown_export_service.py -q`
2. **presenter 単体**: `uv run pytest tests/test_presenters -q`
3. **全体回帰**: `uv run pytest tests/ -q`
4. **手動 (kaleido あり / なし両環境)**:
   - kaleido **あり**:
     - 複数 spec → 1 ウィンドウ・タブ集約・spec 一覧と双方向同期
       - 各タブで再描画・spec ソースコピー・PNG コピー・HTML/PNG/SVG/JSON 保存（拡張子に応じて分岐）
       - 再描画のたびに新しい一時 HTML ファイルが使われ、`QWebEngineView` に古い内容が残らない
       - PNG コピー / PNG・SVG 保存 / Markdown export 用 PNG 書き出し中も UI が固まらない
       - Markdown export → 最終出力 Markdown と 1:1 対応の `{markdown_stem}_plots/plot_*.png` が並置され、Markdown に `## Visualizations` セクションと画像参照が入る
     - 設定 `all_tabs` / `prompt` / `first_only` 切替の挙動
     - 設定 `export_include_plotly_visualizations` を OFF → セクション/画像とも生成されない
     - Python spec の再描画が sandbox を再走させて反映される
   - kaleido **なし**:
     - PNG コピー / PNG・SVG 保存ボタンが無効化＋ツールチップ表示
     - HTML / JSON 保存は通常動作
     - Markdown export 実行時 → セクション省略 + status bar に skip 通知（export 自体は成功）
   - UI 言語切替後にツールバー / ダイアログ / セクション見出しが追従
   - 既存ドキュメント / リクエスト切替で PlotWindow が破壊されず残存

## Decisions（質問結果から確定）

- **タブ戦略**: リクエスト 1 回 = PlotWindow 1 つ。複数 spec はタブで集約。
- **multi_spec_mode**: `prompt | first_only | all_tabs (新・既定)` の 3 値。
- **保存形式**: HTML / PNG / SVG / JSON すべてサポート。PNG/SVG は kaleido 必須。
- **kaleido**: extras `gem-read[plotly-export]`。未インストール時は機能を無効化（クラッシュなし）。kaleido を使う PNG コピー / PNG・SVG 保存 / Markdown export 用 PNG 書き出しは worker 経由で非同期実行する。
- **Markdown export 埋め込み**: PNG として並置 + `export_include_plotly_visualizations: bool = True` を新設。
- **spec 一覧ペイン**: PlotWindow 内左 Splitter（折りたたみトグル）。
- **再描画スコープ**: 同一 spec の単純リロードのみ。再描画時は毎回別ファイル名の HTML を発行して `QWebEngineView` キャッシュを回避する。
- **コピー対象**: spec ソース + PNG（kaleido 必須）。
- **ライフサイクル**: 現行どおりユーザーが閉じるまで残る。
- **保存初期ディレクトリ**: `config.export_folder` を流用。
- **Markdown asset 命名**: asset ディレクトリは最終 Markdown ファイルの stem 基準で `{markdown_stem}_plots/` とし、配下は `plot_{idx}.png` の固定命名とする。
- **PlotWindow UI 状態永続化**: Phase 3 では非永続。Splitter 状態やペイン折りたたみ状態の永続化は Optional な Phase 3.1 とする。

## 非ゴール（Phase 3 の外）

- spec 内 JSON のインライン編集ダイアログ（再描画は元 source の単純リロードのみ）。
- kaleido 以外の代替（matplotlib/orca）。
- 全タブ一括保存・一括再描画。
- HTML を Markdown に埋め込む方式（PNG に統一）。
- ブラウザ拡張 / desktop_capture への横展開（pdf_epub_reader 限定）。
- PlotWindow の Splitter 状態・ペイン折りたたみ状態の永続化（Optional な Phase 3.1 で扱う）。

## Further Considerations

1. **Kaleido v1 前提**: 現行の `plotly>=6.1.1` とは整合しているため `kaleido>=1.3.0` で問題ない。ただし v1 は Chrome / Chromium 非同梱のため、extras 化とあわせて実行環境要件の明記が必要。
2. **PlotWindow タブの上限**: LLM が大量 spec を返した場合のメモリ／HTML inline サイズ。一旦上限を設けず、極端に多いケース（>10）は将来課題として残す。
3. **Markdown asset ディレクトリ命名**: source document の stem ではなく、実際に書き出す Markdown ファイル名の stem を基準に `{markdown_stem}_plots/` を作る。これにより export ごとの asset bundle を 1:1 で管理でき、古い画像の混入や追加 cleanup を避けやすい。
4. **PlotWindow UI 状態永続化**: Splitter 位置や spec 一覧ペインの開閉状態を永続化すると UX 改善の余地があるが、Phase 3 の必須要件からは外す。必要なら Optional な Phase 3.1 で `QSettings` による最小限の状態保存のみ追加する。
