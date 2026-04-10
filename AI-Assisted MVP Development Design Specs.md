# **AIアシスタント向け 開発要件・アーキテクチャ設計書 (MVP版)**

## **1. プロジェクトの目的と概要**

PySide6を用いたローカルデスクトップ向けのAI連携ドキュメントビューアを開発する。PyMuPDFを用いてPDFおよびEPUBを画像としてレンダリングし、ユーザーが選択したテキストをGemini APIで解析（和訳・解説）する。また、全文のコンテキストキャッシュを利用した高度な解析機能を提供する。

本プロジェクトの最大の特徴は、**厳格なMVP (Model-View-Presenter) アーキテクチャの採用**である。自動テストの容易性と将来的な描画エンジンの差し替えを見据え、ビジネスロジックとGUI表現を完全に分離する。

## **2. 技術スタックと基本ルール**

- **GUIフレームワーク:** PySide6
- **ドキュメントエンジン:** PyMuPDF (fitz) ※PDF/EPUB両用
- **AI API:** Google Gen AI SDK (google-genai) ※新SDKを採用
- **非同期基盤:** asyncio + qasync（Qtイベントループ統合）
- **アーキテクチャ:** MVP (Model-View-Presenter) / Passive View パターン
- **言語:** Python 3.13以上 (Type Hinting, typing.Protocol を積極利用)
- **パッケージ管理:** uv / pyproject.toml
- **テスト:** pytest + pytest-asyncio

### **⚠️ AIへの厳格な指示（絶対遵守のMVPルール）**

1. **Passive Viewの徹底:** View（QWidgetの継承クラス）は「完全に受動的（馬鹿）」でなければならない。View内でデータの加工、API呼び出し、PDFの解析などのロジックを**一切書いてはならない**。
2. **依存の方向:**
   - ViewはModelを知らない。Presenterも知らない（シグナルを飛ばすだけ）。
   - PresenterはModelを知っている。また、Viewの**「インターフェース（Protocol）」**を知っている。
   - PySide6のクラス（QPixmap, QWidget, QThread等）は、**PresenterやModelに絶対にインポートしてはならない**。データの受け渡しはPythonの標準型（str, bytes, list, dataclass）で行うこと。
3. **非同期処理:** Model層の公開メソッドはすべて `async def` とする。Presenterは `await` で呼び出す。メインスレッド（GUI）をブロックしてはならない。
4. **テストの優先:** Model層はQtに依存しない純粋なPythonコードで実装し、単体テストを最優先する。Presenterも可能な限りロジックを分割し、Viewをモックしてテスト可能にする。
5. **ディレクトリ構成:** `src` レイアウトを採用し、テストコードと実装コードを明確に分離する。Model, Presenter, Viewはそれぞれ独立したサブディレクトリに配置する。
6. **ソースコードの自己文書化:** 各クラス・関数には新規参加のジュニアエンジニアがWhyまで理解できる粒度のdocstringおよびinline commentを付与し、型ヒントを活用してコードの意図を明確にする。

### **非同期処理の統一方針**

Model層は **asyncio ベースで統一** し、処理の性質に応じて内部実装を切り替える。Presenter から見た呼び出しパターンは常に `await model.method()` で統一される。

| 処理の性質    | 内部実装                                              | 具体例                                |
| ------------- | ----------------------------------------------------- | ------------------------------------- |
| **I/O-bound** | `await` でネイティブ非同期呼び出し                    | Gemini API通信、キャッシュ操作        |
| **CPU-bound** | `await loop.run_in_executor(ThreadPoolExecutor, ...)` | PyMuPDF画像レンダリング、テキスト抽出 |

Qt イベントループと asyncio の統合は `qasync` を用い、**infrastructure/ 層に隔離する**。これにより Model 層は Qt に一切依存せず、純粋な `async def` として単体テスト可能となる。

## **3. ディレクトリ構成**

`src` レイアウトを採用し、テスト時のimport汚染を防ぐ。コードの生成は以下の構造を前提とすること。

```
pdf-epub_reader_with_Gemini/
├── src/
│   └── pdf_epub_reader/             # パッケージ本体
│       ├── __init__.py
│       ├── __main__.py              # python -m pdf_epub_reader で起動可能
│       ├── app.py                   # Model, View, Presenterのインスタンス化と結合
│       │
│       ├── interfaces/              # 契約 (Contracts)
│       │   ├── __init__.py
│       │   └── view_interfaces.py   # typing.Protocol を用いたViewのインターフェース定義
│       │
│       ├── dto/                     # データ転送オブジェクト
│       │   ├── __init__.py
│       │   ├── document_dto.py      # PageData, TextSelection 等
│       │   └── ai_dto.py           # AnalysisResult, CacheStatus 等
│       │
│       ├── presenters/
│       │   ├── __init__.py
│       │   ├── main_presenter.py    # アプリ全体の進行
│       │   ├── panel_presenter.py   # サイドパネル領域の進行
│       │   ├── settings_presenter.py # 設定ダイアログの進行
│       │   └── cache_presenter.py   # キャッシュ管理ダイアログの進行
│       │
│       ├── models/                  # Qt非依存（純粋Python + asyncio）
│       │   ├── __init__.py
│       │   ├── document_model.py    # PyMuPDFによる解析・テキスト抽出ロジック
│       │   └── ai_model.py         # Gemini API通信、キャッシュ管理
│       │
│       ├── views/                   # PySide6 実装 (interfacesを満たすこと)
│       │   ├── __init__.py
│       │   ├── main_window.py       # 大枠のレイアウトとスクロールビュー
│       │   ├── side_panel_view.py   # AI結果表示、操作パネル
│       │   ├── bookmark_panel.py    # しおり（目次）ツリーパネル
│       │   ├── settings_dialog.py   # 設定ダイアログ
│       │   └── cache_dialog.py      # キャッシュ管理ダイアログ
│       │
│       ├── infrastructure/          # Qt ↔ asyncio 橋渡し
│       │   ├── __init__.py
│       │   └── event_loop.py        # qasync によるイベントループ統合 + on_shutdown コールバック
│       │
│       └── utils/
│           ├── __init__.py
│           ├── config.py            # 設定値（デフォルト値・スキーマ定義）
│           └── exceptions.py        # Model層の独自例外クラス
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # pytest共通フィクスチャ
│   ├── test_models/
│   │   ├── __init__.py
│   │   ├── test_document_model.py
│   │   └── test_ai_model.py
│   └── test_presenters/
│       ├── __init__.py
│       ├── test_main_presenter.py
│       ├── test_panel_presenter.py
│       └── test_cache_presenter.py
│
├── .env.example                     # 環境変数テンプレート（GEMINI_API_KEY等）
├── .gitignore
├── pyproject.toml
└── README.md
```

