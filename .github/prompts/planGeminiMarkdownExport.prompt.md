## Plan: Markdown Export For Gemini Results

Browser extension に、Gemini の現在表示中の結果を Markdown ファイルとして即ダウンロードする機能を追加する。基本方針は、overlay の Gemini タブから background へ typed message を送り、background が download 権限で保存を行う構成にする。保存内容は 1 つの batch run を 1 ファイルにまとめ、複数の selection 入力を列挙したうえで、Gemini の回答本文と explanation を出力する。追加メタデータは popup の永続設定で個別に ON/OFF できるようにする。保存は既定のダウンロード先へ即保存し、ファイル名はページ title と timestamp を必ず含める。overlay を閉じた後の再ダウンロードは今回のスコープ外とし、表示中 payload をそのまま export source とする。

**Steps**

1. Phase 1: Export contract と設定モデルを追加する。Extension settings の export 設定は Further Considerations #2 の方針に従い、flat fields ではなく `MarkdownExportSettings` 型のサブオブジェクト（`markdownExport` キー）として `ExtensionSettings` に追加する。既定値は回答本文 + explanation + 選択元テキスト ON、raw response / 記事メタデータ / usage token / YAML frontmatter OFF にする。messages.ts の message contract には export request / response 型を追加し、`BackgroundRuntimeMessage` union にも必ず追加する（追加しないと background の `onMessage` が型エラーになる）。export request の payload は Markdown 組み立てに必要な項目（`translatedText`, `explanation`, `rawResponse`, `selectedText`, `sessionItems`, `articleContext`, `usage`, `action`, `modelName`, `pageTitle`, `pageUrl`）だけを持つ専用型にする。`OverlayPayload` 全体は乗せない（`previewImageUrl` など画像データが混入するため）。これは後続の popup UI、overlay action、background download 実装の前提になる。
2. Phase 1 details: 既存の settings merge 互換性を維持する。`phase0.ts` の `mergeExtensionSettings()` は settings 全保存の正規化ブリッジであり、ここに `markdownExport` サブオブジェクトの safe default 補完を追加しないと、popup から Settings を保存するたびに export 設定が黙って消える。古い保存値でも `markdownExport` が存在しない場合は全フィールドを既定値で補完するよう `mergeExtensionSettings` を拡張し、phase0.ts と settingsStorage.ts だけで正規化を完結させる。blocks 3, 4, 5
3. Phase 2: Popup に export 設定 UI を追加する。既存の settings form に markdown export セクションを追加し、booleans を checkbox 群として常設する。項目は includeExplanation, includeSelections, includeRawResponse, includeArticleMetadata, includeUsageMetrics, includeYamlFrontmatter を持たせる。`PopupRefs` インターフェースに各 checkbox の ref フィールドを追加し、`getPopupRefs()` の null チェックブロックにも追加する（`getPopupRefs` はいずれか 1 つでも null なら `null` を返し popup が無言で壊れる）。form submit ハンドラは現在 `{ apiBaseUrl, defaultModel, lastKnownModels }` の 3 フィールドのみを `saveExtensionSettings` に渡しているため、submit ハンドラで export checkbox 群を読み取り `markdownExport` サブオブジェクトを組み立てて一緒に渡すよう変更する。保存時は既存 settings と同じフローで chrome.storage.local へ永続化する。UI は popup の責務に収め、overlay 側には設定編集 UI を持ち込まない。depends on 1-2
4. Phase 2 details: popup 表示文言で、保存対象の初期値と frontmatter が通常 OFF であることを明示する。必要なら filename rule の説明文も popup に短く追加する。parallel with 5 if settings shape is fixed
5. Phase 3: Background export pipeline を追加する。background runtime に export message handler を追加する。export 設定（`markdownExport` サブオブジェクト）は content 側の message payload に含めず、handler が `loadExtensionSettings()` を呼んで background 側で直接取得する（他の既存 handler が `loadExtensionSettings` を呼ぶのと同じパターン）。handler は受信した batch selections と Gemini 結果をまとめて `background/services/markdownExportService.ts` に渡し Markdown 文字列を組み立てさせ、`background/gateways/downloadGateway.ts` に渡して `chrome.downloads.download` を呼ぶ。download 処理は gateway に隔離し entry に直接書かない。manifest に downloads 権限を追加する。保存ファイル名は sanitized page title + timestamp（`YYYYMMDD-HHmmss` 形式）+ `.md` とし、title sanitize は `[/\\?%*:|"<>]` を `-` に置換し末尾の空白・ハイフンをトリム後 80 文字で切り捨てる。ブラウザ既定の重複回避に任せる。depends on 1-2
6. Phase 3 details: serializer は現在の run を 1 ファイルにまとめる。構成は title / exportedAt / model / action / source page などの header、複数 selection の列挙、Gemini 回答本文、任意 explanation、任意 raw response、任意 article metadata、任意 usage metrics の順にする。YAML frontmatter が ON のときだけ先頭に machine-readable metadata を付ける。mock result も live result と同様に保存対象にする。download 失敗時は typed error を返し、overlay の既存 error section へ表示させる。depends on 5
7. Phase 4: Overlay UI と content action を追加する。Gemini タブの結果欄の近くに Markdown download ボタンを追加し、success 状態で結果が存在するときだけ有効化する。このボタンは結果が存在しないときは HTML テンプレートに含まれないか hidden になるため、`renderOverlay` 内での DOM 取得は `deleteArticleCacheButton` と同じ optional chaining パターン（`root.querySelector<HTMLButtonElement>('...')?.addEventListener(...)`）を使う。必須要素の null チェックブロックには追加しない（追加すると結果がない状態で null チェックが `return` してしまい overlay 全体がレンダリングされなくなる）。ボタン押下で content が必要フィールドを payload として background に送る。再保存要件は不要なので、session store に結果本文を永続化する変更は行わない。depends on 1, 5
8. Phase 4 details: batch export は現在の sessionItems を列挙し、Gemini の結果は 1 つだけ出力する現在仕様に合わせる。ボタン表示は Gemini タブの translatedText または explanation の存在に紐づけ、loading / error / empty state では無効または非表示にする。失敗時は overlay の error section に既存パターンでエラーメッセージを出す。depends on 7
9. Phase 5: テストを追加する。settings 正規化と popup 保存の unit test、overlay の button rendering と message dispatch の unit test、background の message handler / serializer / download gateway の unit test を追加する。既存 test suite の責務分離に合わせ、popup/renderPopup.test.ts、content/renderOverlay.test.ts、background/registerBackgroundRuntime.test.ts か新規 background export suite を主戦場にする。`__tests__/mocks/chrome.ts` に `chrome.downloads` の mock（`chrome.downloads.download` を `vi.fn()` で実装）を追加する。これを忘れると background handler テストが `TypeError: chrome.downloads is undefined` で落ちる。depends on 1-8
10. Phase 5 details: 重要ケースは、既定値の merge、旧 settings からの upgrade、explanation ON/OFF、raw response ON/OFF、selection list ON/OFF、frontmatter ON/OFF、page title sanitize、mock result export、download API failure mapping をカバーする。Playwright は今回のユーザー要件上は必須ではないが、実行余力があれば download start と filename だけを確認する smoke を追加できる。parallel with late-stage manual verification
11. Phase 6: 検証と必要最小限のドキュメント更新を行う。browser-extension の設定画面に export 設定が増えるため、popup 操作と export 動線が分かるように短い説明を追加する。README か user docs への明示が必要なら、markdown export が overlay の Gemini タブから実行され、追加メタデータは popup で切り替える点だけを追記する。depends on 3-9

