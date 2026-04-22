# Browser Extension UI Language Plan

## 目的

本企画書は、`browser-extension/` の UI を日本語 / English で切り替え可能にするための実装方針をまとめる。
対象は popup、overlay、context menu、実行時エラーメッセージとし、初回既定値は `chrome.i18n.getUILanguage()` を用いて決定する。

## 背景

現状の browser-extension では、UI 文言が popup、content overlay、background の menu 生成、各 runtime のエラー文言に分散している。

- popup 文言は `browser-extension/src/popup/ui/renderPopup.ts` に直書きされている
- overlay 文言は `browser-extension/src/content/overlay/renderOverlay.ts` と `browser-extension/src/content/overlay/overlayActions.ts` に分散している
- context menu 文言は `browser-extension/src/background/menus/phase0ContextMenu.ts` で生成している
- runtime error は `background/usecases/`、`background/services/`、`content/selection/` などで直接 message string を作っている

この状態では popup だけに言語設定を追加しても UI 全体の言語は切り替わらない。
そのため、shared に locale 解決と辞書参照の仕組みを置き、background / content / popup から共通利用できる形へ揃える必要がある。

## スコープ

今回の対象は次の通りとする。

- popup UI の全固定文言
- overlay UI の全固定文言
- background が生成する context menu title
- UI に表示される実行時エラーメッセージ

今回の対象外は次の通りとする。

- `manifest.json` の `name`、`description`、`commands.description` の多言語化
- Chrome Web Store 表示文言の多言語化
- 3 言語目以降の対応
- `system` 追従モードの追加
- すでに開いている overlay のリアルタイム言語切り替え（言語変更後、次回 overlay 起動時またはページリロード時から反映されるものとする）

`manifest.json` の静的文言まで多言語化する場合は `_locales/` と manifest i18n を別途導入する必要があるが、今回は runtime UI の手動切り替えを優先する。

## 要件

### 必須要件

- popup に UI 言語選択項目を追加する
- 選択肢は `日本語` と `English` の 2 つに限定する
- 設定未保存時は `chrome.i18n.getUILanguage()` を参照して初期言語を決定する
- `ja` 系 locale なら日本語にする
- それ以外は英語にする
- locale が取得できない、または判定できない場合は英語にする
- popup、overlay、context menu、実行時エラー表示の言語が保存設定に従って切り替わる
- popup で言語設定を保存したら、その後に開く popup / overlay / context menu に反映される

### 補足要件

- 既存の settings 保存形式との後方互換性を維持する
- 旧 settings からの migration を明示的な破壊変更なしで吸収する
- 各 runtime で別々に locale 判定ロジックを持たない
- 文言の新規追加時に辞書の抜け漏れが分かりやすい構成にする

## 基本方針

### 1. 言語設定は persisted value を持つ

設定には `uiLanguage` を追加し、保存値は次の 2 値に限定する。

- `ja`
- `en`

初回のみ `chrome.i18n.getUILanguage()` で既定値を決める。
一度保存された後は OS / browser locale が変わっても自動追従しない。

この方針を採る理由は次の通り。

- popup 上の手動選択を最優先にできる
- runtime ごとに locale を再判定して表示が揺れるのを防げる
- 既存の settings storage パターンに自然に乗せられる

### 2. locale 判定は shared に集約する

locale 判定と正規化は `shared/` に置き、popup / background / content が同じ関数を使う。

想定する責務は次の通り。

- 生 locale 文字列を受けて `ja` / `en` へ正規化する
- `chrome.i18n.getUILanguage()` の結果を既定値へ変換する
- `uiLanguage` 設定値が欠けている legacy settings を安全に補完する

### 3. 文言辞書も shared に集約する

翻訳辞書は runtime ごとに分けず、shared の単一辞書群として持つ。

理由は次の通り。

