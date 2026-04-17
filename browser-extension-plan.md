# Browser Translation Extension Plan

## 目的

本企画書は、既存の Gem Read のバックエンド資産を一部流用しつつ、
Chrome / Edge 上で閲覧中の HTML 本文を Gemini API に送信して翻訳や補助解析を行う
ブラウザ拡張プロジェクトのたたき台を示す。

## 背景

現行アプリは PDF / EPUB を対象とするローカルデスクトップアプリであり、
選択領域のテキスト抽出、画像付きマルチモーダル送信、Gemini モデル切替、
Context Cache などの機能を備えている。

一方で、日常的な情報収集ではブラウザ上の記事、論文要約ページ、技術文書、ブログなど、
HTML コンテンツに対して同様の翻訳・解析体験を求める場面が多い。
そこで、ブラウザで選択した本文やその周辺画像を対象に、既存の AI 連携資産を再利用しながら
軽量な拡張機能として提供する。

## プロダクト概要

ユーザーがブラウザ上で本文を選択すると、拡張機能が選択テキストを抽出し、
必要に応じて選択範囲のスナップショット画像も取得してローカル Python バックエンドへ送信する。
加えて、テキスト選択に依存しない自由矩形の撮影範囲指定にも対応し、図表・数式・画像中心の領域を
そのまま翻訳や解説対象として送信できるようにする。
バックエンドは Gemini API を呼び出し、翻訳、解説付き翻訳、カスタムプロンプト解析を実行する。
結果はブラウザ上のオーバーレイ UI に表示する。

## 目標

- HTML ページ上の本文テキストを選択して Gemini に送れること
- 選択範囲に対応するスナップショット画像を補助入力として送れること
- ユーザーが自由矩形で指定した画像領域を撮影し、翻訳・解説付き翻訳の対象として送れること
- 翻訳、解説付き翻訳、カスタムプロンプト解析を提供すること
- 翻訳結果や解説内の数式をオーバーレイ上で可読な形にレンダリングできること
- 既存 Python 資産のうち Gemini 連携と設定管理を再利用すること
- Chrome / Edge の両方で動作すること
- UI は最終的にブラウザページ上のオーバーレイで表示すること

## 非目標

- PDF ビューアや EPUB リーダー機能をブラウザ拡張内に再実装すること
- ページ全体の完全な OCR を常時行うこと
- サーバー常設の SaaS を最初から構築すること
- すべてのサイトで同一の DOM 抽出精度を保証すること

## 想定ユースケース

- 技術記事の一部段落を選択して日本語に翻訳する
- 数式や図表を含む箇所を選択し、テキストに加えて画像も送って補助解析する
- 図表、数式、キャプション付き画像などを自由矩形で囲って撮影し、画像主体で翻訳や解説付き翻訳を行う
- 英文論文紹介ページの複数箇所を順に選択し、まとめて翻訳する
- 用語の背景説明を含めた解説付き翻訳をその場で確認する
- 選択箇所について自由入力のカスタムプロンプトで問い合わせる

## 必須要件

- 選択テキストの抽出
- 複数選択の保持と順序付き送信
- 選択範囲のスナップショット取得 (TypeScript側 Canvas による Crop/Resize)
- 自由矩形による撮影範囲選択
- 自由矩形で選択した画像領域に対する翻訳および解説付き翻訳
- Gemini へのテキスト + 画像のマルチモーダル送信
- モデル切替
- 結果表示 UI
- 翻訳結果、解説、カスタムプロンプト結果に含まれる Markdown / LaTeX 数式の安全なレンダリング
- ローカル設定保存 (Local API のポート番号や接続先設定を含む)
- API キーを拡張内に持たず、Python 側に閉じ込める構成
- Local Python API 未稼働時の明確なフォールバック・エラー表示

## 推奨要件