### **ディレクトリ構成の設計意図**

| ディレクトリ      | 役割                                                   | Qt依存 |
| ----------------- | ------------------------------------------------------ | ------ |
| `interfaces/`     | View の Protocol 定義。Presenter が依存する契約        | ✗      |
| `dto/`            | 層間のデータ受け渡し用 dataclass。全層が参照可能       | ✗      |
| `models/`         | ビジネスロジック。asyncio ベース。テスト最優先         | **✗**  |
| `presenters/`     | Model と View(Protocol) を仲介。async/await で呼び出し | **✗**  |
| `views/`          | PySide6 による GUI 実装。Passive View                  | ✓      |
| `infrastructure/` | qasync によるイベントループ橋渡し                      | ✓      |
| `utils/`          | 設定値・例外クラス等の共通ユーティリティ               | ✗      |

## **4. 機能要件とMVPによるデータフロー**

### **4.1. ドキュメント閲覧機能**

- **View:** PySide6の機能（QGraphicsViewなど）を用いて画像を縦に並べて表示する。ユーザーがドラッグで範囲選択したら、その「画面上の座標リスト」をシグナルでPresenterに通知する。
- **Presenter:** 受け取った座標リストをModelに渡す（`await model.extract_text(...)`）。Modelから返ってきたデータ（bytes, dataclass等）をViewに「これを表示せよ」と命令する。
- **Model:** PyMuPDFを操作し、指定されたページをレンダリング（CPU-bound → `run_in_executor`）。また、渡された座標から元のテキストデータを抽出する。

#### **レンダリングDPIとズームのアーキテクチャ**

ページ画像のレンダリング DPI とユーザーのズーム操作は **完全に分離** する。レンダリングは常に固定 DPI で行い、ズームは `QGraphicsView` のビュー変換（`setTransform` / `scale`）で制御する。これにより、ズームアウト時にも高解像度のレンダリング結果がスケール表示され、画質が維持される。

**DPI の役割分担:**

| 名前          | 値                                        | 用途                                                                  |
| ------------- | ----------------------------------------- | --------------------------------------------------------------------- |
| `_base_dpi`   | `AppConfig.default_dpi`（デフォルト 144） | シーン座標計算（プレースホルダー配置）、PDF ポイント⇔ピクセル座標変換 |
| `_render_dpi` | `_base_dpi × devicePixelRatio`            | Model への実レンダリング指示。高 DPI モニターでの物理ピクセル活用     |

- **Presenter** は初期化時に `IMainView.get_device_pixel_ratio()` で画面の DPR を取得し、`_render_dpi = int(_base_dpi * dpr)` を算出する。ズーム変更時に DPI は再計算 **しない**。
- **View** はレンダリング済み `QPixmap` に `setDevicePixelRatio(dpr)` を設定する。Qt がシーン上の論理サイズ（`_base_dpi` 相当）に自動マッピングしつつ、物理ピクセルをフル活用する。
- **ズーム変更時:** Presenter は `view.set_zoom_level(level)` を呼ぶのみ。View は `QGraphicsView.resetTransform()` + `scale(level, level)` でビュー変換を適用する。プレースホルダーの再配置やページの再レンダリングは不要。
- **座標変換:** `QGraphicsView.mapToScene()` がビュー変換を自動考慮するため、ラバーバンド選択やハイライト描画の座標変換コードは `_base_dpi / 72.0` のスケール係数をそのまま使用できる。

**高 DPI モニター対応の例:**

| 環境                      | DPR | `_base_dpi` | `_render_dpi` | A4 論理幅 (px) | A4 物理幅 (px) |
| ------------------------- | --- | ----------- | ------------- | -------------- | -------------- |
| 標準モニター (100%)       | 1.0 | 144         | 144           | 1190           | 1190           |
| Windows 150% スケーリング | 1.5 | 144         | 216           | 1190           | 1786           |
| Retina / 4K (200%)        | 2.0 | 144         | 288           | 1190           | 2381           |

### **4.2. AI解析機能とコンテキストキャッシュ**

- **View:** 「解析実行」や「全文キャッシュ有効化」ボタンが押されたら、シグナルを発火するのみ。ローディングアニメーションの開始/停止はPresenterからのメソッド呼び出し（例: `view.show_loading()`）で行う。サイドパネル上部にモデル選択用のプルダウンメニュー（QComboBox）を配置し、ユーザーが API リクエスト時に使用するモデルを設定ダイアログで選択されたモデル群の中から切り替え可能にする。
- **Presenter:** `await model.analyze(request)` で非同期呼び出し。結果の DTO（翻訳テキストやトークン数）が返ってきたら、`view.update_result_text(text)` を呼び出す。AI 関連の例外（`AIKeyMissingError`, `AIAPIError`, `AIRateLimitError`）を catch し、エラーメッセージを結果パネルに表示する。初期化時に `AppConfig.selected_models` からサイドパネルのモデルプルダウンを設定する。
- **Model:** `google-genai` SDK の `genai.Client` を使い、Gemini API と通信（I/O-bound → ネイティブ `await client.aio.models.generate_content(...)`）。API 仕様に依存する処理はすべてここにカプセル化する。API キー未設定時もインスタンス化可能とし、API 呼び出し時に `AIKeyMissingError` を送出する（ドキュメント閲覧のみの利用を妨げない）。429/5xx エラーに対しては最大3回の指数バックオフリトライ（1s→2s→4s）を行い、`google-genai` の例外は `AIAPIError`/`AIRateLimitError` にラップして Presenter に返す。

#### **Context Caching アーキテクチャ**

google-genai SDK の Explicit Caching API を用い、ドキュメント全文テキストをサーバー側にキャッシュすることで、繰り返しの解析リクエストにおけるトークンコストを削減する。

**キャッシュのライフサイクル:**