- popup、overlay、background menu で同じキー体系を使える
- 実行時エラーメッセージの英日差し替えを一箇所で管理できる
- テストで ja / en の両方を同一 API で検証できる

## 既定 locale の解決仕様

### 判定ルール

初回設定時の既定 locale は次の順で決める。

1. `chrome.i18n.getUILanguage()` を試す
2. 取得値が `ja` で始まるなら `ja`
3. それ以外なら `en`
4. API が使えない、空文字、例外時も `en`

### 例

- `ja`
- `ja-JP`
- `ja-jp`

上記はすべて `ja` に正規化する。

- `en`
- `en-US`
- `fr-FR`
- `zh-CN`
- `undefined`
- `''`

上記はすべて `en` に正規化する。

### 注意点

`chrome.i18n.getUILanguage()` は厳密には OS locale ではなく browser UI language 寄りの値だが、Chrome 拡張の runtime で一貫して取得しやすい情報として採用する。
今回の仕様では「ja 系か、それ以外か」の 2 択しか扱わないため、この近似で十分と判断する。

## データモデル変更案

### `ExtensionSettings`

`browser-extension/src/shared/config/phase0.ts` に `uiLanguage` を追加する。

想定型:

```ts
export type UiLanguage = 'ja' | 'en';

export interface ExtensionSettings {
  apiBaseUrl: string;
  defaultModel: string;
  sharedSystemPrompt: string;
  lastKnownModels: string[];
  uiLanguage: UiLanguage;
  articleCache: ArticleCacheSettings;
  markdownExport: MarkdownExportSettings;
}

export interface ExtensionSettingsInput {
  apiBaseUrl?: string | null;
  defaultModel?: string | null;
  sharedSystemPrompt?: string | null;
  lastKnownModels?: readonly string[] | null;
  uiLanguage?: UiLanguage | null;
  articleCache?: Partial<ArticleCacheSettings> | null;
  markdownExport?: Partial<MarkdownExportSettings> | null;
}
```

### default 値の扱い

方式 B を採用する。

- `DEFAULT_EXTENSION_SETTINGS.uiLanguage` は `'en'` 固定とする
- `mergeExtensionSettings()` は `uiLanguage` の `null` / `undefined` / 不正値を `'en'` に正規化する（他フィールドと同じパターン）
- `loadExtensionSettings()` は `mergeExtensionSettings()` 適用後に、storage に `uiLanguage` が保存されていなかった場合のみ `detectDefaultUiLanguage()` で上書きする
- `loadExtensionSettings()` が locale 注入を行う唯一の場所であり、`mergeExtensionSettings()` は locale 検出を行わない

この方針により、テスト環境や `chrome.i18n` が使えない環境でも `'en'` として安全に動作する。また、`saveExtensionSettings()` / `patchExtensionSettings()` が `uiLanguage` を無言で落とす危険を防ぐ。

## shared i18n レイヤー設計

### 追加候補ファイル

- `browser-extension/src/shared/i18n/uiLanguage.ts`
- `browser-extension/src/shared/i18n/messages.ts`
- `browser-extension/src/shared/i18n/translator.ts`

### `uiLanguage.ts` の責務

- locale string を `ja` / `en` へ正規化する関数
- `chrome.i18n.getUILanguage()` を既定設定へ変換する関数

`UiLanguage` 型は `phase0.ts` に定義し、`uiLanguage.ts` が import する。
`phase0.ts` は外部依存ゼロを維持し、`i18n/` が `phase0.ts` に依存する方向を保つ。

import 方向:

```
phase0.ts           ← UiLanguage 型定義、mergeExtensionSettings で uiLanguage を正規化
  ↑ import
i18n/uiLanguage.ts  ← normalizeUiLanguage(), detectDefaultUiLanguage()
  ↑ import
i18n/translator.ts  ← t()
```

想定 API:

