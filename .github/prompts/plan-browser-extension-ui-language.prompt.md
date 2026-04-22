# 実装用プロンプト

ブラウザ拡張 browser-extension に対して、runtime UI の日本語 / English 切り替え機能を実装してください。対象は popup、overlay、context menu、ユーザーに見える runtime error message です。既存コードベースを尊重し、最小限で一貫した変更にまとめてください。

## 必須要件

- popup に UI 言語設定を追加する
- 選択肢は 日本語 と English の 2 つだけにする
- 保存値は uiLanguage: 'ja' | 'en' とする
- 設定未保存時だけ chrome.i18n.getUILanguage() を使って既定値を決める
- ja 系 locale は ja、それ以外と不明値は en にする
- popup、overlay、context menu、runtime error が保存設定の言語で表示されるようにする
- popup で保存後、その後に開く popup / overlay / context menu に反映されるようにする
- 既存 settings 形式との後方互換性を保つ。破壊的変更はしない

## 設計制約

- locale 判定ロジックは shared に集約する。runtime ごとに別実装しない
- dictionary も shared に集約し、popup / background / content で同じキー体系を使う
- mergeExtensionSettings() は locale 検出を行わず、純粋に正規化だけを担当させる
- loadExtensionSettings() が uiLanguage 未保存時の default locale 注入を行う唯一の場所になるようにする
- content 側では chrome.i18n.getUILanguage() を呼ばず、background から受け取る OverlayPayload.uiLanguage を使う
- background の UI 向け error は、可能な限り background 側で翻訳済み文字列にして content に渡す
- 今回は manifest.json や _locales/ は触らない

## 実装対象の中心ファイル

- browser-extension/src/shared/config/phase0.ts
- browser-extension/src/shared/storage/settingsStorage.ts
- browser-extension/src/shared/contracts/messages.ts
- browser-extension/src/popup/ui/renderPopup.ts
- browser-extension/src/content/overlay/renderOverlay.ts
- browser-extension/src/content/overlay/overlayActions.ts
- browser-extension/src/background/menus/phase0ContextMenu.ts
- browser-extension/src/background/entry.ts
- browser-extension/src/background/usecases/openOverlaySession.ts
- browser-extension/src/background/usecases/updateSelectionSession.ts
- browser-extension/src/background/usecases/runSelectionAnalysis.ts

## 新規追加候補

- browser-extension/src/shared/i18n

## 既存コードの確認結果

- uiLanguage はまだ未実装
- shared i18n ディレクトリはまだ存在しない
- popup 文言は browser-extension/src/popup/ui/renderPopup.ts に英語で直書きされている
- overlay 文言は browser-extension/src/content/overlay/renderOverlay.ts と browser-extension/src/content/overlay/overlayActions.ts に直書きされている
- context menu title は browser-extension/src/background/menus/phase0ContextMenu.ts に直書きされており、現状は日本語
- background usecase に UI 向けエラー文字列が散在している
- 既存 unit test は browser-extension/tests/unit/shared/settingsStorage.test.ts、browser-extension/tests/unit/popup/renderPopup.test.ts、browser-extension/tests/unit/content/renderOverlay.test.ts、browser-extension/tests/unit/background/openOverlaySession.test.ts、browser-extension/tests/unit/background/updateSelectionSession.test.ts、browser-extension/tests/unit/background/runSelectionAnalysis.test.ts がある

## 実装ステップ

- browser-extension/src/shared/config/phase0.ts に UiLanguage 型、ExtensionSettings.uiLanguage、ExtensionSettingsInput.uiLanguage、DEFAULT_EXTENSION_SETTINGS.uiLanguage = 'en' を追加する
- mergeExtensionSettings() で uiLanguage の null / undefined / 不正値を 'en' に正規化する
- shared/i18n/uiLanguage.ts を追加し、normalizeUiLanguage() と detectDefaultUiLanguage() を実装する。chrome.i18n.getUILanguage() の例外や空値は en にフォールバックする
- browser-extension/src/shared/storage/settingsStorage.ts の loadExtensionSettings() で、storage に uiLanguage が保存されていない場合のみ detectDefaultUiLanguage() で補完する
- shared/i18n/messages.ts と shared/i18n/translator.ts を追加し、ja/en の辞書と t(language, key, params?) を実装する。翻訳漏れは型で検知できるようにする
- popup をローカライズする。言語選択 UI を追加し、固定文言、status、hint、debug 表示、保存時メッセージを辞書参照に置き換える。保存直後は popup 自身も表示言語を反映させる
- browser-extension/src/shared/contracts/messages.ts の OverlayPayload に uiLanguage を追加し、background の payload builder から必ず設定値を渡す
- overlay をローカライズする。固定文言とクライアントエラー文言を辞書参照に切り替える
- context menu をローカライズする。ensurePhase0ContextMenu(uiLanguage) 形式に変え、install / startup / storage change の全経路から同じ関数を呼ぶ
- chrome.storage.onChanged を background に追加し、uiLanguage 変更時に context menu を再生成する
- background usecase / service の UI 向け error / notice を辞書化する。外部由来の raw detail はローカライズ済み wrapper message に埋め込む
- browser-extension/src/background/services/cropSelectionImage.ts、browser-extension/src/background/services/markdownExportService.ts、browser-extension/src/background/services/analysisSessionStore.ts も確認し、UI 向け文言があれば今回の辞書に含める
- 関連 unit test を更新・追加し、必要なら Playwright 側の期待値も更新する

## テスト要件

- browser-extension/tests/unit/shared/settingsStorage.test.ts に、ja-JP から ja、en-US / 未知 locale / 空文字 / 例外から en を選ぶケースを追加する
- legacy settings 読み込み時に uiLanguage が安全に補完されることを確認する
- browser-extension/tests/unit/popup/renderPopup.test.ts に、popup の初期表示と言語保存の検証を追加する
- browser-extension/tests/unit/content/renderOverlay.test.ts に、同一 payload でも uiLanguage に応じて文言が切り替わる検証を追加する
- background の test に、OverlayPayload へ uiLanguage が流れること、localized error が返ること、context menu 再生成が動くことを追加する

## 検証手順

- まず関連する Vitest を browser-extension 配下で実行する
- 実装後は変更箇所に近い unit test を優先して再実行する
- 最後に browser-extension 全体の test を必要最小限で確認する
- 実行できなかった検証があれば、理由を明記する

## 作業ルール

- 既存の runtime-first 分割を崩さない
- 不要なリファクタや unrelated fix は入れない
- 直書き UI 文言は可能な限り shared dictionary へ寄せる
- 変更後に、どのファイルで何を変えたかと、実行した検証を簡潔にまとめる
- 実装後、未ローカライズ文字列が残っていないか追加確認する