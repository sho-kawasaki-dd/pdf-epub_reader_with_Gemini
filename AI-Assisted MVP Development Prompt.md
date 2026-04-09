# **AIアシスタント向け 開発要件・アーキテクチャ設計書 (MVP版)**

## **1. プロジェクトの目的と概要**

PySide6を用いたローカルデスクトップ向けのAI連携ドキュメントビューアを開発する。PyMuPDFを用いてPDFおよびEPUBを画像としてレンダリングし、ユーザーが選択したテキストをGemini APIで解析（和訳・解説）する。また、全文のコンテキストキャッシュを利用した高度な解析機能を提供する。

本プロジェクトの最大の特徴は、**厳格なMVP (Model-View-Presenter) アーキテクチャの採用**である。自動テストの容易性と将来的な描画エンジンの差し替えを見据え、ビジネスロジックとGUI表現を完全に分離する。

## **2. 技術スタックと基本ルール**

* **GUIフレームワーク:** PySide6
* **ドキュメントエンジン:** PyMuPDF (fitz) ※PDF/EPUB両用
* **AI API:** Google AI SDK (google-generativeai)
* **非同期基盤:** asyncio + qasync（Qtイベントループ統合）
* **アーキテクチャ:** MVP (Model-View-Presenter) / Passive View パターン
* **言語:** Python 3.13以上 (Type Hinting, typing.Protocol を積極利用)
* **パッケージ管理:** uv / pyproject.toml
* **テスト:** pytest + pytest-asyncio

### **⚠️ AIへの厳格な指示（絶対遵守のMVPルール）**

1. **Passive Viewの徹底:** View（QWidgetの継承クラス）は「完全に受動的（馬鹿）」でなければならない。View内でデータの加工、API呼び出し、PDFの解析などのロジックを**一切書いてはならない**。
2. **依存の方向:**
   * ViewはModelを知らない。Presenterも知らない（シグナルを飛ばすだけ）。
   * PresenterはModelを知っている。また、Viewの**「インターフェース（Protocol）」**を知っている。
   * PySide6のクラス（QPixmap, QWidget, QThread等）は、**PresenterやModelに絶対にインポートしてはならない**。データの受け渡しはPythonの標準型（str, bytes, list, dataclass）で行うこと。
3. **非同期処理:** Model層の公開メソッドはすべて `async def` とする。Presenterは `await` で呼び出す。メインスレッド（GUI）をブロックしてはならない。
4. **テストの優先:** Model層はQtに依存しない純粋なPythonコードで実装し、単体テストを最優先する。Presenterも可能な限りロジックを分割し、Viewをモックしてテスト可能にする。
5. **ディレクトリ構成:** `src` レイアウトを採用し、テストコードと実装コードを明確に分離する。Model, Presenter, Viewはそれぞれ独立したサブディレクトリに配置する。
6. **ソースコードの自己文書化:** 各クラス・関数には新規参加のジュニアエンジニアがWhyまで理解できる粒度のdocstringおよびinline commentを付与し、型ヒントを活用してコードの意図を明確にする。

### **非同期処理の統一方針**

Model層は **asyncio ベースで統一** し、処理の性質に応じて内部実装を切り替える。Presenter から見た呼び出しパターンは常に `await model.method()` で統一される。