```ts
import type { UiLanguage } from '../config/phase0';

export function normalizeUiLanguage(
  value: string | null | undefined
): UiLanguage;
export function detectDefaultUiLanguage(): UiLanguage;
```

### `messages.ts` の責務

- ja / en の辞書本体を保持する
- popup / overlay / context menu / error message 用キーをまとめる
- TypeScript の `satisfies Record<UiLanguage, MessageDictionary>` パターン等を用いて、言語間の翻訳抜け漏れ（キーの不足）をコンパイル時に検知できる静的型定義を構成する

想定イメージ:

```ts
type MessageDictionary = {
  popupTitle: string;
  popupSave: string;
  contextMenuTranslate: string;
};

export const UI_MESSAGES = {
  en: {
    popupTitle: 'Local Bridge',
    popupSave: 'Save',
    contextMenuTranslate: 'Translate with Gem Read',
  },
  ja: {
    popupTitle: 'Local Bridge',
    popupSave: '保存',
    contextMenuTranslate: 'Gem Read で翻訳',
  },
} satisfies Record<UiLanguage, MessageDictionary>;
```

### `translator.ts` の責務

- `UiLanguage` と key から文言を返す
- 置換パラメータ付き message を組み立てる

想定 API:

```ts
export function t(
  language: UiLanguage,
  key: MessageKey,
  params?: Record<string, string | number>
): string;
```

置換パラメータは次のようなケースで使う。

- `You can keep up to {count} selections in one batch.`
- `最大 {count} 件まで選択を保持できます。`

## popup 変更計画

### popup 対象

- `browser-extension/src/popup/ui/renderPopup.ts`

### popup 実施内容

- settings form に `UI Language` 選択項目を追加する
- 選択肢は `日本語` と `English` の 2 件にする
- 初回表示時は `loadExtensionSettings()` の `uiLanguage` を反映する
- 保存時に `saveExtensionSettings()` へ `uiLanguage` を渡す
- popup 内の固定文言、status、hint、debug 表示文言を辞書参照へ置き換える

### popup 実装上のポイント

- `renderPopup()` の `innerHTML` テンプレートは、組み立て前に `language` を決めて文言差し替えする
- `formatStatusBadge()`、`formatStatusLine()`、`formatSourceLine()`、`setMessage()`、`renderDebugCacheList()` も辞書参照へ寄せる
- popup で言語を保存した直後は、その popup 自身も保存後文言へ再描画できる構成にする

### popup で追加する設定項目イメージ

- Label: `UI Language` / `表示言語`
- Option: `日本語`
- Option: `English`

## overlay 変更計画

### overlay 対象

- `browser-extension/src/content/overlay/renderOverlay.ts`
- `browser-extension/src/content/overlay/overlayActions.ts`

### overlay 実施内容

- OverlayPayload に `uiLanguage` を追加する
- background が overlay 描画 payload を組み立てるときに必ず `uiLanguage` を注入する
- overlay の固定文言をすべて辞書参照へ置き換える
- overlayActions 側のクライアントエラーメッセージも辞書参照にする

### 文言対象の例

- selection empty state
- result label
- action hint
- batch hint
- banner text
- Gemini empty state
- raw response details label
- export button
- custom prompt validation error
- add selection / remove item / image toggle 失敗メッセージ

### 実装上のポイント

- content runtime 単独で locale 判定しない
- background が settings を読んで payload に含めることで、overlay の表示言語を常に保存設定へ一致させる
- `buildOverlayPayload()` と `buildEmptyOverlayPayload()` の `options` 引数に `uiLanguage` を追加し、呼び出し元が `settings.uiLanguage` を渡す形にする

  ```ts
  // options 型への追加
  options: {
    status?: OverlayPayload['status'];
    error?: string;
    launcherOnly?: boolean;
    preserveDrafts?: boolean;
    uiLanguage?: UiLanguage;  // 追加
  }
  ```

  呼び出し箇所は `openOverlaySession.ts`、`updateSelectionSession.ts`、`entry.ts` 内の複数箇所に及ぶ。すべての呼び出し元で `settings.uiLanguage` を渡す。session に `uiLanguage` を持たせる方式は session の責務を広げすぎるため採用しない。`buildOverlayPayload()` 内部で settings を再読みする方式は非同期化が必要でコストが増すため採用しない。

