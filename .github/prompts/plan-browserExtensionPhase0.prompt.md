## Plan: ブラウザ拡張 Phase 0 (技術検証) 実装計画

本計画は、`browser-extension-plan.md` の Phase 0 にあたる、Webページ上の選択範囲からローカルPython APIとの通信や画像切抜きの技術検証を行うための具体的なステップです。

**Steps**
1. **Python依存関係の更新**
   - 既存の `pyproject.toml` に `fastapi`, `uvicorn` を追加し、既存環境に統合します。
2. **検証用 FastAPI サーバーの構築**
   - `src/browser_api/main.py` を新規作成し、`chrome-extension://*` を許可するCORS設定を導入します。
   - `/analyze/translate` 等のPOSTエンドポイントを作成し、既存の `src/pdf_epub_reader/models/ai_model.py` を呼び出して翻訳を行う（またはモックを返す）処理を記述します。
   - FastAPI 起動時に `.env` を読み込む初期化を追加し、`GEMINI_API_KEY` と既存 `AppConfig` をデスクトップ版と同じ前提で利用できるようにします。
   - CORS は拡張 ID 固定に依存しないよう、`allow_origin_regex` を用いて `chrome-extension://.*` を許可する方針を採ります。
3. **拡張機能: マニフェストと権限設定**
   - `browser-extension/` 側で `permissions` (`contextMenus`, `activeTab`, `scripting`, `offscreen`) を許可します。
   - 追加で `host_permissions` に `http://127.0.0.1:8000/*` と `http://localhost:8000/*` を設定し、Background からローカル API へ `fetch` できる状態にします。
4. **拡張機能: 情報取得・キャプチャの連動 (Background & Content Script)**
   - Background: `chrome.contextMenus` を登録し、右クリックメニュー「翻訳テスト」を作成します。
   - Content Script: Backgroundからの指示を受け、現在の選択テキストとその `getBoundingClientRect()` の座標を Background へ返却します。
   - 座標契約として、Content Script は `rect` に加えて `window.innerWidth` / `window.innerHeight` / `window.devicePixelRatio` を返し、Phase 0 では複数 rect を扱わず union rect 1 個に正規化します。
   - Background: 座標を受け取り次第、`chrome.tabs.captureVisibleTab` で画面のスクリーンショットを撮影します。
   - Background: 受け取った viewport 情報とキャプチャ画像の実寸からスケール係数を算出し、crop 座標を画像ピクセル座標へ変換してから切り抜きを行います。
5. **画像切り抜きとリサイズの高速化 (OffscreenCanvas)**
   - Background スクリプト上 (または Offscreen Document) で、`OffscreenCanvas` と `createImageBitmap` を用いて、撮影した画像を座標通りに Crop/Resize します。
   - 処理後、Base64 JPEG/WebP にエンコードして通信用ペイロードを作成します。
6. **API 通信と結果の可視化 (Content Script UI)**
   - Background: 作成したテキストと画像ペイロードを `http://127.0.0.1:8000/analyze/translate` へ fetch します。
   - Content Script: 返ってきた予測テキストと切り抜き画像（プレビュー）を簡易的な `div` 要素として画面上に注入（オーバーレイ表示）して検証結果を示します。

**Relevant files**
- `pyproject.toml` — Webフレームワーク (FastAPI, uvicorn) の追加
- `src/browser_api/main.py` — ローカルAPIアプリケーションの初期構築、CORS設定、ルーティング
- `browser-extension/manifest.json` — 必要な権限の設定
- `browser-extension/src/background.ts` — コンテキストメニュー処理、Screen Capture、OffscreenCanvas処理、API fetch
- `browser-extension/src/content.ts` — 選択座標取得、簡易オーバーレイUIの描画

**Verification**
1. FastAPIサーバーを `uvicorn src.browser_api.main:app --reload` で起動し、エラーなく立ち上がるか（CORSの有効化）。
2. ブラウザ上でテキストを選択して右クリック -> [翻訳テスト] をクリックした際、Content Script のオーバーレイに選択テキスト、正しく Crop された画像、AI の応答結果（またはモック）が表示されるか。
3. 画像切り抜きのパフォーマンス（Canvas処理時間）がコンソールログ上で数ミリ秒〜数十ミリ秒以内に収まり、著しいラグを引き起こしていないか確認する。
4. 拡張機能の manifest に `host_permissions` が含まれ、Background から `127.0.0.1` / `localhost` の両方へ疎通できることを確認する。
5. ブラウザ倍率や OS スケーリングが入っていても、返送された viewport 情報を使うことで crop 領域が目視で大きくずれないことを確認する。

**Decisions**
- API のエンドポイント起動は既存の `pyproject.toml` 依存関係として FastAPI 等を導入。
- 起動トリガーは「コンテキストメニュー（右クリック）からの実行」とする。
- 通信経路はセキュリティ考慮のため、Content Script -> Background -> FastAPI とする。
- 画面画像の取得後、Crop/Resize 等の加工は TS 拡張機能の Background 層 (OffscreenCanvas 等) で完結させる。
- 検証結果は F12 コンソールだけでなく、Content Script 上からの「簡易的なオーバーレイ表示」として描画する。
- ローカル API 呼び出し先は Phase 0 では `http://127.0.0.1:8000` を正としつつ、manifest の `host_permissions` は `localhost` も許可して環境差分に備える。
- crop の座標系は DOM 座標をそのまま使わず、Content Script が返す viewport 情報とキャプチャ画像の実寸から Background 側でスケール変換して決定する。
- FastAPI 側でも `.env` 読み込みと既存 `AppConfig` / `AIModel` 初期化を明示し、デスクトップ版と API キー管理の前提を揃える。
