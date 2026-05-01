# Plan: AI Request Cancel and Timing Status

Gemini API へのリクエストについて、`pdf_epub_reader` で以下を実現する。

- Gemini API の**応答完了までの時間**を計測し、status bar に表示する。
- AI 応答受信後から Plotly グラフが**表示されるまでの時間**を計測し、status bar に表示する。
- **進行中の AI リクエストを途中でキャンセル**できるようにする。
- 既存の Plotly sandbox cancel と整合した UI を保つ。
- **ユーザーによる request cancel では全文キャッシュを捨てない**。`invalidate_cache()` / `delete_cache()` / `_cache_name` / `_cache_model` の明示クリア経路には入らないようにする。

## TL;DR

- timing 表示は **status bar のみ** に出す。
- status 文言は以下の方針にする。
  - 実行中: 汎用表現で十分。例: `Running Gemini request...`
  - timing: `AI response: {ai_seconds} s / graph render: {graph_seconds} s`
  - cancel: `Gemini request was cancelled.`
- cancel 対象は **AI リクエストと Plotly 描画の両方**。
- cancel 後は **既存結果を残し、新規応答は反映しない**。
- AI cancel は SDK 内部の cache state を触らず、**Presenter が保持する request task をキャンセル**して UI 反映を止める。
- Plotly Python cancel は既存 `CancelToken` を継続利用し、AI request cancel とは役割を分ける。

## Goal / Non-goal

### Goal

1. 翻訳・カスタムプロンプトの AI request について、開始から応答受信までの時間を測定して status bar に表示する。
2. Plotly JSON / Python 描画について、AI 応答受信からウィンドウ表示までの時間を測定して status bar に表示する。
3. AI request 実行中は status bar に running 表示と Cancel リンクを出す。
4. Cancel 押下時は進行中 request の結果反映だけを止め、既存表示と cache state を保持する。

### Non-goal

1. Gemini SDK の HTTP リクエストを強制的に物理中断することを保証する。
2. ユーザー cancel を cache invalidation のトリガーにすること。
3. timing 情報を Markdown export や恒久 DTO に保存すること。
4. cache fallback policy 自体を再設計すること。

## Design Principles

1. **キャンセルは request 単位**。
   Presenter が保持する進行中 task を `cancel()` し、その request の UI 反映だけを止める。
2. **全文キャッシュ保全**。
   ユーザー cancel は upstream error ではないため、`invalidate_cache()` / `delete_cache()` や internal cache state の clear と切り離す。
3. **timing の責務分離**。
   - AI 応答時間: `PanelPresenter` で計測
   - Plotly 表示時間: `MainPresenter` で計測
4. **status UI の一元化**。
   既存の Plotly running UI を拡張または一般化し、AI request にも使える status surface を `MainWindow` に持たせる。
5. **既存結果を守る**。
   Cancel 時は結果欄を空にしない。新しい response だけを捨てる。

## Phases / Steps

### Phase 1: Lifecycle and Timing DTOs

1. **PanelPresenter に request lifecycle の受け口を追加**
   - `set_on_ai_request_started_handler(cb: Callable[[], None])`
     - 引数なし。MainPresenter 側でメッセージを固定するため、モード情報は渡さない。
   - `set_on_ai_request_finished_handler(cb: Callable[[float], None])`
   - `set_on_ai_request_cancelled_handler(cb: Callable[[], None])`
   - `set_on_ai_request_failed_handler(cb: Callable[[], None])`
     - AI 固有エラー（`AIKeyMissingError` 等）以外の予期しない例外（ネットワーク断、SDK 内部エラー等）が発生した際に MainPresenter の running UI を確実に解除するためのハンドラ。
   - `cancel_active_request() -> None`
   - 内部状態として `self._active_analysis_task: asyncio.Task | None` を保持する。