- `overlayActions.ts` のエラー文言は、`uiLanguage` が必要な関数に `payload: OverlayPayload` または `uiLanguage: UiLanguage` を直接引数として渡す形で対応する。モジュール変数で保持する方式は複数タブ時に言語が混線する危険があるため採用しない

## context menu 変更計画

### context menu 対象

- `browser-extension/src/background/menus/phase0ContextMenu.ts`
- `browser-extension/src/background/entry.ts`

### context menu 実施内容

- `ensurePhase0ContextMenu()` に `uiLanguage: UiLanguage` 引数を追加して menu title を生成するようにする
  - 内部で `loadExtensionSettings()` を呼ぶ方式は非同期依存が重複するため採用しない
  - install / startup / storage change のすべての経路で直前に settings を読むため、その値を引数として渡す
- install / startup 時だけでなく、`uiLanguage` 変更時にも context menu を再生成する
  - 対象は translation 用メニューと自由矩形開始メニューの両方とする

### 反映方法

第一候補は `chrome.storage.onChanged` を background で監視する方式とする。

理由は次の通り。

- popup と background を直接結合しなくて済む
- 将来 settings の更新元が popup 以外に増えても追従しやすい
- service worker 再起動後も同じ初期化パターンを保ちやすい

### 想定フロー

1. popup が `saveExtensionSettings()` で `uiLanguage` を保存する
2. background が `chrome.storage.onChanged` で `gem-read.settings` 変更を受ける
3. `uiLanguage` に差分があれば `ensurePhase0ContextMenu(next.uiLanguage)` を再実行する
4. 以後の右クリックメニューは新しい言語で表示される

`uiLanguage` 変化の差分検出は次のように行う。

```ts
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local') return;
  const settingsChange = changes[EXTENSION_SETTINGS_STORAGE_KEY];
  if (!settingsChange) return;
  const prev = settingsChange.oldValue as ExtensionSettings | undefined;
  const next = settingsChange.newValue as ExtensionSettings | undefined;
  if (prev?.uiLanguage !== next?.uiLanguage && next) {
    void ensurePhase0ContextMenu(next.uiLanguage ?? detectDefaultUiLanguage());
  }
});
```

## 実行時エラーメッセージ変更計画

### 対象カテゴリ

- background usecase が overlay に返す error
- background service が throw する UI 向け error
- content 側で即時表示する validation error
- selection 取得失敗などのユーザー向け案内

今回の Phase では、上記 4 類型をすべて辞書化の対象とし、Phase 4 へ棚卸しを持ち越さない。

### エラーメッセージ基本方針

ユーザーに見える可能性がある message string は、可能な限り辞書 key から組み立てる。

### 例外的にそのまま出すもの

- Local API のレスポンス本文
- 低レベルなネットワークエラー詳細
- 外部由来の予期しない raw error

これらは完全翻訳しきれないため、外側だけをローカライズした message に包む。

例:

- ja: `ポップアップ設定の保存に失敗しました: {detail}`
- en: `Failed to save popup settings: {detail}`

### 実装上のルール

- UI へ直接出す既知エラーは `t(language, key)` で組み立てる
- Background 側で発生した UI 向けエラー（usecase が overlay へ返すエラーなど）は、Background 自身が設定から保持している `uiLanguage` を用いて Background 内で翻訳済み文字列として構築し、Content (Overlay) 側へ文字列として渡す境界設計を基本とする
- 想定外エラーは `toErrorMessage()` 系 helper で detail を連結する
- 低レベル層で locale を持ち回る必要がある場合は、文字列を throw するより UI key を返す設計も検討する