| イベント                                     | 動作                                                                                                                                |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| ユーザーが「全文キャッシュを作成」ボタン押下 | Presenter が `DocumentModel.extract_all_text()` → `AIModel.create_cache(full_text, model_name=..., display_name=...)` を順次呼出    |
| キャッシュ作成成功                           | `CacheStatus(is_active=True, ...)` をサイドパネルに反映。以降の `analyze()` で `cached_content` パラメータを自動付与                |
| キャッシュ作成失敗（トークン不足等）         | `AICacheError` を catch し、ステータスバーに通知。キャッシュなしで動作継続（自動フォールバック）                                    |
| `analyze()` でキャッシュ付きリクエスト失敗   | キャッシュを内部クリアし、キャッシュなしで 1 回リトライ                                                                             |
| ドキュメント切替                             | `open_file()` の先頭で既存キャッシュを `invalidate_cache()` で自動削除                                                              |
| サイドパネルでモデル切替                     | キャッシュがモデルに紐づくため、不一致時は確認ダイアログ → OK で invalidate、Cancel でモデル選択をリバート                          |
| 既存キャッシュがある状態で「作成」ボタン押下 | `_do_cache_create` 先頭で `get_cache_status()` → active なら `invalidate_cache()` で旧キャッシュを削除してから新規作成（Phase 7.5） |
| キャッシュ TTL のカウントダウンが 0 到達     | View の `QTimer` が 0 検出 → コールバック → Presenter が `get_cache_status()` で最新状態を取得し UI を自動リフレッシュ（Phase 7.5） |
| アプリケーション終了                         | `run_app` の `on_shutdown` コールバックで `invalidate_cache()` を呼出し、確認ダイアログなしでキャッシュを自動破棄（Phase 7.5）      |

**キャッシュの設計方針:**

- `system_instruction` はキャッシュに含めない（翻訳/カスタムプロンプトでシステム指示が異なるため、リクエスト時に個別指定）
- キャッシュ対象はドキュメント全文テキストのみ（画像はキャッシュしない）
- `display_name` に `"pdf-reader: {filename}"` プレフィックスを設定し、`list_caches()` でアプリ用キャッシュのみフィルタリング可能にする
- `analyze()` のレスポンスから `usage_metadata`（`prompt_token_count`, `cached_content_token_count`, `candidates_token_count`）を `logger.info` で出力し、キャッシュヒットを実行時に確認可能にする
- キャッシュ TTL は `AppConfig.cache_ttl_minutes`（デフォルト 60 分）で設定可能

**キャッシュ管理 UI:**

- サイドパネルにキャッシュ作成/削除のトグルボタンを配置
- メニューバー「キャッシュ(&C)」→「キャッシュ管理(&M)...」（キーバインド: **Ctrl+Shift+G**）から専用ダイアログを起動
- キャッシュ管理ダイアログは 2 タブ構成: タブ1「現在のキャッシュ」（ステータス表示＋作成/削除/TTL 更新）、タブ2「キャッシュ確認」（`list_caches()` でアプリ用キャッシュ一覧をテーブル表示＋選択行の削除）
- ダイアログ表示前に `await ai_model.list_caches()` + `await ai_model.get_cache_status()` でデータを事前取得し、`CachePresenter` に渡す（モーダル同期パターン）

**キャッシュ残り時間カウントダウン表示（Phase 7.5）:**

サイドパネルとキャッシュ管理ダイアログの両方で、キャッシュの残り時間を `H:MM:SS` 形式で 1 秒ごとにリアルタイム更新する。

| 表示場所                       | 表示形式                                                        | 0 到達時の動作                                                                                                 |
| ------------------------------ | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| サイドパネル `_cache_label`    | `キャッシュ: ON (12345 tokens) — 残り 0:42:15`                  | `_on_cache_expired` コールバック発火 → Presenter → `get_cache_status()` で自動リフレッシュ → UI OFF 表示に更新 |
| キャッシュ管理ダイアログ タブ1 | 「残り TTL:」行に `0:42:15` 表示（`_ttl_label` を毎秒更新）     | カウントダウン停止 + ラベル「期限切れ」表示                                                                    |
| キャッシュ管理ダイアログ タブ2 | 各行の Expire 列は ISO 時刻の静的表示（リアルタイム更新は不要） | ―                                                                                                              |

- **View 実装:** 各 View 内で `QTimer(1000ms)` + `_expire_time_utc: datetime` を保持し、`start_cache_countdown(expire_time: str)` / `stop_cache_countdown()` メソッドで制御。`CacheDialog` では `accept()` / `reject()` オーバーライドでタイマーを自動停止（リーク防止）
- **Presenter → View の連携:** `update_cache_status(status)` 内で `status.is_active and status.expire_time` なら `view.start_cache_countdown(expire_time)` を呼び、inactive 時は `view.stop_cache_countdown()` を呼ぶ。0 到達時のコールバック（`set_on_cache_expired`）は `PanelPresenter` → `MainPresenter` にコールバック委譲する
- **表示テキストの分離:** `update_cache_status_brief(text)` で Presenter が設定する基本テキスト（`キャッシュ: ON (12345 tokens)`）と、`_on_countdown_tick` で View が毎秒追記するカウントダウン部分（`— 残り H:MM:SS`）を `_cache_base_text` で分離管理する

#### **モデル選択アーキテクチャ**

ユーザーは設定ダイアログ（AI Models タブ）から利用可能なモデルの一覧を API 経由で取得し、使用するモデルを複数選択できる。選択されたモデル群はサイドパネルのプルダウンメニューに表示され、リクエスト単位でモデルを切り替え可能にする。

| 項目                 | 詳細                                                                                               |
| -------------------- | -------------------------------------------------------------------------------------------------- |
| デフォルトモデル     | 空文字 `""`（`AppConfig.gemini_model_name`）。初回起動時はモデル未設定状態                         |
| デフォルト選択リスト | 空リスト `[]`（`AppConfig.selected_models`）。Fetch Models 実施後にユーザーが選択                  |
| モデル一覧取得       | 設定ダイアログの「Fetch Models」ボタン押下時に `IAIModel.list_available_models()` を非同期呼び出し |
| モデル選択の永続化   | `AppConfig.selected_models: list[str]` に JSON 永続化                                              |
| リクエスト単位の指定 | `AnalysisRequest.model_name` フィールドで Presenter がモデル名を渡す                               |
| サイドパネル         | QComboBox で `selected_models` から選択。変更時にコールバックで Presenter に通知                   |
| モデル未設定時       | QComboBox を disabled にし「モデル未設定」プレースホルダーを表示。翻訳・キャッシュ作成を拒否       |

