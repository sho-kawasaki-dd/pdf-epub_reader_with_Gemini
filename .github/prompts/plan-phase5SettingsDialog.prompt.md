## Plan: Phase 5 — Settings Dialog

AppConfig の全ユーザー設定項目を GUI で変更・保存できるモーダル設定ダイアログを MVP パターンで実装する。`ISettingsDialogView` Protocol + `SettingsPresenter` + `SettingsDialog` (QDialog) の 3 層構成。DPI 変更時は現在開いているドキュメントを即座に再レイアウト＋再レンダリングする。

---

### Decisions

| 項目 | 決定 |
|---|---|
| UI スタイル | モーダル QDialog（OK / Cancel で一括適用） |
| 起動方法 | Edit > Preferences + Ctrl+, |
| レイアウト | 2 タブ: "Rendering" / "Detection"（英語） |
| バリデーション | SpinBox/ComboBox で入力範囲制限 |
| リセット | 「Reset to Defaults」ボタン（全設定一括） |
| DPI 変更 | OK 後、即座にプレースホルダー再配置 + 再レンダリング |
| Presenter | 新規 `SettingsPresenter` を作成 |
| ダイアログ生成 | MainPresenter にファクトリ `Callable[[], ISettingsDialogView]` を注入（Qt 非依存を維持） |

---

### Steps

#### Phase A: Protocol と基盤 *(sequential)*

1. **`ISettingsDialogView` Protocol 定義** — `view_interfaces.py` に追加。set/get メソッド群 6 項目（`render_format`, `jpeg_quality`, `default_dpi`, `page_cache_max_size`, `auto_detect_embedded_images`, `auto_detect_math_fonts`）、`set_on_reset_defaults` コールバック登録、`exec_dialog() -> bool` ライフサイクルメソッド。

2. **`IMainView` に `set_on_settings_requested(cb)` 追加** — 同ファイル内。

3. **`IDocumentModel` に `update_config(config)` 追加** — `model_interfaces.py` に追加。

4. **バリデーション定数の追加** — `config.py` に `DPI_MIN=72`, `DPI_MAX=600`, `JPEG_QUALITY_MIN=1`, `JPEG_QUALITY_MAX=100`, `PAGE_CACHE_MIN=1`, `PAGE_CACHE_MAX=500`。

#### Phase B: SettingsPresenter *(depends on A)*

5. **`presenters/settings_presenter.py` を新規作成:**
   - `__init__(view, config)` — リセットコールバック登録
   - `show() -> AppConfig | None` — view に現在値 populate → `exec_dialog()` → accepted なら view から値読取→AppConfig 生成→`save_config()` で JSON 永続化→返却。cancelled は None
   - `_read_config_from_view()` — **ダイアログ外フィールド（`window_width`, `window_height`, `recent_files`）は現在 config からコピーして保持**
   - `_on_reset_defaults()` — `AppConfig()` のデフォルト値で再 populate

#### Phase C: SettingsDialog QDialog *(parallel with B)*

6. **`views/settings_dialog.py` を新規作成:**
   - `QTabWidget` 2 タブ構成
   - **Rendering タブ:** Image Format(`QComboBox`: PNG/JPEG)、JPEG Quality(`QSpinBox`: 1–100)、Default DPI(`QSpinBox`: 72–600, step=12)、Page Cache Size(`QSpinBox`: 1–500)
   - **Detection タブ:** Auto-detect embedded images / math fonts（`QCheckBox` ×2）
   - **ボタン行:** Reset to Defaults（左寄せ）、Cancel + OK（右寄せ、`QDialogButtonBox`）
   - Image Format が PNG のとき JPEG Quality をグレーアウト（値はリセットしない）
   - `exec_dialog()` → `self.exec() == QDialog.Accepted`

#### Phase D: 既存コンポーネントの統合 *(depends on A, B)*

7. **`DocumentModel.update_config(config)`** — `document_model.py` に追加。`self._config` 更新 + `self._page_cache.clear()`。