**Relevant files**

- d:\programming\py_apps\gem-read\browser-extension\manifest.json — downloads 権限の追加
- d:\programming\py_apps\gem-read\browser-extension\src\shared\config\phase0.ts — ExtensionSettings に export 設定型と既定値を追加
- d:\programming\py_apps\gem-read\browser-extension\src\shared\storage\settingsStorage.ts — 新 settings 項目の merge / load / save 互換性を維持
- d:\programming\py_apps\gem-read\browser-extension\src\shared\contracts\messages.ts — export request / response message を追加
- d:\programming\py_apps\gem-read\browser-extension\src\popup\ui\renderPopup.ts — export 設定 UI と保存導線を追加
- d:\programming\py_apps\gem-read\browser-extension\src\background\entry.ts — export message routing を追加するが、entry は thin のまま維持
- d:\programming\py_apps\gem-read\browser-extension\src\background\services\analysisSessionStore.ts — 今回は結果本文を永続化しない前提のため参照のみ。将来の再保存要件が出たら拡張候補
- d:\programming\py_apps\gem-read\browser-extension\src\background\services\markdownExportService.ts — 新規。Markdown 文字列組み立て責務
- d:\programming\py_apps\gem-read\browser-extension\src\background\gateways\downloadGateway.ts — 新規。chrome.downloads 呼び出しの隔離
- d:\programming\py_apps\gem-read\browser-extension\src\content\overlay\renderOverlay.ts — Gemini タブの download button 配置と enabled/disabled 制御
- d:\programming\py_apps\gem-read\browser-extension\src\content\overlay\overlayActions.ts — export action を background message に変換
- d:\programming\py_apps\gem-read\browser-extension\src\content\overlay\overlayStyles.ts — download ボタンの CSS を既存ボタンスタイルに合わせて追加
- d:\programming\py_apps\gem-read\browser-extension\_\_tests\_\_\mocks\chrome.ts — chrome.downloads mock を追加
- d:\programming\py_apps\gem-read\browser-extension\_\_tests\_\_\unit\popup\renderPopup.test.ts — popup 設定 UI と保存テストの拡張
- d:\programming\py_apps\gem-read\browser-extension\_\_tests\_\_\unit\content\renderOverlay.test.ts — button 表示、message dispatch、error UX のテスト
- d:\programming\py_apps\gem-read\browser-extension\_\_tests\_\_\unit\background\registerBackgroundRuntime.test.ts — runtime message handler の回帰テスト候補
- d:\programming\py_apps\gem-read\browser-extension\_\_tests\_\_\unit\background\markdownExport.test.ts — 新規。serializer と download handler の本体テスト

