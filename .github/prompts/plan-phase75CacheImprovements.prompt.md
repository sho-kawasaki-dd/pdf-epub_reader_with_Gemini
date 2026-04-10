# Plan: Phase 7.5 — キャッシュ改修3件

サイドパネル + キャッシュ管理ダイアログにカウントダウン表示、キャッシュ重複作成防止、アプリ終了時のキャッシュ自動破棄の3件。方法B (`event_loop.run_app` の `on_shutdown` コールバック) を採用。

---

## Phase A: カウントダウン表示

**A-1. `ISidePanelView` Protocol 追加** — `src/pdf_epub_reader/interfaces/view_interfaces.py`

1. `start_cache_countdown(expire_time: str) -> None` — ISO 形式の `expire_time` を渡してカウントダウン開始
2. `stop_cache_countdown() -> None` — カウントダウン停止
3. `set_on_cache_expired(cb: Callable[[], None]) -> None` — 0到達時のコールバック登録

**A-2. `SidePanelView` 実装** — `src/pdf_epub_reader/views/side_panel_view.py`

1. `__init__` で `QTimer` (`_countdown_timer`, 1000ms) と `_expire_time_utc: datetime | None` を追加
2. `start_cache_countdown`: ISO→`datetime` パース → `_expire_time_utc` 保持 → `QTimer.start()`
3. `stop_cache_countdown`: `QTimer.stop()` → `_expire_time_utc = None`
4. `_on_countdown_tick`: 残り秒を算出 → 0以下なら stop + `_on_cache_expired` コールバック発火 + ラベル「期限切れ」。0超なら `HH:MM:SS` でラベル更新
5. カウントダウンテキストの連携設計: `_cache_base_text` を保持。`update_cache_status_brief(text)` は `_cache_base_text = text` をセットしラベルを即時更新。`_on_countdown_tick` は `_cache_base_text + " — 残り H:MM:SS"` をラベルに追記
6. 表示例: `キャッシュ: ON (12345 tokens) — 残り 0:42:15`

**A-3. `PanelPresenter` 更新** — `src/pdf_epub_reader/presenters/panel_presenter.py`

1. `__init__` で `view.set_on_cache_expired(self._on_cache_expired)` を登録
2. `update_cache_status(status)` 内: active + `expire_time` → `view.start_cache_countdown(expire_time)` / inactive → `view.stop_cache_countdown()`
3. `set_on_cache_expired_handler(cb)` / `_on_cache_expired()` 新設: MainPresenter へコールバック委譲

**A-4. `MainPresenter` 更新（期限切れ自動リフレッシュ）** — `src/pdf_epub_reader/presenters/main_presenter.py`

1. `__init__` で `panel_presenter.set_on_cache_expired_handler(self._on_cache_expired)` を登録
2. `_on_cache_expired` → `asyncio.ensure_future(self._do_cache_expired())`
3. `_do_cache_expired`: `await ai_model.get_cache_status()` → `panel_presenter.update_cache_status(status)` + ステータスバーに「キャッシュの有効期限が切れました」

**A-5. `ICacheDialogView` Protocol 追加** — `src/pdf_epub_reader/interfaces/view_interfaces.py` _（A-1 と並列可）_

1. `start_countdown(expire_time: str) -> None`
2. `stop_countdown() -> None`

**A-6. `CacheDialog` 実装** — `src/pdf_epub_reader/views/cache_dialog.py` _（A-5 依存）_

1. `QTimer` + `_expire_time_utc` で `_ttl_label` を毎秒更新（HH:MM:SS 形式）
2. `accept()` / `reject()` オーバーライドで `stop_countdown()` を自動呼出し

**A-7. `CachePresenter` 更新** — `src/pdf_epub_reader/presenters/cache_presenter.py` _（A-5, A-6 依存）_

1. `show()` 内: `cache_status.is_active and cache_status.expire_time` → `view.start_countdown(expire_time)` を呼ぶ

---

## Phase B: キャッシュ重複作成防止 _（Phase A と独立・並列可）_