**起動時バックグラウンドモデル検証:**

`MainPresenter` は起動直後に `asyncio.ensure_future()` でバックグラウンドモデル検証を行う。UI 表示はブロックしない。

| 状態                                  | 動作                                                                            |
| ------------------------------------- | ------------------------------------------------------------------------------- |
| Fetch 成功 + `gemini_model_name` 有効 | そのまま継続                                                                    |
| Fetch 成功 + `gemini_model_name` 無効 | config をクリア + `save_config()` 永続化 + ステータス案内 + プルダウン disabled |
| API キー未設定                        | ステータス「API キーを設定してください (Preferences → AI Models)」              |
| ネットワークエラー等                  | ステータス警告 + 既存設定で続行（オフライン利用を妨げない）                     |

#### **システムプロンプトと出力言語**

システムプロンプトは `AppConfig` で設定可能とし、`{output_language}` プレースホルダーを含むテンプレート文字列とする。AIModel は API 呼び出し直前にプレースホルダーを置換する。

| 設定項目                       | AppConfig フィールド        | デフォルト値                                                                                 |
| ------------------------------ | --------------------------- | -------------------------------------------------------------------------------------------- |
| 翻訳モード用システムプロンプト | `system_prompt_translation` | 「テキストを {output_language} に翻訳。数式は LaTeX、化学式は `\ce{}`、Markdown 形式で回答」 |
| カスタムプロンプトモード用     | （固定）                    | 「{output_language} で回答してください。Markdown 形式で回答してください。」                  |
| 出力言語                       | `output_language`           | `"日本語"`                                                                                   |

これらは設定ダイアログの AI Models タブから編集可能とする。

#### **エラーハンドリングと例外階層**

AI 関連の例外はすべて `utils/exceptions.py` に定義し、Model が送出 → Presenter が catch → View に表示する流れを徹底する。

| 例外クラス                     | 送出条件                                                | Presenter の対応                                     |
| ------------------------------ | ------------------------------------------------------- | ---------------------------------------------------- |
| `AIError`                      | AI 系基底例外                                           | —                                                    |
| `AIKeyMissingError(AIError)`   | API キーが未設定のまま API 呼び出し                     | 結果パネルに「API キーが設定されていません」を表示   |
| `AIAPIError(AIError)`          | API 通信エラー一般（`status_code`, `message` 属性付き） | 結果パネルにエラー詳細を表示                         |
| `AIRateLimitError(AIAPIError)` | 429 レート制限（リトライ上限超過後）                    | 結果パネルに「API レート制限」を表示                 |
| `AICacheError(AIError)`        | キャッシュ作成失敗・トークン不足等（Phase 7 で追加）    | ステータスバーにエラー通知、キャッシュなしで動作継続 |

### **4.3. マルチモーダル矩形選択機能**

矩形選択はテキストだけでなく、数式（LaTeXコンパイル済グリフ）や埋め込み画像にも対応する。PDF内の数式はテキスト抽出だけでは構造が壊れるケースが大半であるため、選択領域をクロップ画像として Gemini Vision にマルチモーダル送信することで正確な認識を実現する。

**トークン最適化のための3段階判定:**

| 優先度 | 判定条件                                                                | クロップ画像送信                |
| ------ | ----------------------------------------------------------------------- | ------------------------------- |
| 1      | ユーザーが「画像としても送信」トグル ON（セッション内、デフォルト OFF） | **常に送る**                    |
| 2      | 埋め込み画像自動検出 ON（AppConfig 永続化）かつ画像検出                 | **自動で送る** + ステータス通知 |
| 2      | 数式フォント自動検出 ON（AppConfig 永続化）かつ数式フォント検出         | **自動で送る** + ステータス通知 |
| 3      | いずれも該当しない & トグル OFF                                         | **送らない（テキストのみ）**    |

- **View:** 「画像としても送信」チェックボックスのON/OFFをコールバックで通知するのみ。選択範囲プレビューはテキスト表示に加え、クロップ画像がある場合はサムネイルも表示する。
- **Presenter:** ユーザートグル状態と AppConfig の自動検出設定を Model に渡す。自動検出でクロップ画像が付与された場合はステータスバーでユーザーに通知する。`AnalysisRequest` に画像バイト列を含めて AI Model に引き渡す。
- **Model (DocumentModel):** PyMuPDF の `get_images()` + 矩形交差で埋め込み画像を、`get_text("dict")` のフォント情報から数式フォント（CMR/CMMI/CMSY/CMEX/Math/Symbol/STIX 等）および数学記号 Unicode 範囲を検出する。検出時またはユーザー強制時に `get_pixmap(clip=...)` でクロップ画像を生成する。
- **Model (AIModel):** `AnalysisRequest.images` が空ならテキストのみ、非空ならマルチモーダルで Gemini API を呼び出す。

### **4.4. AI回答欄の Markdown・数式レンダリング**

Gemini の応答は Markdown 形式（見出し、箇条書き、コードブロック、LaTeX 数式 `$...$` / `$$...$$`、化学式 `\ce{...}`）で返るため、サイドパネルの AI 回答欄は `QWebEngineView` + `markdown` ライブラリ + KaTeX（ローカルバンドル）で描画する。Markdown→HTML 変換は View 層の責務とし、Presenter は生の Markdown 文字列を渡すだけに徹する。KaTeX バンドルは `src/pdf_epub_reader/resources/katex/` に同梱し、最低限 `katex.min.css`、`katex.min.js`、`contrib/auto-render.min.js`、`contrib/mhchem.min.js`、`fonts/` を配置する。

### **4.5. しおり（目次）パネル**

PDF/EPUB が持つ階層型の目次 (Table of Contents) をメインウィンドウ左側に折りたたみ可能なツリーパネルとして表示し、項目クリックで該当ページへ即座にスクロールするナビゲーション機能を提供する。

**レイアウト:**

既存の 2 ペイン QSplitter（ドキュメント | AI パネル）を 3 ペイン構成に拡張する。

```
┌──────────┬──────────────────────┬──────────────┐
│  しおり   │    ドキュメント       │  AI パネル    │
│ (index 0) │     (index 1)        │  (index 2)   │
│ 折りたたみ│                      │              │
│ 可能      │   ← 既存部分 →      │              │
│           │                      │              │
└──────────┴──────────────────────┴──────────────┘
```