## runtime ごとの言語取得責務

### popup の責務

- `loadExtensionSettings()` で取得した `uiLanguage` を使う
- 設定未保存時のみ shared の default locale 解決を使う

### background の責務

- settings 読み出し時に `uiLanguage` を必ず取得する
- context menu 生成と overlay payload 組み立てに使う

### content の責務

- 独自に `chrome.i18n.getUILanguage()` を呼ばない
- background から受け取った `OverlayPayload.uiLanguage` を使う

この役割分担により、表示言語の決定権は settings に一本化される。

## 影響ファイル候補

### 共有設定と i18n

- `browser-extension/src/shared/config/phase0.ts`
- `browser-extension/src/shared/storage/settingsStorage.ts`
- `browser-extension/src/shared/contracts/messages.ts`
- `browser-extension/src/shared/i18n/uiLanguage.ts`
- `browser-extension/src/shared/i18n/messages.ts`
- `browser-extension/src/shared/i18n/translator.ts`

### popup

- `browser-extension/src/popup/ui/renderPopup.ts`

### background

- `browser-extension/src/background/entry.ts` — `chrome.storage.onChanged` リスナー追加と、`runSelectionAnalysis` 完了後の `buildOverlayPayload()` 呼び出し（L512 付近）への `uiLanguage` 注入
- `browser-extension/src/background/menus/phase0ContextMenu.ts` — `ensurePhase0ContextMenu(uiLanguage)` 引数追加
- `browser-extension/src/background/usecases/openOverlaySession.ts`
- `browser-extension/src/background/usecases/updateSelectionSession.ts` — `buildOverlayPayload()` / `buildEmptyOverlayPayload()` の `options` 拡張
- `browser-extension/src/background/usecases/runSelectionAnalysis.ts`

### content

- `browser-extension/src/content/overlay/renderOverlay.ts`
- `browser-extension/src/content/overlay/overlayActions.ts`
- `browser-extension/src/content/selection/snapshotStore.ts` — UI 向けエラー文言があれば辞書参照へ移行、なければ変更不要（Phase 1 の棚卸しで確定する）

### 追加確認対象

これら 3 ファイルは Phase 1 完了前に UI 向け文言の有無を棚卸しし、変更が必要かどうかを確定する。UI 向け文言が見つかった場合は、その場で今回のローカライズ対象に含める。

- `browser-extension/src/background/services/cropSelectionImage.ts`
- `browser-extension/src/background/services/markdownExportService.ts`
- `browser-extension/src/background/services/analysisSessionStore.ts`

## 実装ステップ案

### Phase 1: shared 基盤

- `phase0.ts` に `UiLanguage` 型を追加し、`DEFAULT_EXTENSION_SETTINGS.uiLanguage` を `'en'` で追加する
- `mergeExtensionSettings()` に `uiLanguage` の正規化ルール（`null` / `undefined` / 不正値 → `'en'`）を追加する
- `settingsStorage.ts` の `loadExtensionSettings()` に locale 注入ロジックを追加する（`uiLanguage` が storage 未保存の場合のみ `detectDefaultUiLanguage()` で補完）
- `i18n/uiLanguage.ts` に `normalizeUiLanguage()` と `detectDefaultUiLanguage()` を追加する（`UiLanguage` 型は `phase0.ts` から import）
- 文言辞書 `i18n/messages.ts` と translator `i18n/translator.ts` を追加する
- 「追加確認対象」3 ファイル（`cropSelectionImage.ts`、`markdownExportService.ts`、`analysisSessionStore.ts`）の UI 向け文言有無を棚卸しし、Phase 4 の対象に含めるか確定する

### Phase 2: popup

- popup に言語選択 UI を追加
- popup の全固定文言を辞書参照へ移行
- save / refresh / debug 系メッセージをローカライズ

### Phase 3: overlay