| 処理の性質 | 内部実装 | 具体例 |
|---|---|---|
| **I/O-bound** | `await` でネイティブ非同期呼び出し | Gemini API通信、キャッシュ操作 |
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
│       │   └── panel_presenter.py   # サイドパネル領域の進行
│       │
│       ├── models/                  # Qt非依存（純粋Python + asyncio）
│       │   ├── __init__.py
│       │   ├── document_model.py    # PyMuPDFによる解析・テキスト抽出ロジック
│       │   └── ai_model.py         # Gemini API通信、キャッシュ管理
│       │
│       ├── views/                   # PySide6 実装 (interfacesを満たすこと)
│       │   ├── __init__.py
│       │   ├── main_window.py       # 大枠のレイアウトとスクロールビュー
│       │   └── side_panel_view.py   # AI結果表示、操作パネル
│       │
│       ├── infrastructure/          # Qt ↔ asyncio 橋渡し
│       │   ├── __init__.py
│       │   └── event_loop.py        # qasync によるイベントループ統合
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
│       └── test_panel_presenter.py
│
├── .env.example                     # 環境変数テンプレート（GEMINI_API_KEY等）
├── .gitignore
├── pyproject.toml
└── README.md
```

### **ディレクトリ構成の設計意図**

| ディレクトリ | 役割 | Qt依存 |
|---|---|---|
| `interfaces/` | View の Protocol 定義。Presenter が依存する契約 | ✗ |
| `dto/` | 層間のデータ受け渡し用 dataclass。全層が参照可能 | ✗ |
| `models/` | ビジネスロジック。asyncio ベース。テスト最優先 | **✗** |
| `presenters/` | Model と View(Protocol) を仲介。async/await で呼び出し | **✗** |
| `views/` | PySide6 による GUI 実装。Passive View | ✓ |
| `infrastructure/` | qasync によるイベントループ橋渡し | ✓ |
| `utils/` | 設定値・例外クラス等の共通ユーティリティ | ✗ |

## **4. 機能要件とMVPによるデータフロー**

### **4.1. ドキュメント閲覧機能**

* **View:** PySide6の機能（QGraphicsViewなど）を用いて画像を縦に並べて表示する。ユーザーがドラッグで範囲選択したら、その「画面上の座標リスト」をシグナルでPresenterに通知する。
* **Presenter:** 受け取った座標リストをModelに渡す（`await model.extract_text(...)`）。Modelから返ってきたデータ（bytes, dataclass等）をViewに「これを表示せよ」と命令する。
* **Model:** PyMuPDFを操作し、指定されたページをレンダリング（CPU-bound → `run_in_executor`）。また、渡された座標から元のテキストデータを抽出する。

### **4.2. AI解析機能とコンテキストキャッシュ**

* **View:** 「解析実行」や「全文キャッシュ有効化」ボタンが押されたら、シグナルを発火するのみ。ローディングアニメーションの開始/停止はPresenterからのメソッド呼び出し（例: `view.show_loading()`）で行う。
* **Presenter:** `await model.analyze_text(...)` で非同期呼び出し。結果の DTO（翻訳テキストやトークン数）が返ってきたら、`view.update_result_text(text)` や `view.update_token_count(count)` を呼び出す。
* **Model:** Gemini APIと通信（I/O-bound → ネイティブ `await`）。32kトークン未満でのContext Cachingエラーを回避するための自動フォールバックロジック等、API仕様に依存する処理はすべてここにカプセル化する。

### **4.3. 非同期処理のアーキテクチャ図**

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

* APIキー等の秘匿情報は **環境変数** で管理する。`.env` ファイル + `python-dotenv` を使用し、`.env` は `.gitignore` に含める。
* `utils/config.py` にはデフォルト値やスキーマ定義のみを記述する。秘匿情報そのものをハードコードしてはならない。
* `.env.example` にテンプレートを用意し、必要な環境変数名を明示する。

## **6. 開発フェーズ（AIへのタスク指示用）**

* **Phase 0: プロジェクト構成の作成:** ディレクトリ構成、`__init__.py`、`pyproject.toml` の依存定義、`.env.example`、`conftest.py` 等のスキャフォールドを作成する。
* **Phase 1: インターフェースとDTOの定義:** `interfaces/view_interfaces.py` に Protocol を用いてViewが持つべきメソッドを定義する。`dto/` にデータ転送オブジェクトを定義する。その後、GUIを使わずにコンソール出力だけで動く「ダミーのView」とPresenterを作成し、ロジックの流れを確認する。
* **Phase 2: ViewのPySide6実装:** Phase 1で定義したインターフェースを満たす `views/main_window.py` 等を実装し、`infrastructure/event_loop.py` でqasyncを設定、Presenterと結合する。
* **Phase 3: Modelの実装 (PyMuPDF):** `document_model.py` を実装し、PDFの画像レンダリング（`run_in_executor`）と仮想スクロール向けのデータ供給、および座標からのテキスト抽出を完成させる。
* **Phase 4: Modelの実装 (Gemini API):** `ai_model.py` を `async def` で実装し、Gemini APIへの通常リクエスト（ネイティブ `await`）と結果の返却を実現する。
* **Phase 5: Context Cachingの実装:** 全文抽出とキャッシュ作成機能、最小トークン制限の回避ロジックをModelに組み込み、Presenter経由でView（有効期限やステータス）を更新する。

## **7. 推奨リファレンス**

* PySide6 Documentation
* PyMuPDF (fitz) Documentation
* Google Gen AI SDK for Python (Context Caching, count\_tokens)
* Python typing.Protocol (PEP 544)
* qasync — Qt-asyncio event loop integration
* pytest-asyncio — async test support