| 項目                   | 仕様                                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| ウィジェット           | `BookmarkPanelView`（`QWidget` + `QTreeWidget`）                                                                                |
| 配置                   | QSplitter index 0（左端）。コンストラクタ引数として MainWindow に注入（既存 SidePanelView と同じパターン）                      |
| 初期幅                 | `BOOKMARK_PANEL_WIDTH = 200`（`utils/config.py` に定数追加）                                                                    |
| 折りたたみ             | `QSplitter.setCollapsible(0, True)`。ドキュメントペイン（index 1）は折りたたみ不可                                              |
| 初期状態               | 幅 0 で折りたたみ。文書を開いて目次がある場合に自動で 200px 幅に展開                                                            |
| トグル                 | 「表示(&V)」メニュー新設 → 「しおり(&B)」（`Ctrl+B`、`setCheckable(True)`）。トグル時はドキュメント/AI パネルの現在比率を維持   |
| 目次なし文書           | `display_toc([])` で空ツリー。パネルは折りたたみ状態のまま                                                                      |
| ツリー階層構築         | `ToCEntry.level` を使用したスタックベースの親子関係構築。各 `QTreeWidgetItem` の `UserRole` に `page_number`（0-indexed）を格納 |
| 初期展開状態           | 第 1 レベルのみ展開（`collapseAll()` → トップレベル項目のみ `setExpanded(True)`）                                               |
| 項目クリック時         | コールバックで Presenter に `page_number` を通知 → `scroll_to_page()` を再利用してページ先頭へスクロール                        |
| 現在ページのハイライト | なし（Phase 8 スコープ外）                                                                                                      |

**MVP データフロー:**

- **Model:** 変更なし。`DocumentModel._open_document_sync()` が PyMuPDF の `doc.get_toc()` から `ToCEntry(title, page_number, level)` のリストを抽出し、`DocumentInfo.toc` に格納する処理は実装済みである。
- **Presenter:** `MainPresenter.open_file()` で `doc_info.toc` を取得し、`view.display_toc(doc_info.toc)` で View に渡す。`set_on_bookmark_selected` で登録されたコールバックで、クリック時に `view.scroll_to_page(page_number)` を呼び出す。
- **View:** `BookmarkPanelView` が `QTreeWidget` で目次をツリー表示する。`MainWindow` が `display_toc()` / `set_on_bookmark_selected()` を `IMainView` Protocol のメソッドとして実装し、しおりパネルの表示/非表示制御とコールバック委譲を行う。

**IMainView Protocol 追加メソッド:**

| メソッド                                                      | 役割                                               |
| ------------------------------------------------------------- | -------------------------------------------------- |
| `display_toc(entries: list[ToCEntry]) -> None`                | 目次データをしおりパネルに表示し表示状態を自動制御 |
| `set_on_bookmark_selected(cb: Callable[[int], None]) -> None` | しおり項目クリック時のコールバック登録             |

### **4.6. 非同期処理のアーキテクチャ図**

```
┌─────────────────────────────────────────────────┐
│  Qt Event Loop (メインスレッド)                    │
│  ┌───────────┐    Signal     ┌───────────────┐  │
│  │   View    │ ──────────→  │  Presenter    │  │
│  │ (PySide6) │ ←────────── │  (await)      │  │
│  └───────────┘  メソッド呼出  └───────┬───────┘  │
│                                      │ await    │
│  ┌─────────────────┐                 ↓          │
│  │  infrastructure/ │         ┌─────────────┐   │
│  │  qasync          │ ◄─────  │   Model     │   │
│  │  (ループ統合)     │         │ (async def) │   │
│  └─────────────────┘         └──────┬──────┘   │
│                                      │          │
└──────────────────────────────────────┼──────────┘
                                       │
                    ┌──────────────────┼──────────────┐
                    │                  │              │
              ┌─────▼─────┐    ┌──────▼──────┐       │
              │ await     │    │ run_in_     │       │
              │ (native)  │    │ executor    │       │
              │ I/O-bound │    │ CPU-bound   │       │
              └─────┬─────┘    └──────┬──────┘       │
                    │                  │   Worker Thread
                    ▼                  ▼              │
              Gemini API         PyMuPDF (fitz)       │
                    └──────────────────┴──────────────┘
```

## **5. 設定と秘匿情報の管理**

- APIキー等の秘匿情報は **環境変数** で管理する。`.env` ファイル + `python-dotenv` を使用し、`.env` は `.gitignore` に含める。
- `utils/config.py` にはデフォルト値やスキーマ定義のみを記述する。秘匿情報そのものをハードコードしてはならない。
- `.env.example` にテンプレートを用意し、必要な環境変数名を明示する。

## **6. 開発フェーズ（AIへのタスク指示用）**