- 記事本文全体抽出による Context Cache 利用
- サイトごとの抽出失敗時フォールバック
- レート制限や API エラー時の分かりやすい表示
- ショートカットからの起動
- オーバーレイ位置、サイズ、テーマの調整

## 数式レンダリング方針

本機能の実装着手は Phase 2 以降とし、Phase 1 では plain text による結果表示を許容する。

### 基本方針

- オーバーレイの結果表示は plain text のままではなく、Markdown + LaTeX 数式を描画できる renderer を前提とする。
- 数式は inline `$...$` と display `$$...$$` を基本記法とし、必要に応じて `\(...\)` と `\[...\]` も受け入れる。
- 化学式や反応式を扱うため、可能であれば mhchem 相当の拡張も有効化する。
- backend は結果文字列を返す役割に留め、Markdown / 数式レンダリングは browser-extension 側の overlay で完結させる。

### 実装方針

- overlay 内では `textContent` による単純表示ではなく、`Markdown parse -> sanitize -> KaTeX auto-render` の順で描画する。
- Markdown parser は `markdown-it` または `marked` のような軽量実装を採用し、生 HTML は原則無効化または厳格に制限する。
- HTML sanitization には `DOMPurify` などの実績ある sanitizer を使い、AI 応答をそのまま `innerHTML` に流し込まない。
- 数式レンダリングには KaTeX を採用し、browser-extension の Shadow DOM 内で完結するよう CSS と script を閉じ込める。
- code block / inline code の中身は数式レンダリング対象から除外し、説明文やサンプルコードの可読性を壊さない。
- KaTeX の描画に失敗した場合や未知の記法が混ざる場合は、overlay 全体を壊さずに元の Markdown テキストへ安全にフォールバックする。

### 出力契約

- Python 側の Gemini 呼び出しでは、可能な範囲で「本文は Markdown、数式は LaTeX delimiter を使う」形式を促すプロンプトを採用する。
- browser API の response schema は HTML 断片ではなく、従来どおり text ベースの文字列を返す。
- frontend は翻訳、解説付き翻訳、カスタムプロンプトの各結果を共通 renderer に通し、描画品質を揃える。

### フォールバックと制約

- 数式レンダリングは UX 改善機能として扱うが、render failure により翻訳結果そのものが失われてはならない。
- CSP や site script と干渉しないよう、必要な style は Shadow DOM 内へ注入する。
- 数式を含む長文では描画コストが上がるため、再描画範囲を最小化し、必要なら段階描画を検討する。

## 技術方針

### 採用方針

- フロントエンド: TypeScript ベースの Chrome / Edge 拡張
- バックエンド: ローカル Python サービス (FastAPI)
- AI 呼び出し: Gemini API
- UI 表示: Content Script から注入するオーバーレイ

### この構成を採る理由

- DOM 選択、オーバーレイ描画、拡張権限、スクリーンショット取得は TypeScript 側が自然
- 既存の Gemini 連携、DTO、設定、キャッシュ制御は Python 側資産を流用しやすい
- API キーをブラウザ拡張に置かずに済む
- ローカルアプリとして段階的に開発しやすい

### リポジトリ構成方針

既存資産の直接インポートや機能検証を迅速に行うため、初期開発段階では同一リポジトリ（モノレポ構成）での開発を採用する。
- **フロントエンド構成**: 現状の `gem-read` リポジトリ直下にブラウザ拡張用のディレクトリ（`browser-extension/`）を新設して実装を行う。
- **バックエンド構成**: Local Python API は `src/browser_api/` （例）として新設する。これにより、将来のAPI独立を見据えつつ、当面は `src/pdf_epub_reader/` の既存資産を自然にインポート可能とする。
- **メリット**: 既存のPythonモジュール（`ai_model.py` 等）をそのまま参照でき、ローカルAPIと拡張機能の連携テストが単一ワークスペースで完結する。
- **将来的な見直し**: 共通利用するバックエンドAPIがデスクトップアプリ（Gem Read）から完全に分離・独立した段階で、必要に応じてリポジトリの分離を検討する。

