import type { UiLanguage } from '../config/phase0';

export const UI_MESSAGES = {
  en: {
    popupEyebrow: 'Gem Read',
    popupTitle: 'Local Bridge',
    popupSubtitle:
      'Popup settings for Local API connectivity, default model, article cache behavior, and Markdown export metadata.',
    popupChecking: 'Checking',
    popupCheckingLine: 'Local API connectivity is being checked.',
    popupApiBaseUrlLabel: 'Local API Base URL',
    popupApiBaseUrlHint:
      'Allowed values are localhost only, for example http://127.0.0.1:8000.',
    popupDefaultModelLabel: 'Default Model',
    popupDefaultModelHint:
      'Fetched models are suggested automatically, but a manual model ID is also allowed.',
    popupUiLanguageLabel: 'UI Language',
    popupUiLanguageJa: '日本語',
    popupUiLanguageEn: 'English',
    popupSharedSystemPromptLabel: 'Shared System Prompt',
    popupSharedSystemPromptHint:
      'Applied to translation, translation with explanation, and custom prompt requests. The saved text is kept as entered.',
    popupArticleCacheSummary: 'Article Cache',
    popupArticleCacheSummaryNote:
      'Default: automatic full-article cache creation is on',
    popupArticleCacheAutoCreateTitle: 'Automatically create full article cache',
    popupArticleCacheAutoCreateHint:
      'When off, Gem Read still reuses an existing article cache for the tab, but it will not create a new one automatically.',
    popupArticleCacheHint:
      'This applies to article-sized pages only. It does not disable cache reuse or manual deletion.',
    popupMarkdownExportSummary: 'Markdown Export',
    popupMarkdownExportSummaryNote: 'Default: explanation + selected text',
    popupIncludeExplanationTitle: 'Include explanation',
    popupIncludeExplanationHint:
      "Enabled by default. Saves Gemini's explanation section when present.",
    popupIncludeSelectionsTitle: 'Include selected source text',
    popupIncludeSelectionsHint:
      'Enabled by default. Lists the current batch selections before the answer body.',
    popupIncludeRawResponseTitle: 'Include raw response',
    popupIncludeRawResponseHint:
      'Disabled by default. Adds the unprocessed Gemini response payload.',
    popupIncludeArticleMetadataTitle: 'Include article metadata',
    popupIncludeArticleMetadataHint:
      'Disabled by default. Adds source page metadata such as title, byline, and site name.',
    popupIncludeUsageMetricsTitle: 'Include usage metrics',
    popupIncludeUsageMetricsHint:
      'Disabled by default. Adds token usage when the current result includes it.',
    popupIncludeYamlFrontmatterTitle: 'Include YAML frontmatter',
    popupIncludeYamlFrontmatterHint:
      'Disabled by default. Adds machine-readable metadata at the top of the file.',
    popupMarkdownExportHint:
      'Default export saves answer body, explanation, and selected text. Filename rule is page title plus timestamp.',
    popupRefresh: 'Refresh',
    popupSave: 'Save',
    popupOpenOverlay: 'Open Overlay On Active Tab',
    popupOpenOverlayHint:
      'Browser commands are the primary flow in Phase 3. This button uses the same active-tab overlay reopen path as the keyboard shortcut.',
    popupDebugCacheSummary: 'Debug: Cache Management',
    popupDebugLoadCaches: 'Load browser-extension caches',
    popupStatusReachable: 'Reachable',
    popupStatusMockMode: 'Mock Mode',
    popupStatusUnreachable: 'Unreachable',
    popupStatusLineReachable:
      'Local API is reachable and returned a live model catalog.',
    popupStatusLineMockMode:
      'Local API is up, but popup is using fallback or degraded model information.',
    popupStatusLineUnreachable:
      'Local API could not be reached from the popup.',
    popupSourceCachedModels: 'Cached models available: {count}',
    popupSourceNoModels: 'No model suggestions are available yet.',
    popupSourceModels: 'Model source: {source} | suggestions: {count}',
    popupMessageSaved: 'Settings saved.',
    popupMessageStatusRefreshed: 'Connection status refreshed.',
    popupMessageOverlayOpened:
      'Overlay shortcut opened on the active tab.',
    popupMessageDeletedCache: 'Deleted cache: {cacheName}',
    popupMessageNoCaches: 'No browser-extension caches found.',
    popupErrorUseLocalhost:
      'Use a localhost URL such as http://127.0.0.1:8000.',
    popupErrorRefreshNeedsLocalhost: 'Refresh needs a valid localhost URL.',
    popupErrorSaveSettings: 'Failed to save popup settings',
    popupErrorRefreshStatus: 'Failed to refresh popup status',
    popupErrorOpenOverlay: 'Failed to open overlay shortcut',
    popupErrorOpenOverlayResponse: 'Failed to open the Gem Read overlay',
    popupErrorLoadCacheList: 'Failed to load cache list',
    popupErrorDeleteCache: 'Failed to delete cache',
    popupErrorUnreachable: 'Local API is unreachable',
    popupDetailNotCheckedYet: 'Local API connectivity has not been checked yet.',
    popupDetailUsingCachedModels: 'Using cached models from popup storage.',
    overlayTitle: 'Gem Read Overlay',
    overlaySubtitle:
      'Selection actions stay on-page while the background keeps the API flow.',
    overlayStatusRunning: 'Running',
    overlayStatusError: 'Error',
    overlayStatusMockResult: 'Mock Result',
    overlayStatusLiveResult: 'Live Result',
    overlayTablistLabel: 'Overlay sections',
    overlayMinimizeAria: 'Minimize overlay',
    overlayCloseAria: 'Close overlay',
    overlayTabWorkspace: 'Workspace',
    overlayTabGemini: 'Gemini',
    overlaySectionRuntime: 'Runtime',
    overlaySectionBatch: 'Batch',
    overlayBatchCounter: '{count}/{max} items',
    overlayActionAddSelection: 'Add Current Selection',
    overlayActionAddRectangle: 'Add Rectangle',
    overlaySectionActions: 'Actions',
    overlayModelPlaceholder: 'Optional model override',
    overlayActionTranslate: 'Translate',
    overlayActionTranslateExplain: 'Translate + Explain',
    overlayCustomPromptPlaceholder: 'Custom prompt for the current selection',
    overlayActionRunCustom: 'Run Custom Prompt',
    overlayActionHintReady:
      'Reuse the cached batch with a different action or model. Press Alt+R to rerun the last action or Ctrl+Enter in the custom prompt box to submit.',
    overlayActionHintUnavailable:
      'Select text and run Gem Read once before action buttons become available. Press Alt+Backspace to clear all selections.',
    overlaySectionSelection: 'Selection',
    overlaySectionCropPreview: 'Crop Preview',
    overlayAltCropPreview: 'Selection crop preview',
    overlayEmptySelectionText: 'No selection text captured.',
    overlaySectionExport: 'Export',
    overlayActionDownloadMarkdown: 'Download Markdown',
    overlaySectionExplanation: 'Explanation',
    overlaySectionDetails: 'Details',
    overlayRawResponseSummary: 'Raw Response',
    overlaySectionError: 'Error',
    overlayResultTranslation: 'Translation',
    overlayResultCustomPrompt: 'Custom Prompt Result',
    overlayGeminiLoading:
      'Gemini response is on the way. This tab will fill in when the current run finishes.',
    overlayGeminiError: 'No Gemini response is available for the latest run.',
    overlayGeminiIdle:
      'Run Translate or Translate + Explain to show Gemini output here.',
    overlayMetaLoading: 'Background workflow is running.',
    overlayBannerRemoteMissing:
      'The server-side article cache was missing, so this request completed without cache.',
    overlayBannerNoSession:
      'No cached selection session is ready yet. Select text on the page and run Gem Read once before using overlay actions.',
    overlayBannerMockMode:
      'Mock mode is active. The Local API is reachable, but Gemini credentials are not configured.',
    overlayBannerDegraded: 'Runtime is degraded: {reason}.',
    overlaySectionArticleContext: 'Article Context',
    overlayArticleCharsSuffix: 'chars',
    overlayArticleUnavailableTitle: 'Article context unavailable',
    overlayArticleUnavailableSubtitle:
      'Article extraction is not available for this page.',
    overlayArticleHashPrefix: 'Hash',
    overlayArticleNoSummary: 'No extracted article context yet.',
    overlayArticleCacheNone: 'No article cache state yet.',
    overlayArticleUnavailable: 'Article context unavailable',
    overlayArticleExtractionUnavailable:
      'Article extraction is not available for this page.',
    overlayArticleNoContextYet: 'No extracted article context yet.',
    overlayActionDeleteCache: 'Delete Cache',
    overlayArticleTokensPill: 'Article {count} tokens',
    overlayRequestTokensPill: 'Request {count} tokens',
    overlayArticleTokenPill: 'Article {count} tokens',
    overlayRequestTokenPill: 'Request {count} tokens',
    overlayTtlPill: 'TTL {count}s',
    overlaySectionTokens: 'Tokens',
    overlayTokenCurrentRequest: 'Current Request',
    overlayTokenEstimatedValue: '{count} estimated',
    overlayTokenUnavailable: 'Unavailable',
    overlayTokenSelectedModel: 'the selected model',
    overlayTokenCountedAgainst: 'Counted against {model}.',
    overlayTokenRequestUnavailableNote:
      'Token counting is not available for the current request.',
    overlayTokenRequestUnavailable:
      'Token counting is not available for the current request.',
    overlayTokenArticleBaseline: 'Article Baseline',
    overlayTokenArticleValue: '{count} article tokens',
    overlayTokenLongArticleCandidate: 'Long article candidate',
    overlayTokenArticleNote:
      'Used to decide whether automatic cache creation is worth it for this tab.',
    overlayTokenArticleUnavailableNote:
      'Article extraction succeeded, but token counting is not available yet.',
    overlayTokenArticleCandidate: 'Long article candidate',
    overlayTokenArticleEligible:
      'Used to decide whether automatic cache creation is worth it for this tab.',
    overlayTokenArticleUnavailable:
      'Article extraction succeeded, but token counting is not available yet.',
    overlayTokenCacheImpact: 'Cache Impact',
    overlayTokenLastResponse: 'Last Response',
    overlayTokenTotalValue: '{count} total',
    overlayTokenUsageRecorded: 'Usage recorded',
    overlayTokenLastResponseValue: '{count} total',
    overlayTokenLastResponseRecorded: 'Usage recorded',
    overlayCacheStatusActive: 'Cache active{suffix}',
    overlayCacheStatusCandidateEligible: 'Cache eligible for auto-create',
    overlayCacheStatusCandidateBelowThreshold:
      'Cache below auto-create threshold',
    overlayCacheStatusCreating: 'Creating article cache',
    overlayCacheStatusRemoteMissing: 'Cache missing on server; local state reset',
    overlayCacheStatusInvalidatedReason: 'Cache invalidated: {reason}',
    overlayCacheStatusInvalidated: 'Cache invalidated',
    overlayCacheStatusUnsupported: 'Cache unsupported for this model',
    overlayCacheStatusDegraded: 'Cache state degraded',
    overlayCacheStatusIdle: 'Cache idle',
    overlayCacheImpactNone: 'No cache state',
    overlayCacheImpactCachedOnce: '{count} cached once',
    overlayCacheImpactActive: 'Cache active',
    overlayCacheImpactCandidate: 'Auto-create candidate',
    overlayCacheImpactCreating: 'Creating cache',
    overlayCacheImpactUnsupported: 'Model unsupported',
    overlayCacheImpactDegraded: 'Degraded',
    overlayCacheImpactFallback: 'Fallback without cache',
    overlayCacheImpactInvalidated: 'Invalidated',
    overlayCacheImpactIdle: 'Idle',
    overlayArticleCacheNoneNote:
      'No article cache state has been resolved for this tab yet.',
    overlayBatchHintReady: 'Up to {count} selections can be reused in this batch.',
    overlayBatchHintFull: 'The batch is full at {count} selections.',
    overlayBatchHintRectangleActive:
      'Finish the current rectangle capture before adding more selections.',
    overlayBatchHintStart:
      'Add the current text selection with Ctrl+Shift+9 or capture an image region with Ctrl+Shift+Y to start a reusable batch.',
    overlayBatchHintReuse:
      'Batch items keep their own cached crop preview so later analysis does not depend on live page selection.',
    overlaySessionEmpty: 'No items in the current batch.',
    overlaySessionImageOnly: '[Image region only]',
    overlaySessionKindRectangle: 'Rectangle',
    overlaySessionKindSelection: 'Selection',
    overlaySessionRemove: 'Remove',
    overlaySessionCachedCropReady: 'Cached crop ready',
    overlaySessionNoCachedCrop: 'No cached crop',
    overlaySessionIncludeImage: 'Include image',
    overlayErrorAddRectangle: 'Failed to add the rectangle selection.',
    overlayRectangleCancelled: 'Rectangle selection was cancelled.',
    overlayRectangleActive:
      'Rectangle selection is active. Drag on the page to capture a region or press Esc to cancel.',
    overlayTokenCacheActive:
      'Article context is already cached for this tab and model.',
    overlayTokenCacheReuse:
      'The last response reused {count} cached tokens from the article context.',
    overlayTokenCacheReuseEstimate:
      'Selection reruns stay near {count} request tokens while Gemini reuses the cached article context.',
    overlayTokenCacheCreateCompare:
      'Creating cache stores about {articleTokens} article tokens once, then reruns stay near {requestTokens} selection tokens.',
    overlayTokenCacheCreateDefault:
      'This article is large enough to justify automatic cache creation.',
    overlayTokenCacheRetryWithout:
      'Gem Read retried without article cache after Gemini could not find the server-side cache for this tab.',
    overlayTokenCachePending:
      'Cache state is available, but no token comparison is ready yet.',
    overlayUsageUnavailable: 'No response usage metadata is available.',
    overlayUsageMissingStageCounts:
      'The response completed, but Gemini did not return per-stage token counts.',
    overlayErrorCustomPromptEmpty: 'Custom prompt cannot be empty.',
    overlayErrorActionFailed: 'Overlay action failed.',
    overlayErrorBatchLimit:
      'You can keep up to {count} selections in one batch.',
    overlayErrorSelectionRequired:
      'A page selection is required before adding it to the batch.',
    overlayErrorAddSelection: 'Failed to add the current selection.',
    overlayErrorRemoveSelection: 'Failed to remove the selection item.',
    overlayErrorToggleImage:
      'Failed to update image inclusion for the selection item.',
    overlayErrorDeleteCache: 'Failed to delete the active article cache.',
    overlayErrorExport: 'Failed to export the current Gemini result.',
    menuTranslate: 'Translate with Gem Read',
    menuRectangle: 'Start free-rectangle selection with Gem Read',
    bgNoticeTabClosed: 'Article cache was cleared because the tab was closed.',
    bgNoticeOverlayClosed:
      'Article cache was cleared because the overlay session ended.',
    bgNoticeManualCacheDelete:
      'Article cache was deleted manually for this tab.',
    bgErrorNoActiveTab: 'No active browser tab is available for Gem Read.',
    bgErrorOpenOverlay: 'Failed to open the Gem Read overlay.',
    bgErrorRectangleStart:
      'Rectangle selection could not be started on this page.',
    bgErrorOverlayAction: 'Overlay action failed.',
    bgErrorAppendSelection: 'Failed to append selection item.',
    bgErrorRemoveSelection: 'Failed to remove selection item.',
    bgErrorToggleSelectionImage:
      'Failed to update selection image inclusion.',
    bgErrorDeleteActiveCache: 'Failed to delete the active article cache.',
    bgErrorClearSelectionBatch: 'Failed to clear the selection batch.',
    bgErrorMarkdownExport: 'Markdown export failed.',
    bgErrorCacheOverlaySession: 'Failed to cache overlay session.',
    bgErrorCacheBatchOverlaySession:
      'Failed to cache batch overlay session.',
    bgErrorSelectionSessionMissing:
      'Analysis session could not be found. Add a new selection and try again.',
    bgErrorSelectionUnavailable:
      'Selection text could not be captured.',
    bgErrorLiveSelectionRequired:
      'A live text selection is required. Select text on the page and try again.',
    bgErrorActiveTabWindow: 'Active tab window could not be resolved.',
    bgErrorItemNotFound: 'Selection item could not be found.',
    bgErrorImagePreviewRequired:
      'A cached crop preview is required before enabling image inclusion.',
    bgErrorInvalidCrop: 'Crop coordinates for the selection are invalid.',
    bgErrorOffscreenContext:
      'The 2D context for OffscreenCanvas could not be created.',
    bgNoticeRemoteMissing:
      'The server-side article cache could not be found, so this request completed without cache.',
  },
  ja: {
    popupEyebrow: 'Gem Read',
    popupTitle: 'Local Bridge',
    popupSubtitle:
      'Local API 接続、既定モデル、記事キャッシュ、Markdown 出力設定を管理します。',
    popupChecking: '確認中',
    popupCheckingLine: 'Local API の接続を確認しています。',
    popupApiBaseUrlLabel: 'Local API Base URL',
    popupApiBaseUrlHint:
      'localhost のみ許可されます。例: http://127.0.0.1:8000',
    popupDefaultModelLabel: '既定モデル',
    popupDefaultModelHint:
      '取得したモデル候補を自動表示しますが、手入力のモデル ID も使えます。',
    popupUiLanguageLabel: '表示言語',
    popupUiLanguageJa: '日本語',
    popupUiLanguageEn: 'English',
    popupSharedSystemPromptLabel: '共通システムプロンプト',
    popupSharedSystemPromptHint:
      '翻訳、翻訳+解説、カスタムプロンプトに適用されます。保存時は入力内容をそのまま保持します。',
    popupArticleCacheSummary: '記事キャッシュ',
    popupArticleCacheSummaryNote:
      '既定: 記事全体キャッシュの自動作成は有効',
    popupArticleCacheAutoCreateTitle: '記事全体キャッシュを自動作成する',
    popupArticleCacheAutoCreateHint:
      '無効でも既存のキャッシュは再利用されますが、新規作成は自動では行いません。',
    popupArticleCacheHint:
      '記事サイズのページにのみ適用されます。キャッシュ再利用や手動削除は無効化しません。',
    popupMarkdownExportSummary: 'Markdown 出力',
    popupMarkdownExportSummaryNote: '既定: 解説 + 選択テキスト',
    popupIncludeExplanationTitle: '解説を含める',
    popupIncludeExplanationHint:
      '既定で有効です。Gemini の解説セクションがあれば保存します。',
    popupIncludeSelectionsTitle: '選択元テキストを含める',
    popupIncludeSelectionsHint:
      '既定で有効です。回答本文の前に現在の batch 選択を列挙します。',
    popupIncludeRawResponseTitle: '生レスポンスを含める',
    popupIncludeRawResponseHint:
      '既定で無効です。未加工の Gemini レスポンス payload を追加します。',
    popupIncludeArticleMetadataTitle: '記事メタデータを含める',
    popupIncludeArticleMetadataHint:
      '既定で無効です。タイトル、著者、サイト名などのソース情報を追加します。',
    popupIncludeUsageMetricsTitle: '使用量メトリクスを含める',
    popupIncludeUsageMetricsHint:
      '既定で無効です。結果に含まれる token 使用量を追加します。',
    popupIncludeYamlFrontmatterTitle: 'YAML frontmatter を含める',
    popupIncludeYamlFrontmatterHint:
      '既定で無効です。ファイル先頭に機械可読なメタデータを追加します。',
    popupMarkdownExportHint:
      '既定の出力には回答本文、解説、選択テキストが含まれます。ファイル名はページタイトルとタイムスタンプです。',
    popupRefresh: '再読込',
    popupSave: '保存',
    popupOpenOverlay: 'アクティブタブで Overlay を開く',
    popupOpenOverlayHint:
      'Phase 3 の主導線はブラウザコマンドです。このボタンもキーボードショートカットと同じ active-tab の reopen 経路を使います。',
    popupDebugCacheSummary: 'Debug: キャッシュ管理',
    popupDebugLoadCaches: 'browser-extension キャッシュを読み込む',
    popupStatusReachable: '接続可',
    popupStatusMockMode: 'Mock Mode',
    popupStatusUnreachable: '未接続',
    popupStatusLineReachable:
      'Local API に接続でき、live model catalog が返されました。',
    popupStatusLineMockMode:
      'Local API には接続できていますが、popup は fallback または degraded なモデル情報を使っています。',
    popupStatusLineUnreachable:
      'popup から Local API に接続できませんでした。',
    popupSourceCachedModels: '保存済みモデル候補: {count}',
    popupSourceNoModels: 'まだモデル候補はありません。',
    popupSourceModels: 'モデル取得元: {source} | 候補数: {count}',
    popupMessageSaved: '設定を保存しました。',
    popupMessageStatusRefreshed: '接続状態を更新しました。',
    popupMessageOverlayOpened:
      'アクティブタブで Overlay ショートカットを開きました。',
    popupMessageDeletedCache: 'キャッシュを削除しました: {cacheName}',
    popupMessageNoCaches: 'browser-extension キャッシュは見つかりませんでした。',
    popupErrorUseLocalhost:
      'http://127.0.0.1:8000 のような localhost URL を指定してください。',
    popupErrorRefreshNeedsLocalhost:
      '再読込には有効な localhost URL が必要です。',
    popupErrorSaveSettings: 'popup 設定の保存に失敗しました',
    popupErrorRefreshStatus: 'popup 状態の更新に失敗しました',
    popupErrorOpenOverlay: 'Overlay の起動に失敗しました',
    popupErrorOpenOverlayResponse: 'Gem Read Overlay を開けませんでした',
    popupErrorLoadCacheList: 'キャッシュ一覧の読み込みに失敗しました',
    popupErrorDeleteCache: 'キャッシュの削除に失敗しました',
    popupErrorUnreachable: 'Local API に接続できません',
    popupDetailNotCheckedYet: 'Local API の接続はまだ確認されていません。',
    popupDetailUsingCachedModels:
      'popup storage に保存されたモデル候補を使用しています。',
    overlayTitle: 'Gem Read Overlay',
    overlaySubtitle:
      '選択操作はページ上のまま行い、API 処理は background が保持します。',
    overlayStatusRunning: '実行中',
    overlayStatusError: 'エラー',
    overlayStatusMockResult: 'Mock 結果',
    overlayStatusLiveResult: 'Live 結果',
    overlayTablistLabel: 'Overlay セクション',
    overlayMinimizeAria: 'overlay を最小化',
    overlayCloseAria: 'overlay を閉じる',
    overlayTabWorkspace: 'Workspace',
    overlayTabGemini: 'Gemini',
    overlaySectionRuntime: '実行状態',
    overlaySectionBatch: 'Batch',
    overlayBatchCounter: '{count}/{max} 件',
    overlayActionAddSelection: '現在の選択を追加',
    overlayActionAddRectangle: '矩形選択を追加',
    overlaySectionActions: 'アクション',
    overlayModelPlaceholder: '任意のモデル上書き',
    overlayActionTranslate: '翻訳',
    overlayActionTranslateExplain: '翻訳 + 解説',
    overlayCustomPromptPlaceholder: '現在の選択に対するカスタムプロンプト',
    overlayActionRunCustom: 'カスタムプロンプトを実行',
    overlayActionHintReady:
      '保存済み batch を別アクションや別モデルで再利用できます。Alt+R で直前アクションを再実行、カスタムプロンプト欄で Ctrl+Enter で送信します。',
    overlayActionHintUnavailable:
      'アクションボタンを使う前にページ上でテキストを選択して Gem Read を 1 回実行してください。Alt+Backspace ですべての選択を消去します。',
    overlaySectionSelection: '選択',
    overlaySectionCropPreview: '切り抜きプレビュー',
    overlayAltCropPreview: '選択範囲の切り抜きプレビュー',
    overlayEmptySelectionText: '選択テキストはまだ取得されていません。',
    overlaySectionExport: '出力',
    overlayActionDownloadMarkdown: 'Markdown を保存',
    overlaySectionExplanation: '解説',
    overlaySectionDetails: '詳細',
    overlayRawResponseSummary: '生レスポンス',
    overlaySectionError: 'エラー',
    overlayResultTranslation: '翻訳',
    overlayResultCustomPrompt: 'カスタムプロンプト結果',
    overlayGeminiLoading:
      'Gemini の応答を待っています。現在の実行が完了するとこのタブに結果が表示されます。',
    overlayGeminiError: '直近の実行には Gemini 応答がありません。',
    overlayGeminiIdle:
      '翻訳 または 翻訳 + 解説 を実行すると Gemini 出力がここに表示されます。',
    overlayMetaLoading: 'background workflow を実行中です。',
    overlayBannerRemoteMissing:
      'サーバー側の記事キャッシュが見つからなかったため、このリクエストはキャッシュなしで完了しました。',
    overlayBannerNoSession:
      'まだ再利用できる選択セッションがありません。Overlay のアクションを使う前にページ上でテキストを選択して Gem Read を 1 回実行してください。',
    overlayBannerMockMode:
      'Mock mode が有効です。Local API には接続できていますが、Gemini の認証情報は設定されていません。',
    overlayBannerDegraded: 'Runtime は degraded 状態です: {reason}',
    overlaySectionArticleContext: '記事コンテキスト',
    overlayArticleCharsSuffix: '文字',
    overlayArticleUnavailableTitle: '記事コンテキストは利用できません',
    overlayArticleUnavailableSubtitle:
      'このページでは記事抽出を利用できません。',
    overlayArticleHashPrefix: 'ハッシュ',
    overlayArticleNoSummary: 'まだ抽出済みの記事コンテキストはありません。',
    overlayArticleCacheNone: 'まだ記事キャッシュ状態はありません。',
    overlayArticleUnavailable: '記事コンテキストは利用できません',
    overlayArticleExtractionUnavailable:
      'このページでは記事抽出を利用できません。',
    overlayArticleNoContextYet: 'まだ抽出済みの記事コンテキストはありません。',
    overlayActionDeleteCache: 'キャッシュを削除',
    overlayArticleTokensPill: '記事 {count} tokens',
    overlayRequestTokensPill: 'リクエスト {count} tokens',
    overlayArticleTokenPill: '記事 {count} tokens',
    overlayRequestTokenPill: 'リクエスト {count} tokens',
    overlayTtlPill: 'TTL {count}s',
    overlaySectionTokens: 'Tokens',
    overlayTokenCurrentRequest: '現在のリクエスト',
    overlayTokenEstimatedValue: '推定 {count}',
    overlayTokenUnavailable: '利用不可',
    overlayTokenSelectedModel: '選択中のモデル',
    overlayTokenCountedAgainst: '{model} で計測しました。',
    overlayTokenRequestUnavailableNote:
      '現在のリクエストでは token 計測を利用できません。',
    overlayTokenRequestUnavailable:
      '現在のリクエストでは token 計測を利用できません。',
    overlayTokenArticleBaseline: '記事の基準値',
    overlayTokenArticleValue: '記事 {count} tokens',
    overlayTokenLongArticleCandidate: '長文記事候補',
    overlayTokenArticleNote:
      'このタブで記事キャッシュを自動作成する価値があるかを判断するために使います。',
    overlayTokenArticleUnavailableNote:
      '記事抽出には成功しましたが、まだ token 計測は利用できません。',
    overlayTokenArticleCandidate: '長文記事候補',
    overlayTokenArticleEligible:
      'このタブで記事キャッシュを自動作成する価値があるかを判断するために使います。',
    overlayTokenArticleUnavailable:
      '記事抽出には成功しましたが、まだ token 計測は利用できません。',
    overlayTokenCacheImpact: 'キャッシュ影響',
    overlayTokenLastResponse: '直近レスポンス',
    overlayTokenTotalValue: '合計 {count}',
    overlayTokenUsageRecorded: '使用量を記録済み',
    overlayTokenLastResponseValue: '合計 {count}',
    overlayTokenLastResponseRecorded: '使用量を記録済み',
    overlayCacheStatusActive: 'キャッシュ有効{suffix}',
    overlayCacheStatusCandidateEligible: '自動作成の対象です',
    overlayCacheStatusCandidateBelowThreshold:
      '自動作成の閾値未満です',
    overlayCacheStatusCreating: '記事キャッシュを作成中です',
    overlayCacheStatusRemoteMissing:
      'サーバー上のキャッシュが見つからず、ローカル状態をリセットしました',
    overlayCacheStatusInvalidatedReason: 'キャッシュは無効化されました: {reason}',
    overlayCacheStatusInvalidated: 'キャッシュは無効化されました',
    overlayCacheStatusUnsupported: 'このモデルではキャッシュを利用できません',
    overlayCacheStatusDegraded: 'キャッシュ状態は degraded です',
    overlayCacheStatusIdle: 'キャッシュは idle です',
    overlayCacheImpactNone: 'キャッシュ状態なし',
    overlayCacheImpactCachedOnce: '{count} を一度キャッシュ',
    overlayCacheImpactActive: 'キャッシュ有効',
    overlayCacheImpactCandidate: '自動作成候補',
    overlayCacheImpactCreating: 'キャッシュ作成中',
    overlayCacheImpactUnsupported: 'モデル非対応',
    overlayCacheImpactDegraded: 'degraded',
    overlayCacheImpactFallback: 'キャッシュなしでフォールバック',
    overlayCacheImpactInvalidated: '無効化済み',
    overlayCacheImpactIdle: 'idle',
    overlayArticleCacheNoneNote:
      'このタブでは、まだ記事キャッシュ状態は解決されていません。',
    overlayBatchHintReady: 'この batch では最大 {count} 件の選択を再利用できます。',
    overlayBatchHintFull: 'この batch は {count} 件で上限です。',
    overlayBatchHintRectangleActive:
      '現在の矩形キャプチャを完了してから追加してください。',
    overlayBatchHintStart:
      'Ctrl+Shift+9 で現在のテキスト選択を追加するか、Ctrl+Shift+Y で画像領域を追加して再利用可能な batch を開始できます。',
    overlayBatchHintReuse:
      'batch 項目ごとに切り抜きプレビューを保持するため、後続の解析は live なページ選択に依存しません。',
    overlaySessionEmpty: '現在の batch に項目はありません。',
    overlaySessionImageOnly: '[画像領域のみ]',
    overlaySessionKindRectangle: '矩形',
    overlaySessionKindSelection: '選択',
    overlaySessionRemove: '削除',
    overlaySessionCachedCropReady: '切り抜きキャッシュあり',
    overlaySessionNoCachedCrop: '切り抜きキャッシュなし',
    overlaySessionIncludeImage: '画像を含める',
    overlayErrorAddRectangle: '矩形選択の追加に失敗しました。',
    overlayRectangleCancelled: '矩形選択はキャンセルされました。',
    overlayRectangleActive:
      '矩形選択が有効です。ページ上でドラッグして領域を選択するか、Esc でキャンセルしてください。',
    overlayTokenCacheActive:
      'この記事コンテキストは、このタブとモデルですでにキャッシュされています。',
    overlayTokenCacheReuse:
      '直近の応答では記事コンテキストから {count} 件の cached token を再利用しました。',
    overlayTokenCacheReuseEstimate:
      'Gemini が記事キャッシュを再利用している間、選択の再実行はおおむね {count} request tokens に収まります。',
    overlayTokenCacheCreateCompare:
      'キャッシュ作成時に約 {articleTokens} article tokens を一度保存し、その後の再実行は約 {requestTokens} selection tokens に収まります。',
    overlayTokenCacheCreateDefault:
      'このページは記事キャッシュを自動作成する価値がある程度に十分長い記事です。',
    overlayTokenCacheRetryWithout:
      'Gemini がこのタブのサーバー側キャッシュを見つけられなかったため、Gem Read は記事キャッシュなしで再試行しました。',
    overlayTokenCachePending:
      'キャッシュ状態は取得できていますが、まだ token 比較は利用できません。',
    overlayUsageUnavailable: 'レスポンスの使用量メタデータはありません。',
    overlayUsageMissingStageCounts:
      'レスポンスは完了しましたが、Gemini は段階別の token 数を返しませんでした。',
    overlayErrorCustomPromptEmpty:
      'カスタムプロンプトは空にできません。',
    overlayErrorActionFailed: 'Overlay アクションに失敗しました。',
    overlayErrorBatchLimit:
      '1 つの batch に保持できる選択は最大 {count} 件です。',
    overlayErrorSelectionRequired:
      'batch に追加するにはページ上の選択が必要です。',
    overlayErrorAddSelection: '現在の選択の追加に失敗しました。',
    overlayErrorRemoveSelection: '選択項目の削除に失敗しました。',
    overlayErrorToggleImage:
      '選択項目の画像含有設定の更新に失敗しました。',
    overlayErrorDeleteCache:
      'アクティブな記事キャッシュの削除に失敗しました。',
    overlayErrorExport: '現在の Gemini 結果の出力に失敗しました。',
    menuTranslate: 'Gem Read で翻訳',
    menuRectangle: 'Gem Read で自由矩形選択を開始',
    bgNoticeTabClosed: 'タブが閉じられたため記事キャッシュをクリアしました。',
    bgNoticeOverlayClosed:
      'overlay セッションが終了したため記事キャッシュをクリアしました。',
    bgNoticeManualCacheDelete:
      'このタブの記事キャッシュを手動で削除しました。',
    bgErrorNoActiveTab:
      'Gem Read を実行できるアクティブなブラウザタブがありません。',
    bgErrorOpenOverlay: 'Gem Read Overlay を開けませんでした。',
    bgErrorRectangleStart:
      'このページでは矩形選択を開始できませんでした。',
    bgErrorOverlayAction: 'Overlay アクションに失敗しました。',
    bgErrorAppendSelection: '選択項目の追加に失敗しました。',
    bgErrorRemoveSelection: '選択項目の削除に失敗しました。',
    bgErrorToggleSelectionImage: '選択画像設定の更新に失敗しました。',
    bgErrorDeleteActiveCache:
      'アクティブな記事キャッシュの削除に失敗しました。',
    bgErrorClearSelectionBatch: '選択 batch のクリアに失敗しました。',
    bgErrorMarkdownExport: 'Markdown 出力に失敗しました。',
    bgErrorCacheOverlaySession:
      'Overlay セッションのキャッシュに失敗しました。',
    bgErrorCacheBatchOverlaySession:
      'batch overlay セッションのキャッシュに失敗しました。',
    bgErrorSelectionSessionMissing:
      '解析セッションが見つかりません。新しい選択を追加してから再実行してください。',
    bgErrorSelectionUnavailable: '選択テキストを取得できませんでした。',
    bgErrorLiveSelectionRequired:
      'ライブのテキスト選択が必要です。ページ上で文字列を選択してから再試行してください。',
    bgErrorActiveTabWindow: 'アクティブタブの window を解決できませんでした。',
    bgErrorItemNotFound: '選択項目が見つかりませんでした。',
    bgErrorImagePreviewRequired:
      '画像含有を有効化するには、キャッシュ済みの切り抜きプレビューが必要です。',
    bgErrorInvalidCrop: '選択範囲の crop 座標が無効です。',
    bgErrorOffscreenContext:
      'OffscreenCanvas の 2D コンテキストを取得できませんでした。',
    bgNoticeRemoteMissing:
      'サーバー側の記事キャッシュが見つからなかったため、このリクエストはキャッシュなしで完了しました。',
  },
} as const satisfies Record<UiLanguage, Record<string, string>>;

export type MessageKey = keyof typeof UI_MESSAGES.en;