- **Phase 0: プロジェクト構成の作成:** ディレクトリ構成、`__init__.py`、`pyproject.toml` の依存定義、`.env.example`、`conftest.py` 等のスキャフォールドを作成する。
- **Phase 1: インターフェースとDTOの定義:** `interfaces/view_interfaces.py` に Protocol を用いてViewが持つべきメソッドを定義する。`dto/` にデータ転送オブジェクトを定義する。その後、GUIを使わずにコンソール出力だけで動く「ダミーのView」とPresenterを作成し、ロジックの流れを確認する。
- **Phase 2: ViewのPySide6実装:** Phase 1で定義したインターフェースを満たす `views/main_window.py` 等を実装し、`infrastructure/event_loop.py` でqasyncを設定、Presenterと結合する。ズームは `QGraphicsView.setTransform()` によるビュー変換方式とし、DPI 再計算による再レンダリング方式は採用しない。`IMainView` に `get_device_pixel_ratio() -> float` を定義し、Presenter が高 DPI 環境でのレンダリング DPI を算出できるようにする。View は `QPixmap.setDevicePixelRatio()` を設定して物理ピクセルを活用する。
- **Phase 3: Modelの実装 (PyMuPDF):** `document_model.py` を実装し、PDFの画像レンダリング（`run_in_executor`）と仮想スクロール向けのデータ供給、および座標からのテキスト抽出を完成させる。Phase 3 では `utils/config.py` に `AppConfig` dataclass と JSON 永続化を導入し、レンダリング設定（画像フォーマット PNG/JPEG 切替、JPEG 品質、キャッシュサイズ、デフォルト DPI 等）をコードレベルで変更可能にする。`AppConfig.default_dpi`（デフォルト 144）は Presenter が実際のレンダリング DPI 算出に使用する基準値であり、Model はこの値に `devicePixelRatio` を乗じた `_render_dpi` で描画する。
- **Phase 4: マルチモーダル矩形選択の実装:** 矩形選択をテキスト専用からマルチモーダル（テキスト＋画像＋数式）に拡張する。DTO に `SelectionContent` を新設し、DocumentModel に `extract_content` メソッド（埋め込み画像検出・数式フォント検出・クロップ画像生成）を追加する。`AppConfig` に `auto_detect_embedded_images` / `auto_detect_math_fonts` トグル（デフォルト ON）を追加し JSON 永続化する。サイドパネルに「画像としても送信」チェックボックス（セッション内、デフォルト OFF）を追加し、AI 回答欄を `QWebEngineView` + `markdown` + KaTeX による Markdown・数式・化学式レンダリングに差し替える。`AnalysisRequest` に `images` フィールドを追加し、AIModel はその有無でテキストのみ / マルチモーダル API 呼び出しを切り替える。KaTeX ローカルバンドルは `src/pdf_epub_reader/resources/katex/` に `katex.min.css`、`katex.min.js`、`contrib/auto-render.min.js`、`contrib/mhchem.min.js`、`fonts/` を同梱する。追加依存: `PySide6-WebEngine`, `markdown`, KaTeX（ローカルバンドル）。詳細は `Phase4_Multimodal_Selection.md` を参照。
- **Phase 5: 包括的設定ダイアログの実装:** Phase 3 で導入した `AppConfig` の値（Phase 4 で追加した自動検出トグルを含む）をユーザーが GUI 上で変更・保存できる設定ダイアログを実装する。対象設定項目は画像フォーマット（PNG/JPEG）、JPEG 品質、ページキャッシュ上限、デフォルト DPI（基準 DPI。`devicePixelRatio` を乗じたレンダリング DPI は自動算出）、埋め込み画像自動検出、数式フォント自動検出等。MVP パターンに従い、設定ダイアログ用の View Protocol・Presenter・View 実装を追加する。設定変更は即座に `AppConfig` へ反映し、JSON ファイルへ永続化する。デフォルト DPI の変更はプレースホルダーの再配置とページの再レンダリングを伴う。
- **Phase 6: Modelの実装 (Gemini API) + モデル選択UI:** `ai_model.py` のスタブを `google-genai` SDK（新SDK）ベースの本実装に差し替える。SDK 依存は `pyproject.toml` で `google-generativeai` → `google-genai>=1.0` に変更する。`genai.Client` を用い、`await client.aio.models.generate_content(...)` でネイティブ非同期呼び出しを行う。`AnalysisRequest.images` が存在する場合は `Part.from_bytes` でマルチモーダル入力として送信する。429/5xx エラーに対し最大3回の指数バックオフリトライ（1s→2s→4s）を AIModel 内部のプライベートヘルパーで実装する。API キー未設定時もインスタンス化は許可し、API 呼び出し時に `AIKeyMissingError` を送出する。`utils/exceptions.py` に `AIError`・`AIKeyMissingError`・`AIAPIError`・`AIRateLimitError` の4例外を追加する。`dto/ai_dto.py` に `ModelInfo` dataclass を新設し、`AnalysisRequest` に `model_name: str | None` フィールドを追加する。`AppConfig` に AI 設定フィールド（`gemini_model_name`, `selected_models`, `system_prompt_translation`, `output_language`）を追加し JSON 永続化する。システムプロンプトは `{output_language}` プレースホルダー付きテンプレートとし、設定ダイアログから編集可能にする。設定ダイアログ（SettingsDialog）に「AI Models」タブを追加し、API 経由でモデル一覧を取得 → 使用モデルの複数選択 → デフォルトモデルの指定を可能にする。サイドパネルにモデル選択プルダウン（QComboBox）を追加し、リクエスト単位でモデルを切り替え可能にする。PanelPresenter に AI 例外のエラーハンドリングを追加し、結果パネルにエラーメッセージを表示する。MainPresenter に `ai_model` 引数を追加し、設定変更時のモデルリスト更新・config 反映フローを整備する。`IAIModel` Protocol に `list_available_models()` と `update_config()` を追加する。テストは `google.genai` を mock.patch で差し替えたモックベースの単体テスト（12件以上）とする。※Phase 6 では Context Caching 関連（`create_cache`, `get_cache_status`, `invalidate_cache`, `count_tokens`）はスタブ維持とし、`analyze()` 内での `cached_content` パラメータ使用も含め Phase 7 に先送りする。
- **Phase 6.5: KaTeX レンダリング修正・サイドパネル改善・解説付き翻訳実装:** Phase 6 完了後に発見された3つの問題を修正する。View/Model 層中心の変更で、Protocol・Presenter の変更は最小限。

  **A. KaTeX レンダリング修正（`side_panel_view.py`）:**
  `QWebEngineView.setHtml(html)` に `baseUrl` が渡されていないため、Chromium が `about:blank` オリジンから `file:///` スキームの KaTeX リソース（CSS/JS/fonts）読み込みをブロックし、数式が一切レンダリングされない問題を修正する。`SidePanelView.__init__` で KaTeX ディレクトリの `QUrl` を算出し `self._katex_base_url` に保持、全5箇所の `setHtml()` 呼び出し（プレースホルダー初期 HTML ×2、`update_result_text` の結果反映 ×2）に第二引数として `baseUrl` を追加する。

  **B. 選択プレビュー折りたたみ（`side_panel_view.py`）:**
  サイドパネルの「選択テキスト」「サムネイルプレビュー」「画像としても送信チェックボックス」を折りたたみ可能にし、AI 回答欄の視認性を向上させる。`CollapsibleSection` カスタムウィジェット（`▶ 選択テキスト` / `▼ 選択テキスト` のクリック可能ヘッダーで子要素の表示/非表示を切替）を `side_panel_view.py` 内に追加し、上記4ウィジェットを内包する。初期状態は展開。Protocol / Presenter の変更は不要（View 内部のレイアウトリファクタのみ）。

  **C. 解説付き翻訳プロンプト＋パース（`config.py`, `ai_model.py`, テスト）:**
  「解説付き翻訳」ボタン押下時（`include_explanation=True`）に、AI が解説を返さない問題を修正する。原因は `_build_system_instruction()` が `include_explanation` フラグを参照しておらず、通常翻訳と同一のシステムプロンプトが送信されること、および `_parse_response()` が常に `explanation=None` を返すこと。
  - `config.py` に `DEFAULT_EXPLANATION_ADDENDUM` 定数（「翻訳の後に『---』区切り線を入れ、その下に専門用語・概念・背景知識の解説を付けてください。」）を追加する（`AppConfig` フィールドは追加しない、設定ダイアログ対象外）。
  - `ai_model.py` の `_build_system_instruction()` に `include_explanation` 引数を追加し、`mode == TRANSLATION` かつ `include_explanation` のとき展開済みプロンプトに `DEFAULT_EXPLANATION_ADDENDUM` を追記する。`analyze()` の呼び出し箇所で `request.include_explanation` を渡す。
  - `_parse_response()` を更新し、`include_explanation=True` かつ TRANSLATION モード時に `raw_text` を `---` 区切りで分割（前半 → `translated_text`、後半 → `explanation`）。区切りなしの場合は全体を `translated_text`、`explanation=None` とする。Presenter の既存結合ロジック（`translated_text + "\n\n---\n\n" + explanation`）をそのまま活用する。
  - テスト: `test_ai_model.py` に解説モードのシステム指示検証・`---` 分割検証・区切りなし検証の3件を追加。`test_panel_presenter.py` の既存 `test_translate_with_explanation` がパスすることを確認（MockAIModel は既に `explanation` を返すため変更不要）。