### 採用アーキテクチャ

#### browser-extension/

ブラウザ拡張側は、**runtime-first modular monolith** を採用する。
最上位の責務分離は機能単位ではなく、Chrome 拡張の実行コンテキスト単位（Background / Content / Popup / Shared）で行う。

- `background/`: 権限が必要な処理の coordinator。context menu、screen capture、ローカル API 通信、crop 実行を担当する。
- `content/`: DOM 読み取りとページ内 UI の owner。Selection API、自由矩形 UI、オーバーレイ描画を担当する。
- `content/` の overlay 表示では、Phase 2 で Markdown / KaTeX renderer を導入し、AI 応答の安全な描画と fallback を担当する。
- `popup/`: 拡張ポップアップの UI と軽量な設定導線を担当する。
- `shared/`: 実行コンテキスト間で共有する契約、設定定数、純粋データ型を置く。

この構成では、トップレベルの entry file は listener 登録や bootstrap のみを持ち、実装本体は `usecases` / `gateways` / `services` / `overlay` / `selection` へ分割する。

#### src/browser_api/

ローカル Python API 側は、**thin hexagonal architecture** を採用する。
FastAPI の router は HTTP 入出力と依存解決に徹し、解析フローやモデル解決、画像デコードなどのユースケースは application 層に寄せる。

- `api/`: FastAPI app、router、request/response schema、dependency wiring、HTTP エラー変換を担当する。
- `application/`: use case とアプリケーションデータ型を置き、HTTP や外部 SDK に依存しない処理を担当する。
- `adapters/`: 既存の `AIModel` や設定ロードを browser API から利用するための bridge を担当する。

この構成により、FastAPI endpoint 増加時も router の肥大化を防ぎ、既存の `pdf_epub_reader` 資産への依存点を adapter 層へ集約できる。

### 採用ディレクトリ構成

現時点で採用する構成は次の通りとする。

```text
browser-extension/
    src/
        background.ts          # thin entry
        content.ts             # thin entry
        popup.ts               # thin entry
        messages.ts            # shared への re-export
        background/
            entry.ts
            menus/
            gateways/
            services/
            usecases/
        content/
            entry.ts
            overlay/
            selection/
        popup/
            entry.ts
            ui/
        shared/
            config/
            contracts/

src/browser_api/
    main.py                  # thin entry
    api/
        app.py
        dependencies.py
        error_handlers.py
        routers/
        schemas/
    application/
        dto.py
        errors.py
        services/
    adapters/
        ai_gateway.py
        config_gateway.py
```

### 追加ルール

- Background と Content の間でやり取りする message は `browser-extension/src/shared/contracts/` に集約する。
- `browser-extension/src/background.ts` と `browser-extension/src/content.ts` は今後も entry file として維持し、ロジックを直書きしない。
- 自由矩形選択は `browser-extension/src/content/` 配下の独立 feature として実装し、Background には矩形座標と capture 実行要求のみを渡す。
- FastAPI の router から `AIModel` を直接呼び出さず、必ず `application/` と `adapters/` を経由させる。

## テスト計画

### テスト方針

- browser-extension は **Vitest + jsdom** を単体テスト基盤とし、Playwright を Chromium 向け E2E の基盤とする。
- `src/browser_api/` は既存の **pytest + pytest-asyncio** 基盤に統合し、application/service と FastAPI router を主対象とする。
- 主対象 OS は Windows とするが、Python テストは将来的な cross-platform 実行を阻害しない書き方を維持する。
- CI gate は browser-extension unit、browser-extension smoke E2E、browser_api pytest を分離して実行できる形にする。
- 実 Gemini API を叩くテストは通常 CI には含めず、手動 smoke または別ジョブ扱いとする。

### browser-extension のテストスイート

#### Unit Test

