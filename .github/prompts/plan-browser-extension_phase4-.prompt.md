# Phase 4 Implementation Prompt

## 目的

`gem-read` リポジトリ内の browser extension と local browser API について、Phase 4 を **article context intelligence** として実装してください。

今回の Phase 4 は、既存の overlay、batch session、keyboard workflow、image-assisted analysis を前提に、
**記事全文抽出、Context Cache、トークン計測、長文記事向け UX** を追加することが目的です。

## 今回のスコープ

- 記事本文全体抽出の導入
- Readability 優先の汎用抽出フローの追加
- 抽出失敗時のフォールバック設計
- browser_api での Context Cache API 公開
- cache 作成、状態確認、削除の実装
- 1 タブ 1 アクティブ cache の管理
- URL 変更、model 変更、TTL 切れ、本文ハッシュ不一致時の cache invalidation
- トークン事前計測 API の追加
- overlay における送信前見積もり、cache 作成前比較、結果後の実績表示
- 長文記事向け overlay UI 改善
- unit test、pytest、Playwright smoke、必要なドキュメント更新

## 今回の非スコープ

以下は今回の実装に含めないこと。

- ブラウザ全体で複数 cache を切り替える高度な cache browser
- タブを跨いだ cache 共有
- browser restart 後の cache session 復元 UI
- OCR の常時実行
- すべてのサイトに対する専用 selector 実装
- SaaS 化や remote backend 化

## 既存の前提

- browser-extension 側には既に overlay、batch session、rectangle selection、rich text rendering、keyboard-first workflow がある。
- background 側には `runSelectionAnalysis`、`appendSelectionSessionItem`、`analysisSessionStore` がある。
- browser_api 側には `/health`、`/models`、`/analyze/translate` があり、`AnalyzeService` が analyze フローを集約している。
- `src/pdf_epub_reader/models/ai_model.py` には既に `count_tokens`、`create_cache`、`get_cache_status`、`delete_cache`、`invalidate_cache`、`list_caches` が存在する。
- Phase 4 では、これら既存 Python 資産を browser_api 経由で安全に公開する。

## 実装上の決定事項

### Article Extraction

- 記事全文抽出は **Readability 優先** とする。
- まず汎用抽出を試し、失敗時のみフォールバックへ進むこと。
- フォールバックは少なくとも以下を持つこと。
  - 選択テキストのみ送信へ戻す
  - 必要に応じた軽量な DOM ベース補助抽出
- Phase 4 では、個別サイト専用 selector は最小限のフックだけ用意し、大量追加はしないこと。

### Cache Granularity

- Context Cache は **1 タブ 1 アクティブ cache** を基本とする。
- 同一タブで新しい本文 cache を作る場合、既存 active cache を置き換えてよい。
- tab ごとの cache state は browser-extension 側でも管理するが、Gemini 上の実体は browser_api 経由で扱うこと。

### Cache Creation

- cache 作成は **常時自動ではなく条件付き自動** とする。
- 少なくとも以下を満たす場合に自動作成候補とすること。
  - 記事全文抽出に成功している
  - テキスト長または token 見積もりが閾値以上
  - 利用モデルが cache 対応想定である
- 自動作成対象でも、UX 上は無言で隠すのではなく、cache 化の状態が分かるようにすること。

### Cache Invalidation

- 以下で active cache を無効化対象とすること。
  - URL 変更時
  - model 変更時
  - TTL 切れ時
  - 本文ハッシュ不一致時
  - ユーザーの手動削除時
- invalidation 失敗時は local state と remote state がずれないよう、degraded 表示を用意すること。

### Token UX

- トークン計測は以下 3 箇所を対象とすること。
  - 送信前見積もり
  - cache 作成前比較
  - 結果後の実績表示
- token count が利用できない場合は、overlay 全体を壊さずに非表示または degraded 表示へフォールバックすること。

### Session Persistence

- Phase 4 でも browser-extension 側の session は tab lifetime ベースを維持してよい。
- ただし cache 状態は、少なくとも tab 内の article context と対応づく形で再解決できるようにすること。