- **Phase 7: Context Caching の実装:** Phase 6 でスタブ維持とした 4 メソッドを google-genai SDK の Explicit Caching API で本実装に差し替え、`analyze()` にキャッシュ自動付与＋フォールバックロジックを追加する。キャッシュ管理 UI（サイドパネルのステータス表示＋トグルボタン、専用ダイアログ）もこのフェーズで実装する。

  **A. Foundation（DTO・Config・例外）:**
  `CacheStatus` DTO に `model_name: str | None`（キャッシュ紐付きモデル名）と `expire_time: str | None`（ISO 形式の有効期限）を追加する。`utils/exceptions.py` に `AICacheError(AIError)` を追加する（キャッシュ作成失敗・トークン不足等で送出）。`AppConfig` に `cache_ttl_minutes: int`（デフォルト 60 分）フィールドとバリデーション定数（`CACHE_TTL_MIN=1`, `CACHE_TTL_MAX=1440`）を追加し、設定ダイアログの AI Models タブに TTL スピナーを設ける。

  **B. AIModel コア実装:**
  `IAIModel` Protocol を更新し、`create_cache(full_text, *, model_name=None, display_name=None)` / `count_tokens(text, *, model_name=None)` にモデル名パラメータを追加する。`update_cache_ttl(ttl_minutes) -> CacheStatus` と `list_caches() -> list[CacheStatus]` を新設する。
  - `count_tokens`: `await client.aio.models.count_tokens(model=..., contents=text)` で実トークン数を取得。SDK エラーは `AIAPIError` でラップ。
  - `create_cache`: 内部状態 `_cache_name` / `_cache_model` を保持。`await client.aio.caches.create(model=..., config=CreateCachedContentConfig(contents=[full_text], display_name="pdf-reader: {filename}", ttl=...))` で作成。`system_instruction` はキャッシュに含めない（翻訳/カスタムでシステム指示が異なるため）。SDK エラーは `AICacheError` で送出。
  - `get_cache_status`: `await client.aio.caches.get(name=...)` で最新状態取得。expire 済みなら内部状態をクリアして `is_active=False` を返却。
  - `invalidate_cache`: `await client.aio.caches.delete(name=...)` + 内部状態クリア。既に削除済みの場合はログのみ。
  - `analyze()` にキャッシュ統合: キャッシュ active かつモデル一致時に `GenerateContentConfig(cached_content=self._cache_name, system_instruction=...)` を付与。キャッシュ付きリクエストが非レートリミットエラーで失敗した場合、キャッシュを内部クリアしキャッシュなしで 1 回リトライ。レスポンスの `usage_metadata` から `prompt_token_count`, `cached_content_token_count`, `candidates_token_count` を `logger.info` で出力。
  - `update_cache_ttl`: `await client.aio.caches.update(name=..., config=UpdateCachedContentConfig(ttl=...))` で TTL 更新。
  - `list_caches`: `client.aio.caches.list()` で全キャッシュ取得 → `display_name.startswith("pdf-reader:")` でフィルタ → `CacheStatus` DTO リストを返却。

  **C. View インターフェース・サイドパネル:**
  `ISidePanelView` にキャッシュ作成/削除コールバック登録（`set_on_cache_create_requested`, `set_on_cache_invalidate_requested`）、ボタン状態制御（`set_cache_active`, `set_cache_button_enabled`）、モデル切替確認ダイアログ（`show_confirm_dialog`）を追加する。Phase 7.5 でカウントダウン関連メソッド（`start_cache_countdown`, `stop_cache_countdown`, `set_on_cache_expired`）を追加する。`ICacheDialogView` Protocol を新設し、2 タブ構成（「現在のキャッシュ」＝ステータス表示＋操作、「キャッシュ確認」＝アプリ用キャッシュ一覧テーブル）をサポートする。Phase 7.5 で `start_countdown` / `stop_countdown` を追加する。`SidePanelView` に既存のキャッシュステータスラベル横にトグルボタンを追加する。

  **D. Presenter 更新:**
  `PanelPresenter` にキャッシュ状態の内部管理、MainPresenter へのコールバック委譲（`set_on_cache_create_handler` / `set_on_cache_invalidate_handler`）、`update_cache_status` 公開メソッド、モデル切替時のキャッシュ一致確認ロジックを追加する。Phase 7.5 で `update_cache_status` 内にカウントダウン開始/停止ロジック（アクティブ時 `view.start_cache_countdown(expire_time)` → 0 到達で `_on_cache_expired` コールバック → MainPresenter 委譲）を追加する。`set_on_cache_expired_handler(cb)` を追加し、MainPresenter が `_on_cache_expired` → `_do_cache_expired()` で `await get_cache_status()` を呼び UI を自動リフレッシュする。`PanelPresenter` に `get_current_model() -> str | None` 公開 getter を追加し、サイドパネルで選択中のモデルを外部から取得可能にする。モデル未設定（`_current_model` が空/None）時は翻訳・カスタムプロンプト・キャッシュ作成を拒否し、結果パネルに設定案内を表示する。`MainPresenter` にキャッシュ作成オーケストレーション（`extract_all_text` → `create_cache`）を追加し、キャッシュ作成時のモデル名は `panel_presenter.get_current_model()` から取得する（`config.gemini_model_name` ではない）。Phase 7.5 で `_do_cache_create` に重複ガード（既存キャッシュがある場合は先に `invalidate_cache()` してから `create_cache()`）を追加する。ドキュメント切替時の自動 invalidate、キャッシュ管理ダイアログ起動（`_on_cache_management_requested` を async 本実装化。表示前に `await list_caches()` + `await get_cache_status()` でデータ取得）を追加する。メニューバー「キャッシュ(&C)」→「キャッシュ管理(&M)...」（キーバインド: **Ctrl+Shift+G**）を追加する。`AIModel.create_cache()` でキャッシュ非対応モデルのエラー（`"not supported for createCachedContent"`）を検出し、`AICacheError("このモデルはコンテキストキャッシュをサポートしていません")` に変換する。起動時バックグラウンドモデル検証（`_validate_models_on_startup`）を追加する（詳細はモデル選択アーキテクチャの節を参照）。

  **E. キャッシュ管理ダイアログ:**
  `CachePresenter`（`presenters/cache_presenter.py`）を新設し、ダイアログ表示＋ユーザーアクション（作成/削除/TTL 更新/一覧から選択削除）の取得を担当する。Phase 7.5 で `show()` 内にてアクティブキャッシュがある場合 `view.start_countdown(expire_time)` を呼び出し、タブ 1 の TTL ラベルをリアルタイム更新する。`CacheDialog`（`views/cache_dialog.py`）を新設し、QDialog モーダルで 2 タブ構成（タブ1: 現在のキャッシュ情報＋操作ボタン＋カウントダウン表示、タブ2: `list_caches()` 結果のテーブル表示＋選択行削除）を実装する。ダイアログ `accept()` / `reject()` オーバーライドで `stop_countdown()` を呼びタイマーを確実停止する。

  **F. テスト:**
  MockAIModel にキャッシュ関連パラメータ・メソッドを追加。MockSidePanelView にキャッシュ UI メソッドを追加。MockCacheDialogView を新設。`test_ai_model.py` にキャッシュメソッドの単体テスト（~12 件: count_tokens, create_cache, get_cache_status, invalidate_cache, analyze with cache + fallback, update_cache_ttl, list_caches）を追加。`test_panel_presenter.py` にキャッシュフローテスト（~6 件）、`test_main_presenter.py` にオーケストレーションテスト（~5 件）、`test_cache_presenter.py` を新設（~3 件）。