- テスト対象は `runtime entry` ではなく、`usecases` / `gateways` / `services` / `overlay` / `selection` を優先する。
- 最初の優先対象は次の通りとする。
    - `background/usecases/runPhase0TranslationTest.ts`
    - `background/services/cropSelectionImage.ts`
    - `content/selection/snapshotStore.ts`
    - `content/overlay/renderOverlay.ts`
- Chrome API mock と DOM setup は共有 fixture に集約し、テストごとに ad hoc な mock を増やさない。
- `background.ts` / `content.ts` / `popup.ts` は thin entry として維持し、原則直接テストしない。
- Phase 2 では数式 renderer の unit test を追加し、inline 数式、display 数式、コードブロック除外、sanitize、render failure fallback を検証する。

#### E2E Test

- E2E は Playwright を Chromium only で導入する。
- 最初の smoke シナリオは「テキスト選択 → context menu 起動導線 → overlay 表示または想定エラー表示」とする。
- unpacked extension 読み込み前提で実行し、必要に応じて local API 応答を stub できる test mode を検討する。
- 自由矩形機能追加後は `content/rect-selection/` 系の専用 E2E を追加する。
- Phase 2 では数式を含む翻訳結果を stub した E2E を追加し、overlay 上で KaTeX が崩れず描画されることを確認する。

### src/browser_api のテストスイート

#### Application / Service Test

- 最優先の単体テスト対象は `application/services/analyze_service.py` とする。
- 検証項目は次を含む。
    - model 名解決
    - Base64 画像 decode
    - `AIKeyMissingError` 時の mock fallback
    - `translation` / `translation_with_explanation` の応答整形
- `AIModel` 実通信は行わず、gateway を差し替えて安定実行できるようにする。

#### Router / API Test

- FastAPI router は `TestClient` ベースで `/health` と `/analyze/translate` を検証する。
- 主な確認項目は次の通りとする。
    - 正常系レスポンス
    - model 未設定時の 400
    - AI error の HTTP mapping
    - app state / dependency override による依存差し替え

### 推奨テスト配置

```text
tests/
    test_browser_api/
        conftest.py
        test_application/
            test_analyze_service.py
        test_api/
            test_health.py
            test_analyze_router.py

browser-extension/
    __tests__/
        setup.ts
        mocks/
        unit/
            background/
            content/
            popup/
        e2e/
```

### 実行方針

- Python の専用テストは `uv run pytest tests/test_browser_api/ -q` を基準コマンドとする。
- browser-extension の unit test は `npm run test`、coverage は `npm run test:coverage` を基準コマンドとする。
- browser-extension の E2E は Playwright smoke を別コマンドで実行可能にし、unit test と分離する。
- 既存回帰確認として `npm run build` と `uv run pytest tests/ -q` を維持する。

### Coverage / CI 運用

- Coverage は初回導入時に hard gate にせず、まずレポート出力を整えて現状値を観測する。
- しきい値は導入後の実測値を見て段階的に設定する。
- CI では少なくとも次の 3 系統を独立ジョブ化できる構成を目指す。
    - browser_api pytest subset
    - browser-extension Vitest
    - browser-extension Playwright smoke

## システム構成案

```mermaid
flowchart LR
    User[User]
    Page[Web Page]
    Content[Content Script]
    Overlay[Overlay UI]
    Background[Extension Background]
    LocalAPI[Local Python API (FastAPI)]
    Gemini[Gemini API]

    User --> Page
    User --> Overlay
    Page --> Content
    Content --> Overlay
    Content --> Background
    Background --> LocalAPI
    LocalAPI --> Gemini
```

**※** Content Script (Overlay) から Local API への直接通信は、対象ページの CSP（Content Security Policy）違反となる可能性が高いため、必ず Background Service Worker を経由させる設計とする。

## コンポーネント責務

### 1. Content Script

- ユーザーのテキスト選択を取得する
- 選択範囲の矩形座標を取得する
- 必要に応じて本文抽出候補を判定する
- オーバーレイ UI をページ上に注入する
- 結果表示や複数選択状態の反映を行う