**Verification**

1. browser-extension 配下で npm run test を実行し、popup / content / background の export 追加テストが通ることを確認する。
2. browser-extension 配下で npm run build を実行し、manifest 権限追加と新規 service/gateway を含めてビルドが通ることを確認する。
3. 手動確認として、success result が表示された状態で download ボタンを押し、既定のダウンロード先に .md が保存されること、ファイル名に sanitized title と timestamp が含まれることを確認する。
4. 手動確認として、default 設定のときに file に回答本文 / explanation / selection list が入り、raw response / article metadata / usage metrics / frontmatter が入らないことを確認する。
5. popup で各 toggle を切り替え、再度 export して出力内容が追従することを確認する。
6. mock-mode result でも export できること、download API 失敗時に overlay error section にメッセージが出ることを確認する。

**Decisions**

- 保存は background + downloads 権限で実装する。
- 保存先は既定のダウンロード先で、Save As は今回のスコープ外とする。
- 保存単位は current batch run を 1 ファイルにまとめる。複数 selection 入力 + 単一 Gemini 結果という現在仕様をそのまま反映する。
- デフォルト出力は回答本文、explanation、選択元テキスト ON。raw response、記事メタデータ、usage token、YAML frontmatter は OFF。
- 設定 UI は popup に常設し、overlay 側は実行専用に保つ。
- overlay を閉じた後の再ダウンロードは非スコープであり、そのため結果本文を analysisSessionStore に保存する変更は行わない。
- mock result も保存対象に含める。
- 失敗時通知は overlay の既存 error section を再利用する。

**Further Considerations**

1. 実装時に serializer の配置先は background/services を推奨する。usecase は orchestration、service は文字列整形責務として分けるとテストしやすい。
2. export 設定は `MarkdownExportSettings` 型の `markdownExport` サブオブジェクトとして実装済み（Step 1 で確定）。将来 Save As や export preset を追加する際もこのサブオブジェクトを拡張するだけで済む。
3. 将来「overlay を閉じた後も再保存したい」要件が出たら、SelectionAnalysisSession に lastResult snapshot を追加し、renderOverlay 依存を外すのが自然な拡張線になる。