8. **`MainPresenter` 拡張** — `main_presenter.py`:
   - コンストラクタに `settings_view_factory: Callable[[], ISettingsDialogView] | None = None` 追加
   - `_on_settings_requested()`: factory → `SettingsPresenter(view, config).show()` → `_apply_config_changes(new_config)`
   - `_apply_config_changes()`: 旧 DPI 記憶 → config 更新 → `document_model.update_config()` → DPI 変更時のみ `_base_dpi`/`_render_dpi` 再計算 + `asyncio.ensure_future(self._reload_layout())`
   - `_reload_layout()`: `get_document_info()` → 新 `_base_dpi` でプレースホルダー再計算 → `view.display_pages()` → View のビューポート監視が自動で再レンダリング要求

9. **`MainWindow` に Edit メニュー追加** — `main_window.py`: "Edit" メニュー + "Preferences" アクション + `QKeySequence("Ctrl+,")` + コールバック登録メソッド。

10. **`app.py` ワイヤリング** — `settings_view_factory=lambda: SettingsDialog(main_window)` を MainPresenter に渡す。

#### Phase E: テスト *(parallel with D)*

11. **`MockSettingsDialogView`** — `mock_views.py` に追加。辞書ベースの set/get + 設定可能な `exec_dialog` 返り値。

12. **`MockDocumentModel.update_config`** — `mock_models.py` に呼び出し記録を追加。

13. **`test_settings_presenter.py` 新規作成** — OK/Cancel/Reset/ダイアログ外フィールド保持/save_config 呼び出しの検証。

14. **`test_main_presenter.py` に設定テスト追加** — DPI 変更時の再レイアウト/DPI 非変更時の再レイアウト不発生/`update_config` 呼び出しの検証。

---

### Relevant Files

**新規作成:**
- `src/pdf_epub_reader/presenters/settings_presenter.py` — SettingsPresenter
- `src/pdf_epub_reader/views/settings_dialog.py` — SettingsDialog QDialog
- `tests/test_presenters/test_settings_presenter.py` — 単体テスト

**修正:**
- `src/pdf_epub_reader/interfaces/view_interfaces.py` — `ISettingsDialogView` + `IMainView` 拡張
- `src/pdf_epub_reader/interfaces/model_interfaces.py` — `update_config` 追加
- `src/pdf_epub_reader/utils/config.py` — バリデーション定数
- `src/pdf_epub_reader/models/document_model.py` — `update_config()` 実装
- `src/pdf_epub_reader/presenters/main_presenter.py` — 設定フロー統合
- `src/pdf_epub_reader/views/main_window.py` — Edit メニュー
- `src/pdf_epub_reader/app.py` — ワイヤリング
- `tests/mocks/mock_views.py` — MockSettingsDialogView
- `tests/mocks/mock_models.py` — update_config 追加
- `tests/conftest.py` — フィクスチャ更新
- `tests/test_presenters/test_main_presenter.py` — テスト追加

---

### Verification

1. `pytest tests/test_presenters/test_settings_presenter.py -v` — 全パス
2. `pytest tests/test_presenters/test_main_presenter.py -v` — 既存テスト破壊なし + 新規テストパス
3. `pytest tests/ -v` — テストスイート全体通過
4. 手動: Edit > Preferences → 値変更 → OK → JSON ファイルに反映確認
5. 手動: DPI 変更 → OK → プレースホルダー再配置 + 再レンダリング確認
6. 手動: Detection チェックボックス変更 → 矩形選択時の挙動変化確認
7. 手動: Reset to Defaults → 全値デフォルト復帰
8. 手動: Cancel → 変更が保存されないこと
9. 手動: Ctrl+, でダイアログ起動

---

### Additional Design Decisions

1. **DPI 変更時のスクロール位置保持** — `_reload_layout()` で再レイアウト後、元のページ付近にスクロール位置を復元する。`IMainView` に `get_current_page() -> int` メソッドを追加し、`_reload_layout()` 内で現在ページ番号を記憶 → `display_pages()` 後に `scroll_to_page()` で復元する。Phase 5 スコープに含める。
2. **JPEG Quality SpinBox のグレーアウト** — PNG 選択時に Quality SpinBox を disabled（グレーアウト）にするが、値はリセットしない。PNG→JPEG 切替時に前回の quality 値がそのまま残る。これは View 層（`SettingsDialog`）内の `QComboBox.currentIndexChanged` シグナルで制御し、Presenter は関与しない。