### Phase 7.5: キャッシュ改修（カウントダウン表示・重複防止・終了時自動破棄）

Phase 7 の補完フェーズ。以下の 3 改修を実施する。

**A. カウントダウン表示:**
サイドパネルおよびキャッシュ管理ダイアログ（タブ 1）でキャッシュ残り時間をリアルタイム（1 秒間隔 `QTimer`）で `H:MM:SS` 形式表示する。

**Protocol 追加:**

- `ISidePanelView`: `start_cache_countdown(expire_time: str)`, `stop_cache_countdown()`, `set_on_cache_expired(cb: Callable[[], None])`
- `ICacheDialogView`: `start_countdown(expire_time: str)`, `stop_countdown()`

**View 実装:**

- `SidePanelView`: `QTimer`（1000ms）+ `_expire_time_utc: datetime | None`。`_cache_base_text` を保持し `_on_countdown_tick` で `"ベーステキスト — 残り H:MM:SS"` 形式でラベル更新。0 以下到達で `_on_cache_expired` コールバック発火 + ラベル「期限切れ」。
- `CacheDialog`: `QTimer` + `_expire_time_utc` でタブ 1 の `_ttl_label` を毎秒更新。`accept()` / `reject()` オーバーライドで `stop_countdown()` を自動呼出し。タブ 2 の一覧テーブル Expire 列は静的 ISO 表示のまま。

**Presenter 更新:**

- `PanelPresenter`: `update_cache_status` 内で active + `expire_time` → `view.start_cache_countdown(expire_time)` / inactive → `view.stop_cache_countdown()`。`set_on_cache_expired_handler(cb)` / `_on_cache_expired()` で MainPresenter へ委譲。
- `CachePresenter`: `show()` 内で active + expire_time → `view.start_countdown(expire_time)` 呼出し。
- `MainPresenter`: `_on_cache_expired` → `_do_cache_expired()` で `await get_cache_status()` → `panel_presenter.update_cache_status(status)` + ステータスバーに「キャッシュの有効期限が切れました」。

**B. キャッシュ重複作成防止:**
`MainPresenter._do_cache_create` の先頭で `await get_cache_status()` → `is_active` なら `await invalidate_cache()` で既存キャッシュを削除してから `create_cache` を続行する。

**C. アプリ終了時のキャッシュ自動破棄（方法 B）:**

- `infrastructure/event_loop.py`: `run_app(app_main, *, on_shutdown=None)` — `on_shutdown: Callable[[], Awaitable[None]] | None`。`finally` ブロック内、`shutdown_asyncgens` の前に `loop.run_until_complete(on_shutdown())` を try/except で実行。
- `app.py`: モジュールレベル `_ai_model_ref` で AIModel 参照を保持。`async def _shutdown()` で `await _ai_model_ref.invalidate_cache()`。`run_app(_app_main, on_shutdown=_shutdown)` に変更。確認ダイアログなしで常に自動破棄。

**D. テスト（10 件追加）:**

- `test_panel_presenter.py` +3 件: カウントダウン開始/停止、expired コールバック発火
- `test_main_presenter.py` +3 件: expired 自動リフレッシュ、重複作成ガード、shutdown 呼出し
- `test_cache_presenter.py` +1 件: active キャッシュで `start_countdown` 呼出し
- Mock 更新: `MockSidePanelView` にカウントダウンメソッド + `simulate_cache_expired()` ヘルパー、`MockCacheDialogView` に `start_countdown` / `stop_countdown`

## **7. 推奨リファレンス**

- PySide6 Documentation
- PyMuPDF (fitz) Documentation
- Google Gen AI SDK for Python — `google-genai` パッケージ（`genai.Client`, `client.aio.models.generate_content`, Context Caching, count_tokens）
- Python typing.Protocol (PEP 544)
- qasync — Qt-asyncio event loop integration
- pytest-asyncio — async test support