## Phase 分け

Phase 4 は一括実装せず、以下のサブフェーズに分けて進めること。

### Phase 4A: Article Context Foundation

目的:

- article context を扱う最小の土台を作る。
- 記事全文抽出を導入し、selection fallback を成立させる。

主な対象:

- browser-extension 側の article extraction 導入
- Readability 優先の抽出フロー
- タイトル、URL、本文ハッシュを含む article context 形状の整理
- 抽出失敗時の fallback 動作
- browser-extension unit test の基礎追加

完了条件:

- article context を抽出できるページでは、本文、タイトル、URL、本文ハッシュが安定して得られる。
- 抽出失敗時は既存の selection-based flow に戻れる。
- overlay や既存 batch / rectangle / custom prompt フローを壊さない。

### Phase 4B: Browser API Cache / Token Surface

目的:

- Python 側に既にある cache / token 機能を browser_api から安全に公開する。

主な対象:

- `GET /cache/status`
- `POST /cache/create`
- `DELETE /cache/{cache_name}` または同等 endpoint
- `POST /tokens/count`
- schema、service、error mapping の整備
- pytest 追加

完了条件:

- browser_api 経由で cache create / status / delete が利用できる。
- token count を取得できる。
- missing model、missing key、unsupported cache model、upstream failure が安定して HTTP へ変換される。

### Phase 4C: Extension Cache Integration

目的:

- article context と cache 状態を tab 単位で結びつけ、分析フローに統合する。

主な対象:

- 1 タブ 1 アクティブ cache の state 管理
- cache 自動作成候補の判定
- URL 変更、model 変更、TTL 切れ、本文ハッシュ不一致時の invalidation
- localApiGateway から cache / token API を使う配線
- background session と article context の連携

完了条件:

- tab ごとに active article context と active cache を追跡できる。
- cache invalidation 条件が動作し、overlay 再表示時にも状態が復元される。
- cache state と selection session が競合せず共存する。

### Phase 4D: Overlay UX / Validation

目的:

- 長文記事向け UI と token / cache UX を仕上げ、E2E と docs を揃える。

主な対象:

- overlay での送信前 token 見積もり表示
- cache 作成前比較表示
- 結果後の usage 実績表示
- cache status と degraded state の可視化
- Playwright smoke 更新
- developer / user docs 更新

完了条件:

- overlay 上で article context、cache 状態、token 情報を区別して表示できる。
- token count が使えない場合でも overlay 全体が壊れない。
- test suite と build が通る。

## 主に触るファイル

- `browser-extension/src/shared/contracts/messages.ts`
- `browser-extension/src/shared/gateways/localApiGateway.ts`
- `browser-extension/src/background/entry.ts`
- `browser-extension/src/background/usecases/runSelectionAnalysis.ts`
- `browser-extension/src/background/services/analysisSessionStore.ts`
- `browser-extension/src/background/services/` 配下の新規 cache / extraction / token service
- `browser-extension/src/content/overlay/renderOverlay.ts`
- `browser-extension/src/content/selection/` 配下の extraction 関連モジュール
- `browser-extension/src/popup/ui/renderPopup.ts` または必要なら settings 導線
- `src/browser_api/api/app.py`
- `src/browser_api/api/routers/` 配下の新規 `cache.py` と `tokens.py`
- `src/browser_api/api/schemas/` 配下の cache / token schema
- `src/browser_api/application/services/analyze_service.py` または責務分割した新規 service
- `src/browser_api/adapters/ai_gateway.py`
- `src/pdf_epub_reader/models/ai_model.py` の既存 cache / token API
- `tests/test_browser_api/...`
- `browser-extension/__tests__/...`
- `docs/developer/testing.md`
- `docs/user/operations.md`
- `docs/user/settings-and-cache.md`

## 実装要件

### Phase 4A の要件

1. browser-extension 側に article extraction の責務を追加すること。
2. Readability を優先し、抽出本文、タイトル、URL、本文ハッシュなど article context をまとめて扱える形にすること。
3. 抽出に失敗した場合、選択ベースの既存フローに安全に戻れること。
4. article extraction の成功系と fallback 系を unit test でカバーすること。