- OverlayPayload に `uiLanguage` を追加
- background の payload builder から言語注入
- overlay / overlayActions の固定文言を移行

### Phase 4: context menu と runtime error

- context menu title のローカライズ
- `storage.onChanged` による再生成導線を追加
- background / content のユーザー向け error 文言を辞書参照へ移行

### Phase 5: テスト整理

- shared settings / locale 判定テスト
- popup 描画と保存テスト
- overlay 文言切替テスト
- context menu 再生成テスト

## テスト計画

### unit test 追加対象

- `browser-extension/__tests__/unit/shared/settingsStorage.test.ts`
- `browser-extension/__tests__/unit/popup/renderPopup.test.ts`
- `browser-extension/__tests__/unit/content/renderOverlay.test.ts`
- background menu 生成まわりの test

### 重点確認項目

- settings 未保存時に `chrome.i18n.getUILanguage()` の `ja-JP` から `ja` が選ばれる
- settings 未保存時に `en-US` や未知 locale から `en` が選ばれる
- legacy settings を読み込んでも `uiLanguage` が安全に補完される
- popup 保存後に `uiLanguage` が永続化される
- overlay が同一 payload 内容でも `uiLanguage` に応じて文言を切り替える
- context menu が `uiLanguage` 変更で再生成される

### E2E 観点

- popup で `English` を保存後、overlay を開くと英語 UI で出る
- popup で `日本語` を保存後、overlay を開くと日本語 UI で出る
- 言語切替後の context menu title が次回右クリック時に反映される

## リスクと対策

### リスク 1: 文言の取りこぼし

文字列直書きが複数 runtime に散っているため、一部だけ英語化・日本語化されず混在する可能性がある。

対策:

- 初回実装時に固定文言の grep を使って棚卸しする
- `shared/i18n/messages.ts` 以外の固定 UI 文言を段階的に減らす

### リスク 2: 低レベル例外の翻訳しにくさ

`throw new Error()` が service 層に散っているため、locale を知らない層で英日文言を確定してしまう危険がある。

対策:

- まずは UI に露出する既知エラーを優先移行する
- 想定外エラーは detail を包む wrapper message に統一する

### リスク 3: context menu の再生成漏れ

popup で保存しても background 側の menu が更新されないと表示言語が古いまま残る。

対策:

- `chrome.storage.onChanged` を background で監視する
- install / startup / settings change の 3 経路を同じ `ensurePhase0ContextMenu()` に集約する

## 受け入れ条件

- popup に `表示言語 / UI Language` の設定項目が存在する
- 初回既定値が `chrome.i18n.getUILanguage()` の `ja` 判定に従う
- `ja` 以外と不明値は英語へフォールバックする
- popup の文言が選択言語で表示される
- overlay の文言が選択言語で表示される
- context menu が選択言語で表示される
- ユーザー向け runtime error が選択言語で表示される
- 既存 settings を持つユーザーでも破壊的変更なく動作する

## 実装時の非目標の再確認

今回は runtime UI の切り替えに集中し、manifest 静的文言の `_locales/` 対応までは行わない。
これにより、popup 手動切替と manifest locale の二重管理を避け、実装範囲を明確に保つ。

## まとめ

本件は単なる popup の文言追加ではなく、shared settings、locale 解決、辞書管理、background から overlay への言語伝播、context menu 再生成の 5 点を揃えて初めて成立する。

最小構成としては次の流れで進めるのが妥当である。

1. settings に `uiLanguage` を追加する
2. `chrome.i18n.getUILanguage()` を用いた default locale 解決を shared に置く
3. shared 辞書と translator を作る
4. popup、overlay、context menu、runtime error を順に辞書参照へ移行する
5. `storage.onChanged` で context menu 再生成を保証する

この方針なら、既存の runtime-first 分割を崩さずに、日本語 / English 手動切り替えを一貫した形で導入できる。