### 2. Background Service Worker

- `chrome.tabs.captureVisibleTab` など権限が必要な処理を担当する
- Content Script とローカル API の橋渡しを行う
- タブ情報、サイト単位設定、権限状態を管理する

### 3. Overlay UI

- 選択プレビューの表示
- 自由矩形選択モードの開始、確定、キャンセル
- 複数選択の一覧表示と削除
- モデル選択
- 翻訳、解説付き翻訳、カスタムプロンプト送信
- ローディング、エラー、結果表示
- Markdown / LaTeX 数式の安全な描画と render failure 時の raw text fallback

### 4. Local Python API

- FastAPI を用いた Web サーバーの提供
- バックグラウンドプロセスとしてユーザー手動による起動
- 拡張機能（`chrome-extension://*` 等）からのアクセスを許可する CORS 設定
- ポート番号の競合回避対応（環境変数や起動引数によるポート指定）
- Gemini API 呼び出し
- モデル一覧取得
- Context Cache 管理
- 設定管理
- トークン計測

## 既存資産の再利用方針

### 再利用しやすい資産

- `src/pdf_epub_reader/models/ai_model.py`
- `src/pdf_epub_reader/dto/ai_dto.py`
- `src/pdf_epub_reader/utils/config.py` の AI 設定部分
- `src/pdf_epub_reader/interfaces/model_interfaces.py` の AI 側契約の考え方

### 参考実装として流用する資産

- `src/pdf_epub_reader/presenters/panel_presenter.py` の複数選択連結ロジック
- `src/pdf_epub_reader/presenters/main_presenter.py` の選択スロット管理の考え方

### 流用せず置き換える資産

- `src/pdf_epub_reader/models/document_model.py`
- PySide6 ベースの View 層
- qasync を前提にしたアプリ起動構成

## UI 方針

### 最終形

ページ右側または選択近傍に固定表示されるオーバーレイ UI を採用する。
Content Script から Shadow DOM を使って注入し、ページ本体の CSS と衝突しにくい構成にする。

### 初期実装

MVP の段階では、オーバーレイ UI を最初から採用してよい。
ただし実装難度が想定より高い場合は、暫定的に拡張のサイドパネル表示へ退避できるよう設計する。

### UI 要件

- ページ選択を邪魔しないこと
- 最小化と再表示ができること
- 選択プレビューと結果表示を見比べやすいこと
- 数式、化学式、箇条書きを含む結果でも可読性を保てること
- 自由矩形選択モード中に撮影対象領域を視覚的に確認できること
- モバイル表示は対象外とし、デスクトップブラウザを優先すること

## テキスト抽出方針

### 優先順位

1. ユーザーの明示的なテキスト選択をそのまま取得する
2. 必要に応じて親要素をたどって文脈候補を抽出する
3. 記事全文が必要な場合のみ main content 抽出を行う

### 実装方針

- 基本は Selection API と Range API を使用する
- 複数選択はネイティブ選択に依存せず、内部リストとして保持する
- 本文全体抽出は Readability 系ライブラリの利用を検討する

## 画像取得と前処理方針

### 基本方針

画像入力は常時送るのではなく、数式、図表、崩れた文字、レイアウト依存の箇所など、
テキストだけでは不十分な場面で補助的に使う。
画像のエンコードや Crop/Resize は、通信ペイロード削減とバックエンド負荷軽減のため、**TypeScript 側（フロントエンドの Canvas API）** で完了させた上で Local API へ送信する。

### トークン節約の優先順位

1. 不要領域を送らない
2. 選択範囲だけを tight crop する (TypeScript 側)
3. 目的に応じて長辺をリサイズする (TypeScript 側)
4. 最後に圧縮形式と品質を調整する (TypeScript 側)

### デフォルト案