2. **PlotlyRenderRequest に timing 情報を追加**
   - `ai_response_elapsed_s: float | None`
   - `response_received_monotonic` は **追加しない**。`_on_plotly_render` が呼ばれた時点が AI 応答受信直後と同義なので、MainPresenter 側で `time.perf_counter()` を取れば十分。
   これにより、MainPresenter が AI response timing と graph render timing をまとめて status 表示できる。

### Phase 2: Generic Running Status UI

3. **MainWindow の Plotly 専用 running UI を汎用化**
   - 現状の `show_plotly_running(cancel_cb)` / `clear_plotly_running()` をベースに、以下のいずれかへ整理する。
     - A. `show_running_operation(message: str, cancel_cb: Callable[[], None], cancel_text: str)` / `clear_running_operation()` を新設し、既存 Plotly API は互換ラッパにする。
     - B. 既存 API を rename して AI/Plotly 共通で使う。
   - 推奨は **A**。差分を小さく保ちやすい。

4. **view interface / mocks を更新**
   - `IMainView` に汎用 running-status API を追加する。
   - `tests/mocks/mock_views.py` に対応実装を追加する。

### Phase 3: AI Request Tracking and Cancel

5. **PanelPresenter の request launch を task tracking に置換**
   - `_on_translate_requested()` の `asyncio.ensure_future(...)` を `asyncio.create_task(...)` に置換する。
   - `_on_custom_prompt_submitted()` も同様に置換する。
   - task 生成時に `self._active_analysis_task` を設定し、`finally` ブロックで必ず `None` に戻す。
   - **二重リクエスト対策**: `_active_analysis_task` が `None` でない場合は `task.cancel()` を呼んでから新しい `create_task()` を実行する。これにより前のリクエスト結果が後から反映されることを防ぐ。
   - `show_loading(False)` と `self._active_analysis_task = None` は **`finally` に一元化する**。`CancelledError` ブロック内には書かない。
   - **Race Condition 対策**: `finally` で `self._active_analysis_task = None` する際、`asyncio.current_task()` と一致するか確認してからクリアする。これにより、二重リクエスト時に古いタスクの `finally` が新しいタスクへの参照を誤消去するのを防ぐ。
     ```python
     finally:
         if self._active_analysis_task is asyncio.current_task():
             self._active_analysis_task = None
         self._view.show_loading(False)
     ```

6. **AI 応答時間を PanelPresenter で計測**
   - `time.perf_counter()` を `await self._ai_model.analyze(request)` の直前・直後で取り、`elapsed_s` を求める。
   - AI 成功時は `update_result_text(...)` を先に行い、その後 `on_ai_request_finished_handler(elapsed_s)` を呼ぶ。
   - timing は `PlotlyRenderRequest` にも載せる。そのため `_handle_plotly_response` のシグネチャを `_handle_plotly_response(request, result, elapsed_s: float)` に変更し、内部で `PlotlyRenderRequest(specs=..., origin_mode=..., ai_response_elapsed_s=elapsed_s)` を生成する。

7. **AI cancel を実装**
   - `cancel_active_request()` は、実行中 task に `task.cancel()` を送るだけにする。
   - `_do_translate()` / `_do_custom_prompt()` で `asyncio.CancelledError` を捕捉し、以下を行う。
     - export state / existing result は維持
     - `on_ai_request_cancelled_handler()` を呼ぶ（MainPresenter が status bar 更新と running UI 解除を担当する）
     - Plotly 抽出や render handler は呼ばない
     - **捕捉後は必ず `raise` する**（asyncio の慣例に従い `task.cancelled()` が正しく `True` になるようにする）
   - `show_loading(False)` と `self._active_analysis_task = None` は `finally` で処理するため `CancelledError` ブロックには書かない。
   - **予期しない例外への対応**: AI 固有エラー（`AIKeyMissingError` / `AIRateLimitError` / `AIAPIError`）以外が発生した場合、`except Exception` ブロックで `on_ai_request_failed_handler()` を呼び出す。これにより MainPresenter 側の running UI が確実に解除される。エラーメッセージは既存の汎用エラー文言を流用するか、そのまま `raise` して呼び出し元に委ねる。
     ```python
     except Exception:
         on_ai_request_failed_handler()
         raise
     ```
   - ここでは **AIModel.invalidate_cache() を呼ばない**。