**B-1. `MainPresenter._do_cache_create` にガード追加** — `src/pdf_epub_reader/presenters/main_presenter.py`

1. 先頭に: `status = await self._ai_model.get_cache_status()` → `if status.is_active:` → `await self._ai_model.invalidate_cache()` → 既存キャッシュを削除してから `create_cache` 続行

---

## Phase C: アプリ終了時のキャッシュ自動破棄 — 方法B _（Phase A, B と独立・並列可）_

**C-1. `run_app` に `on_shutdown` パラメータ追加** — `src/pdf_epub_reader/infrastructure/event_loop.py`

1. `run_app(app_main, *, on_shutdown=None)` — `on_shutdown: Callable[[], Awaitable[None]] | None`
2. `finally` ブロック内、`shutdown_asyncgens` の前に: `if on_shutdown: loop.run_until_complete(on_shutdown())`（try/except で囲み、エラーでもクリーンアップを妨げない）

**C-2. `app.py` でシャットダウンフックを渡す** — `src/pdf_epub_reader/app.py`

1. モジュールレベルに `_ai_model_ref: AIModel | None = None` を追加
2. `_app_main()` 内で `nonlocal _ai_model_ref` → `_ai_model_ref = ai_model` で参照を保持
3. `async def _shutdown()` を新設: `if _ai_model_ref: await _ai_model_ref.invalidate_cache()`（try/except でラップ）
4. `run_app(_app_main, on_shutdown=_shutdown)` に変更

---

## Phase D: テスト _（Phase A, B, C すべて完了後）_

**D-1. Mock 更新** — `tests/mocks/mock_views.py`

- `MockSidePanelView`: `start_cache_countdown` / `stop_cache_countdown` / `set_on_cache_expired` + `simulate_cache_expired()` ヘルパー追加
- `MockCacheDialogView`: `start_countdown` / `stop_countdown` を calls に記録

**D-2. test_panel_presenter.py に3件追加** — `tests/test_presenters/test_panel_presenter.py`

- `test_update_cache_status_starts_countdown`: active + expire_time → `start_cache_countdown` が呼ばれること
- `test_update_cache_status_stops_countdown_when_inactive`: inactive → `stop_cache_countdown` が呼ばれること
- `test_cache_expired_fires_handler`: `simulate_cache_expired()` → handler が発火すること

**D-3. test_main_presenter.py に3件追加** — `tests/test_presenters/test_main_presenter.py`

- `test_cache_expired_refreshes_status`: expired コールバック → `get_cache_status` + `update_cache_status` が呼ばれること
- `test_cache_create_invalidates_existing_first`: active なキャッシュがある状態で `_do_cache_create` → `invalidate_cache` が `create_cache` より先に呼ばれること
- `test_shutdown_calls_invalidate`: `_shutdown()` 関数の単体テスト

**D-4. test_cache_presenter.py に1件追加** — `tests/test_presenters/test_cache_presenter.py`

- `test_active_cache_starts_countdown`: active + expire_time → `start_countdown` が呼ばれること

---

## Verification

1. `pytest tests/ -v` — 全テスト（既存+新規10件）がパス
2. 手動: キャッシュ作成 → サイドパネルに `H:MM:SS` カウントダウン → 0到達で自動リフレッシュ → OFF 表示
3. 手動: キャッシュ管理ダイアログ → タブ1の残りTTLが毎秒更新
4. 手動: キャッシュ active で「作成」ボタン → 旧削除 → 新規作成
5. 手動: キャッシュ active でアプリ終了 → ログに invalidate_cache 呼出し確認

## Decisions

- 表示形式: `H:MM:SS`（例: `1:12:15`、`0:05:30`）で統一
- 0到達時: Presenter 経由で `get_cache_status` を自動リフレッシュし UI 更新
- アプリ終了時: 確認ダイアログなしで常に自動破棄
- 重複防止: `_do_cache_create` 先頭で `invalidate_cache` ガード
- `_format_remaining()` は各 View にインライン実装（共通ヘルパー切り出しは過剰）
- タブ2一覧テーブルの Expire 列は静的 ISO 表示のまま
