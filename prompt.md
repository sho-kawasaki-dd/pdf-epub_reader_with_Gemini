# Phase 3 Implementation Prompt

## 目的

`gem-read` リポジトリ内の browser extension について、Phase 3 を **keyboard-first workflow 改善** として実装してください。

今回の Phase 3 は、既存の overlay、batch session、rectangle selection、background session reuse を前提に、
**ショートカットと overlay 内キーバインドの統一** を完成させることが目的です。

## 今回のスコープ

- browser command の追加と配線
- overlay の再表示と launcher fallback
- 現在の text selection を batch に追加するショートカット
- 既存の自由矩形選択ショートカットの正式サポート
- overlay 内のキーボード操作
- last action / model / custom prompt の再実行
- popup の overlay 起動導線を command ベースの流れに寄せる
- unit test と Playwright smoke の追加更新
- 必要な developer / user ドキュメント更新

## 今回の非スコープ

以下は **Phase 4 以降** に送るため、今回の実装では入れないこと。

- 記事本文全体抽出
- Readability 導入
- Context Cache の browser_api 公開
- トークン事前計測
- サイトごとの抽出最適化
- 永続 session 復元

## 既存の前提

- browser-extension 側には既に overlay、batch session、rectangle selection、rich text rendering、settings persistence がある。
- background 側には `runSelectionAnalysis`、`appendSelectionSessionItem`、`analysisSessionStore` があり、session 再利用の流れがある。
- 既存の rectangle command はすでに `manifest.json` と `background/entry.ts` にある。
- popup には `Open Overlay Shortcut` ボタンがあり、現在は軽量 overlay を直接表示している。

## 実装上の決定事項

### Browser Commands

- overlay の再表示: `Ctrl+Shift+O` / `Command+Shift+O`
- 現在の text selection を batch に追加: `Ctrl+Shift+B` / `Command+Shift+B`
- 自由矩形選択 UI の開始: `Ctrl+Shift+Y` / `Command+Shift+Y`

### Overlay Reopen の仕様

- cached session が存在する場合は、その session をそのまま復元する。
- cached session が存在しない場合は、**launcher-only overlay** を表示する。
- reopen でも draft model と draft custom prompt は失わないこと。

### Batch Add Shortcut の仕様

- `Ctrl+Shift+B` では **現在の live text selection のみ** を batch に追加する。
- live selection が無い場合は、何も起こらないのではなく、overlay 上に明示的なエラーを表示する。
- 直前の rectangle selection や直前 session item を暗黙再利用しないこと。

### Overlay Key Bindings

- `Esc`: overlay を minimize する。rectangle selection 中は既存の cancel 動作を維持する。
- `Shift+Esc`: overlay を閉じて session を clear する。
- `Ctrl+Enter` / `Command+Enter`: custom prompt textarea 内でのみ送信する。
- `Alt+R` / `Option+R`: focus が editable control の外にあるときだけ、last action / last model / last custom prompt を再実行する。

### Session Persistence

- session は tab lifetime のみ保持する。
- reload 後や browser restart 後の復元は今回は扱わない。

### Popup の位置づけ

- popup の `Open Overlay Shortcut` は廃止しない。
- ただし正式な主導線は browser command とし、popup は補助導線として同じ overlay-open flow に寄せること。

## 主に触るファイル

- `browser-extension/manifest.json`
- `browser-extension/src/shared/config/phase0.ts`
- `browser-extension/src/shared/contracts/messages.ts`
- `browser-extension/src/background/entry.ts`
- `browser-extension/src/background/usecases/runSelectionAnalysis.ts`
- `browser-extension/src/background/usecases/updateSelectionSession.ts`
- `browser-extension/src/background/services/analysisSessionStore.ts`
- `browser-extension/src/background/gateways/tabMessagingGateway.ts`
- `browser-extension/src/content/entry.ts`
- `browser-extension/src/content/overlay/renderOverlay.ts`
- `browser-extension/src/content/selection/snapshotStore.ts`
- `browser-extension/src/popup/ui/renderPopup.ts`
- `browser-extension/__tests__/...`
- `docs/developer/testing.md`
- `docs/user/operations.md`

## 実装要件

1. browser command の追加

- `manifest.json` に overlay reopen と batch add command を追加すること。
- command id は shared config に集約し、`background/entry.ts` で dispatch すること。

2. background orchestration の統一

- command ごとに専用 handler を用意してよいが、状態の正本は既存どおり `analysisSessionStore` に置くこと。
- 既存の `runSelectionAnalysis`、`appendSelectionSessionItem`、`buildOverlayPayload` を優先再利用すること。
- command 用の別 session store や別 overlay state を新設しないこと。

3. overlay reopen の実装

- reopen command 実行時、対象 tab に content script が生きていれば overlay を表示すること。
- session があれば batch と last action が復元されること。
- session が無ければ launcher-only overlay を表示すること。

4. batch add command の実装

- active tab の現在 selection を収集し、既存 batch へ append すること。
- capture と crop は既存の append path に寄せること。
- selection が無い場合は overlay に分かりやすいエラーを出すこと。

5. overlay key handling の実装

- `renderOverlay.ts` に overlay root を owner とする keyboard handling を追加すること。
- `Esc`、`Shift+Esc`、`Ctrl/Command+Enter`、`Alt/Option+R` の条件分岐を整理すること。
- textarea、input、contenteditable への誤作動を避けること。
- rerun は既存の `phase1.runOverlayAction` に流すこと。

6. popup helper の整合

- popup の overlay 起動ボタンは、Phase 3 で作る reopen/open の考え方と矛盾しないよう整理すること。
- popup だけ別文言・別状態管理になる実装は避けること。

7. テスト

- unit test を追加し、最低でも以下をカバーすること。
  - command dispatch
  - overlay reopen with cached session
  - overlay reopen without cached session
  - batch add success
  - batch add without live selection
  - `Esc` minimize
  - `Shift+Esc` close and clear
  - `Ctrl/Command+Enter` custom prompt submit
  - `Alt/Option+R` rerun
- Playwright smoke では native context menu 自動化に頼らず、keyboard 主体の flow を通すこと。

8. ドキュメント

- developer testing docs に keyboard workflow の検証手順を追加すること。
- user docs に shortcut と制約を追記すること。
- restricted pages など content script を挿せないページでは command が期待どおり動かない点を明記すること。

## 実装時の制約

- 既存の entry file は thin のまま維持すること。
- command 起点でも Local API 通信は background 経由を崩さないこと。
- 既存の rich text rendering や batch UI の構造を不必要に作り直さないこと。
- 既存の session 再利用パターンを壊さないこと。
- 影響範囲外の Phase 4 機能を先回りで入れないこと。

## 完了条件

- Chrome / Edge で command が認識される。
- overlay の reopen、minimize、close、rerun が keyboard で完結する。
- custom prompt は textarea から keyboard 送信できる。
- batch add shortcut が text selection に対して機能する。
- no-selection 時に silent failure にならない。
- 既存 test suite と build が通る。

## 実行コマンド

- `npm run test`
- `npm run test:e2e`
- `npm run build`

必要に応じて Chrome / Edge 手動確認も行い、結果を簡潔にまとめること。