### Phase 4: MainPresenter Status Orchestration

8. **AI request running status を MainPresenter が制御**
   - `MainPresenter.__init__` に以下の callback 登録を追加する。
     ```python
     self._panel_presenter.set_on_ai_request_started_handler(self._on_ai_request_started)
     self._panel_presenter.set_on_ai_request_finished_handler(self._on_ai_request_finished)
     self._panel_presenter.set_on_ai_request_cancelled_handler(self._on_ai_request_cancelled)
     self._panel_presenter.set_on_ai_request_failed_handler(self._on_ai_request_failed)
     ```
   - `_on_ai_request_started`: `cancel_text = self._translate("ai.cancel_link_text")` を取得し、`show_running_operation("Running Gemini request...", cancel_cb=self._panel_presenter.cancel_active_request, cancel_text=cancel_text)` を呼ぶ。
   - `_on_ai_request_finished(elapsed_s)`: `self._latest_ai_elapsed_s = elapsed_s` として内部に保持し、running UI を解除する。Plotly render が続く場合は status 更新を保留し、後段の timing 表示に委ねる。
   - `_on_ai_request_cancelled`: running UI を解除し、cancel 文言を表示する。
   - `_on_ai_request_failed`: running UI を解除する。エラーメッセージは `PanelPresenter` 側の既存ハンドリングが view に書き込むため、ここでは UI 解除のみを行う（二重表示を避ける）。

9. **AI timing 表示を MainPresenter で整形**
   - `_on_ai_request_finished` 受信時、`_on_plotly_render_handler` が続かない（Plotly off または spec なし）場合は即座に `show_status_message("AI response: {:.1f} s".format(elapsed_s))` を表示する。
   - Plotly render が続く場合は `_latest_ai_elapsed_s` に保持するだけにし、Steps 10・11 の描画完了時に合算して上書きする。
   - Plotly あり／なしの判定は、`_handle_plotly_response` が `on_plotly_render_handler` を呼んだかどうかで行う（呼ばれなければ即時表示）。

### Phase 5: Graph Render Timing

10. **JSON 描画時間を MainPresenter で計測**
   - `_render_and_show_plotly_figure()` の冒頭で start を取り、`window.show_figure_html(...)` 直後で end を取る。
   - status bar に `AI response: {ai_seconds} s / graph render: {graph_seconds} s` を表示する。

11. **Python 描画時間を MainPresenter で計測**
   - `_start_plotly_python_render()` では既存の Plotly cancel UI を継続使用するか、汎用 running UI を再利用する。
   - `_render_plotly_python_async()` の冒頭で start を取り、表示直前で end を取る。
   - 成功時 status は JSON 経路と同じ timing 形式でそろえる。
   - キャンセル時は既存 `SandboxCancelledError` の扱いを維持しつつ、文言だけ共通化するか検討する。

### Phase 6: Texts and i18n

12. **新規文言を DTO / i18n に追加**
   - `ai.running_message`: `Running Gemini request...`
   - `ai.cancelled_message`: `Gemini request was cancelled.`
   - `ai.timing_only`: `AI response: {ai_seconds} s`
   - `ai.timing_with_graph`: `AI response: {ai_seconds} s / graph render: {graph_seconds} s`
   - `ai.cancel_link_text`: `Cancel`
   - 必要なら Plotly running も汎用 running message に寄せる。

13. **TranslationService で新規文言 DTO を構成**
   - `PlotlyTexts` に寄せるか、AI request 用の別 DTO を新設するか決める。
   - 変更量を小さくするなら、MainPresenter が使う status 文言を `MainWindowTexts` または新規 `AnalysisStatusTexts` に追加するのが自然。

### Phase 7: Cache Safety