- 通常の補助画像: 長辺 768px、JPEG または WebP、品質 80 前後
- 文字や数式が重要な画像: 長辺 1024px まで許容
- DOM から十分な本文が取れる場合: 画像送信なしを既定とする

### 理由

Gemini への画像入力コストは、主に画像寸法と解像度に影響される。
そのため、バイトサイズだけを小さくする圧縮よりも、切り抜きと適切なリサイズが重要である。

## バックエンド API 案

### 最小 API

- `POST /analyze/translate`
- `POST /analyze/translate-with-explanation`
- `POST /analyze/custom`
- `GET /models`
- `GET /cache/status`
- `POST /cache/create`
- `DELETE /cache`
- `POST /tokens/count`
- `GET /health`

### リクエスト例

- text: 連結済み本文テキスト
- images: 任意の画像配列
- model_name: 使用モデル名
- url: 対象ページ URL
- page_title: 対象ページタイトル
- selection_metadata: 選択順、座標、抽出方法などのメタデータ

## セキュリティと権限

- Gemini API キーは Python 側だけに保持する
- 拡張は必要最小限の host permissions に絞る
- スクリーンショット取得権限は対象機能使用時のみ求める
- 送信先は原則 `http://127.0.0.1` のローカル API に限定する
- ログには選択本文や画像を不用意に残さない

## 開発フェーズ案

### Phase 0: 技術検証

- 選択テキスト取得
- 選択範囲座標取得
- `captureVisibleTab` による撮影
- TS 側 Canvas での crop / resize / encode の性能確認
- ローカル Python API (FastAPI) の CROS / 呼び出し確認

成果物:

- 最小プロトタイプ
- 実装上の制約一覧

### Phase 1: MVP

- 単一選択の翻訳
- オーバーレイ UI の基本表示 (結果表示は plain text を許容)
- モデル選択
- エラー表示 (Local API 未稼働時のフォールバック通知を含む)
- 拡張機能設定画面 (Local API ポート等の変更機能)
- Python 側の Gemini 呼び出し再利用 (FastAPI 構築と CORS 許可)

成果物:

- 単一選択で安定して翻訳できる拡張

### Phase 2: 実用化

- 複数選択の保持
- 解説付き翻訳
- カスタムプロンプト
- 翻訳結果に対する Markdown + 数式レンダリング基盤の導入
- 解説付き翻訳とカスタムプロンプト結果への数式レンダリング適用
- 画像付き送信
- 自由矩形画像選択 UI
- 自由矩形で選択した画像領域に対する翻訳・解説付き翻訳
- 設定保存

成果物:

- 日常利用できるレベルの拡張

### Phase 3: Keyboard-First Workflow

- overlay / session 操作用ショートカットの整備
- overlay の再表示、最小化、終了をキーボードから実行できるようにする
- 現在の選択テキストを batch に追加するショートカットの追加
- 自由矩形選択 UI を起動するショートカットの正式サポート
- 直前 action、model、custom prompt の再実行をキーボードから実行できるようにする
- popup の overlay 起動導線を補助導線として維持しつつ、browser command 主導の操作体系へ寄せる
- restricted pages や selection 未取得時に silent failure にならないエラー表示を整備する

ショートカット仕様:

- browser command
    - overlay の再表示: `Ctrl+Shift+O` (`Command+Shift+O`)
    - 現在の選択テキストを batch に追加: `Ctrl+Shift+B` (`Command+Shift+B`)
    - 自由矩形選択 UI の開始: `Ctrl+Shift+Y` (`Command+Shift+Y`)
- overlay 内 shortcut
    - `Esc`: 自由矩形選択中は cancel、overlay 表示中は最小化
    - `Shift+Esc`: overlay を終了して session を clear
    - `Ctrl+Enter` (`Command+Enter`): Custom Prompt textarea 内から送信
    - `Alt+R` (`Option+R`): 直前 action / model / custom prompt の再実行