### Phase 4B の要件

1. browser_api に少なくとも以下の endpoint を追加すること。
   - `GET /cache/status`
   - `POST /cache/create`
   - `DELETE /cache/{cache_name}` または同等の delete endpoint
   - `POST /tokens/count`
2. router から `AIModel` を直接呼ばず、既存の application / adapter 経由の責務分離を守ること。
3. `AIKeyMissingError`、cache unsupported、upstream API failure のエラー表現を整理すること。
4. 必要なら text only と text + image で response schema に差異が出ないよう正規化すること。
5. pytest で以下を最低限カバーすること。
   - cache create
   - cache status
   - cache delete
   - token count
   - upstream failure mapping
   - missing model / missing key / unsupported cache model

### Phase 4C の要件

1. tab ごとに active article context と cache 状態を結び付けること。
2. Context Cache は 1 タブ 1 アクティブ cache を基本とすること。
3. 記事全文抽出成功、十分な本文量または token 見積もり、対象モデルという条件を満たしたときのみ、条件付き自動 cache 作成候補にすること。
4. model 変更や URL 変更で invalidation が走る場合、ユーザーに分かる表示を行うこと。
5. TTL 切れ、本文ハッシュ不一致、手動削除時も invalidation が反映されること。
6. cache state transition と invalidation 条件を unit test でカバーすること。

### Phase 4D の要件

1. 送信前に article context または current payload の token 見積もりを表示すること。
2. cache 作成前には、cache 化のメリットがある程度分かる比較表示を入れること。
3. 結果後には、取得可能であれば usage 実績を表示すること。
4. 長文記事前提で、selection batch と article context の区別が付く UI にすること。
5. cache status、token info、degraded state を overlay 上で扱えるようにすること。
6. UI が複雑化しても既存の selection / rectangle / custom prompt フローを壊さないこと。
7. Playwright smoke では article context を持つページに対し、抽出、cache 状態表示、token 表示、既存 selection rerun が共存する flow を通すこと。
8. developer docs に Phase 4 のテストコマンドと確認観点を追記すること。
9. user docs に cache の意味、いつ作成されるか、いつ消えるか、token 表示の意味を追記すること。
10. unsupported pages や抽出失敗時は selection fallback になる点を明記すること。

## 実装時の制約

- 既存の entry file は thin のまま維持すること。
- Local API 通信は引き続き background 経由とすること。
- `AIModel` の既存 cache / token 実装を再利用し、browser_api 側で重複実装しないこと。
- Phase 3 の keyboard workflow を壊さないこと。
- 抽出失敗や token 計測失敗で overlay 全体が unusable にならないこと。
- 過剰な site-specific 実装に寄りすぎず、まず汎用抽出の成功率を上げること。

## 完了条件

- Phase 4A から 4D までを順に完了した結果、article context を抽出できるページでは、selection とは別に全文コンテキストを利用できる。
- browser_api 経由で cache create / status / delete が動く。
- token count が取得でき、overlay に送信前または cache 前比較として表示できる。
- URL 変更、model 変更、TTL 切れ、本文ハッシュ不一致時に cache invalidation が反映される。
- 抽出失敗時は selection-based flow に戻れる。
- 既存の Phase 3 操作系と共存し、test suite と build が通る。

## 実装順の指示

以下の順序で進めること。

1. Phase 4A を完了してから Phase 4C に進むこと。
2. Phase 4B は Phase 4A と並行可能だが、Phase 4C 開始前に完了していること。
3. Phase 4D は Phase 4A から 4C の結果を前提に仕上げること。
4. 各サブフェーズ完了時に、追加したテストと未解決事項を簡潔に整理すること。

## 実行コマンド

- `npm run test`
- `npm run test:e2e`
- `npm run build`
- `uv run pytest tests/test_browser_api/ -q`
- 必要に応じて `uv run pytest tests/ -q`

必要に応じて Chrome / Edge 手動確認も行い、記事抽出、cache 状態、token 表示、selection fallback の結果を簡潔にまとめること。