14. **cache invalidation 経路とユーザー cancel を分離して固定**
   - `PanelPresenter.cancel_active_request()` から `IAIModel.invalidate_cache()` へ到達しないことを確認する。
   - `AIModel.analyze()` の cache fallback ロジックはそのまま維持する。
   - コメントで「user cancel は cache ownership / invalidation と無関係」と明記する。

15. **回帰リスクの確認**
   - model 切替や明示的 cache 削除は従来どおり動くこと。
   - cancel は request 単位でのみ有効で、active cache の ownership を変更しないこと。

## Relevant Files

### Presenter / View

- `src/pdf_epub_reader/presenters/panel_presenter.py`
- `src/pdf_epub_reader/presenters/main_presenter.py`
- `src/pdf_epub_reader/views/main_window.py`
- `src/pdf_epub_reader/interfaces/view_interfaces.py`
- `tests/mocks/mock_views.py`

### DTO / Texts

- `src/pdf_epub_reader/dto/plot_dto.py`
- `src/pdf_epub_reader/dto/ui_text_dto.py`
- `src/pdf_epub_reader/resources/i18n.py`
- `src/pdf_epub_reader/services/translation_service.py`

### Model / Safety Notes

- `src/pdf_epub_reader/models/ai_model.py`
- `src/pdf_epub_reader/interfaces/model_interfaces.py`

### Tests

- `tests/test_presenters/test_panel_presenter.py`
- `tests/test_presenters/test_main_presenter.py`
- `tests/test_models/test_ai_model.py`

## Verification

1. **Presenter focused tests**
   - `uv run pytest tests/test_presenters/test_panel_presenter.py -q`
   - 追加確認:
     - AI request 開始時に active task が保持される
     - cancel で `show_loading(False)` が呼ばれる
     - cancel 後に既存結果が消えない
     - cancel request では render handler が呼ばれない

2. **MainPresenter focused tests**
   - `uv run pytest tests/test_presenters/test_main_presenter.py -q`
   - 追加確認:
     - running status と Cancel リンクが表示される
     - AI timing 表示が期待どおりの文字列になる
     - AI + graph timing 表示が `AI response: ... / graph render: ...` 形式になる
     - Plotly Python cancel と AI cancel が干渉しない

3. **AIModel regression tests**
   - `uv run pytest tests/test_models/test_ai_model.py -q`
   - 少なくとも、既存の cache fallback 系テストが壊れないことを確認する。

4. **Manual verification**
   - `uv run python -m pdf_epub_reader`
   - 確認項目:
     - 翻訳 request 開始で status bar に running + Cancel が出る
     - Cancel 押下で `Gemini request was cancelled.` が出る
     - 結果欄は前回の内容を保持する
     - AI timing が status に出る
     - Plotly JSON success で AI timing + graph timing が出る
     - Plotly Python success で AI timing + graph timing が出る
     - Plotly Python cancel は従来どおり効く
     - Cancel 後も全文 cache を再利用できる

## Decisions

- AI request 実行中の status 文言は **汎用表現**とする。
  - `Running Gemini request...`
- timing 表示の形式は **B** とする。
  - `AI response: {ai_seconds} s / graph render: {graph_seconds} s`
- cancel 後の status 文言は **B** とする。
  - `Gemini request was cancelled.`
- timing 表示は **status bar only**。
- cancel 対象は **AI request + Plotly render**。
- cancel 後は **既存結果を残す**。
- **全文 cache は request cancel では破棄しない**。

## Further Considerations

1. `IAIModel.analyze()` 自体に cancel token を通す案もあるが、今回は変更範囲を絞るため **Presenter task cancellation を優先**する。
2. 送信済み HTTP request の物理中断は SDK / transport 依存のため、今回の目的は「ユーザーが待たされず UI が先に復帰すること」と割り切る。
3. 将来的に timing を export や履歴へ載せたい場合は、`AnalysisResult` へ永続フィールドを追加する余地がある。ただし今回は status 表示だけで十分。