- overlay の再表示は cached session があればそれを復元し、無ければ launcher-only overlay を表示する
- `Ctrl+Shift+B` は live な text selection のみを batch に追加し、selection が無い場合は overlay 上に明示的なエラーを表示する
- browser command は manifest の `commands` で提供し、必要に応じてブラウザ側の拡張ショートカット設定で再割り当てできる前提とする
- overlay 内 shortcut は text input / textarea / contenteditable focus 中の誤作動を避けるため、入力系ショートカットと操作系ショートカットの適用条件を分ける
- session の保持範囲は tab lifetime に限定し、reload 後や browser restart 後の復元は Phase 3 では扱わない

成果物:

- キーボード主体で操作できる日常利用向け拡張

### Phase 4: Article Context Intelligence

- 本文全体抽出と Context Cache
- Readability 優先の汎用記事抽出導入
- サイトごとの抽出失敗時フォールバックと selector 最適化
- トークン事前計測と cache 作成前比較
- 長文記事に対する cache 作成、状態確認、削除の導線整備
- URL 変更、model 変更、TTL 切れ、本文ハッシュ不一致時の cache invalidation
- overlay UI の長文記事向け改善

設計方針:

- Context Cache は 1 タブ 1 アクティブ cache を基本とする
- cache 作成は常時自動ではなく、記事抽出成功かつ長文時の条件付き自動を基本とする
- 記事全文抽出は Readability を優先し、必要に応じてサイト別 selector へフォールバックする
- トークン計測は送信前見積もり、cache 作成前比較、結果後の実績表示を対象とする

成果物:

- 長文記事や技術文書に強く、article context を活かせる拡張

## 主なリスク

- サイトごとの DOM 構造差異により本文抽出が不安定になる
- Iframe や特殊な描画領域では選択取得や撮影が難しい場合がある
- スクリーンショット撮影権限への心理的抵抗がある
- レイアウト依存の UI はサイト CSS 干渉を受けやすい
- AI 応答を HTML として描画する場合、XSS や sanitizer 不備のリスクがある
- 数式レンダリング導入で bundle size と描画コストが増える
- ライセンス条件を満たした再利用方針の整理が必要

## 対応方針

- 抽出失敗時は明示的な選択テキストのみ送る
- オーバーレイは Shadow DOM で分離する
- Markdown から生成した HTML は必ず sanitize し、KaTeX 適用後も raw HTML を信用しない
- 撮影機能は明示操作時のみ動かす
- API 失敗時はテキストのみで再試行できるようにする
- render failure 時は plain text 表示へ自動フォールバックする
- 派生プロジェクト化する場合は AGPL 条件を事前確認する

## 初期開発タスク

- TypeScript 拡張の土台作成
- Local Python API の分離
- 共通 DTO の整理
- 単一選択の送信フロー実装
- オーバーレイ UI 試作
- Markdown / KaTeX renderer の組み込みと fallback 設計
- 画像 crop / resize / encode 実装
- モデル選択 UI 実装
- エラー時の表示とログ整理

## 成功条件

- 技術記事上の選択テキストを数クリックで翻訳できる
- 数式や図表を含む選択に対して画像補助が有効に働く
- 翻訳結果や解説に含まれる数式を overlay 上で崩さず読める
- オーバーレイ UI が日常利用で邪魔にならない
- API キーを拡張側に持たずに運用できる
- 現行アプリの Gemini 連携資産を無理なく再利用できる

## 結論

本プロジェクトは、TypeScript 製ブラウザ拡張とローカル Python バックエンドの組み合わせで進めるのが妥当である。
MVP では単一選択翻訳と plain text ベースのオーバーレイ表示に絞り、Phase 2 で複数選択、数式レンダリング、画像補助を実用化する。
その後の Phase 3 では keyboard-first workflow を整備し、Phase 4 で article context 抽出、Context Cache、トークン計測へ拡張する。
画像前処理は圧縮だけに頼らず、切り抜きとリサイズを主軸に設計する。
