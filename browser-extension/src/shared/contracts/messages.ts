export type OverlayStatus = 'loading' | 'success' | 'error';
export type AnalysisAction =
  | 'translation'
  | 'translation_with_explanation'
  | 'custom_prompt';
export type PopupConnectionStatus = 'reachable' | 'mock-mode' | 'unreachable';
export type RuntimeAvailability = 'live' | 'mock' | 'degraded';
export type DegradedReason =
  | 'config-fallback'
  | 'mock-response'
  | 'offline'
  | 'unknown';
export type ModelCatalogSource =
  | 'live'
  | 'config_fallback'
  | 'storage_fallback';

/**
 * SelectionRect は content script で観測した viewport 座標系の矩形を表す。
 * crop 実行時は background 側で screenshot bitmap 座標へ変換する前提なので、生の viewport 値を保持する。
 */
export interface SelectionRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * 選択文字列だけでなく、後続の crop と API metadata に必要な実行文脈をまとめて運ぶ payload。
 */
export interface SelectionCapturePayload {
  text: string;
  rect: SelectionRect;
  viewportWidth: number;
  viewportHeight: number;
  devicePixelRatio: number;
  url: string;
  pageTitle: string;
}

export interface SelectionCaptureResponse {
  ok: boolean;
  payload?: SelectionCapturePayload;
  error?: string;
}

export type ArticleContextSource = 'readability' | 'dom-fallback';

export interface ArticleContext {
  title: string;
  url: string;
  bodyText: string;
  bodyHash: string;
  source: ArticleContextSource;
  textLength: number;
  excerpt?: string;
  byline?: string;
  siteName?: string;
}

export interface ArticleContextResponse {
  ok: boolean;
  payload?: ArticleContext;
  error?: string;
}

export type ArticleCacheLifecycleStatus =
  | 'idle'
  | 'candidate'
  | 'creating'
  | 'active'
  | 'invalidated'
  | 'degraded'
  | 'unsupported';

export type ArticleCacheInvalidationReason =
  | 'url-changed'
  | 'article-identity-changed'
  | 'model-changed'
  | 'ttl-expired'
  | 'body-changed'
  | 'manual-delete'
  | 'extraction-failed'
  | 'remote-missing';

export interface ArticleCacheState {
  status: ArticleCacheLifecycleStatus;
  autoCreateEligible?: boolean;
  cacheName?: string;
  displayName?: string;
  modelName?: string;
  articleUrl?: string;
  articleIdentity?: string;
  articleHash?: string;
  tokenEstimate?: number;
  tokenCount?: number;
  ttlSeconds?: number;
  expireTime?: string;
  invalidationReason?: ArticleCacheInvalidationReason;
  notice?: string;
  lastValidatedAt?: string;
}

export interface AnalyzeUsageMetrics {
  promptTokenCount?: number;
  cachedContentTokenCount?: number;
  candidatesTokenCount?: number;
  totalTokenCount?: number;
}

export interface AnalyzeApiResponse {
  ok: boolean;
  mode: AnalysisAction;
  translated_text: string;
  explanation: string | null;
  raw_response: string;
  used_mock: boolean;
  image_count: number;
  availability?: RuntimeAvailability;
  degraded_reason?: DegradedReason | null;
  selection_metadata?: Record<string, unknown> | null;
  usage?: AnalyzeUsageMetrics | null;
}

export interface CacheStatusApiResponse {
  ok: boolean;
  isActive: boolean;
  ttlSeconds?: number;
  tokenCount?: number;
  cacheName?: string;
  displayName?: string;
  modelName?: string;
  expireTime?: string;
}

export interface CacheListItem {
  cacheName: string;
  displayName: string;
  modelName: string;
  expireTime?: string;
  tokenCount?: number;
}

export interface CacheListApiResponse {
  ok: boolean;
  items: CacheListItem[];
}

export interface TokenCountApiResponse {
  ok: boolean;
  tokenCount: number;
  modelName: string;
}

export interface AnalyzeRequestOptions {
  action: AnalysisAction;
  modelName?: string;
  customPrompt?: string;
}

export type SelectionSessionSource = 'text-selection' | 'free-rectangle';
export type RectangleSelectionTriggerSource =
  | 'overlay'
  | 'context-menu'
  | 'command';

export interface ModelOption {
  modelId: string;
  displayName: string;
}

export interface SelectionSessionItem {
  id: string;
  source: SelectionSessionSource;
  selection: SelectionCapturePayload;
  includeImage: boolean;
  previewImageUrl?: string;
  cropDurationMs?: number;
}

export interface ModelListApiResponse {
  ok: boolean;
  models: ModelOption[];
  source: ModelCatalogSource;
  availability: RuntimeAvailability;
  detail?: string;
  degradedReason?: DegradedReason;
}

export interface PopupStatusPayload {
  connectionStatus: PopupConnectionStatus;
  availability: RuntimeAvailability;
  apiBaseUrl: string;
  checkedAt?: string;
  detail?: string;
  modelSource?: ModelCatalogSource;
  degradedReason?: DegradedReason;
}

export interface OverlayPayload {
  status: OverlayStatus;
  action?: AnalysisAction;
  modelName?: string;
  modelOptions?: ModelOption[];
  sessionItems?: SelectionSessionItem[];
  maxSessionItems?: number;
  customPrompt?: string;
  sessionReady?: boolean;
  launcherOnly?: boolean;
  preserveDrafts?: boolean;
  selectedText?: string;
  articleContext?: ArticleContext;
  articleContextError?: string;
  articleCacheState?: ArticleCacheState;
  payloadTokenEstimate?: number;
  payloadTokenModelName?: string;
  payloadTokenError?: string;
  translatedText?: string;
  explanation?: string | null;
  previewImageUrl?: string;
  error?: string;
  usedMock?: boolean;
  availability?: RuntimeAvailability;
  degradedReason?: DegradedReason;
  imageCount?: number;
  timingMs?: number;
  rawResponse?: string;
  usage?: AnalyzeUsageMetrics;
}

/**
 * Phase 0 は単発 translation の message 群、Phase 1 は capture 済み session の再利用 message 群を表す。
 * contract を shared に集約しておくと、background/content/popup が同じ payload 形状を前提に進化できる。
 */
export interface CollectSelectionMessage {
  type: 'phase0.collectSelection';
  fallbackText?: string;
  liveOnly?: boolean;
}

export interface RenderOverlayMessage {
  type: 'phase0.renderOverlay';
  payload: OverlayPayload;
}

export interface CollectArticleContextMessage {
  type: 'phase4.collectArticleContext';
}

export interface SeedOverlaySessionPayload {
  previewImageUrl: string;
  cropDurationMs: number;
  modelOptions?: ModelOption[];
  fallbackText?: string;
}

export interface SeedOverlaySessionMessage {
  type: 'phase1.seedOverlaySession';
  payload: SeedOverlaySessionPayload;
}

export interface SeedOverlaySessionResponse {
  ok: boolean;
  error?: string;
}

export interface InvokeOverlayActionMessage {
  type: 'phase1.invokeOverlayAction';
  payload: RunOverlayActionPayload;
}

export interface RunOverlayActionPayload {
  action: AnalysisAction;
  modelName?: string;
  customPrompt?: string;
}

export interface RunOverlayActionMessage {
  type: 'phase1.runOverlayAction';
  payload: RunOverlayActionPayload;
}

export interface RunOverlayActionResponse {
  ok: boolean;
  error?: string;
}

export interface CacheOverlaySessionMessage {
  type: 'phase1.cacheOverlaySession';
  payload: {
    item: SelectionSessionItem;
    modelOptions: ModelOption[];
  };
}

export interface BeginRectangleSelectionMessage {
  type: 'phase2.beginRectangleSelection';
  payload: {
    triggerSource: RectangleSelectionTriggerSource;
  };
}

export interface BeginRectangleSelectionResponse {
  ok: boolean;
  error?: string;
}

export interface AppendSessionItemMessage {
  type: 'phase2.appendSessionItem';
  payload: {
    selection: SelectionCapturePayload;
    source: SelectionSessionSource;
  };
}

export interface SeedBatchOverlaySessionMessage {
  type: 'phase2.seedBatchOverlaySession';
  payload: {
    items: SelectionSessionItem[];
    modelOptions: ModelOption[];
    lastAction?: AnalysisAction;
    lastModelName?: string;
    lastCustomPrompt?: string;
  };
}

export interface SeedBatchOverlaySessionResponse {
  ok: boolean;
  error?: string;
}

export interface CacheBatchOverlaySessionMessage {
  type: 'phase2.cacheBatchOverlaySession';
  payload: {
    items: SelectionSessionItem[];
    modelOptions: ModelOption[];
    lastAction?: AnalysisAction;
    lastModelName?: string;
    lastCustomPrompt?: string;
  };
}

export interface AppendSessionItemResponse {
  ok: boolean;
  item?: SelectionSessionItem;
  error?: string;
}

export interface RemoveSessionItemMessage {
  type: 'phase2.removeSessionItem';
  payload: {
    itemId: string;
  };
}

export interface RemoveSessionItemResponse {
  ok: boolean;
  error?: string;
}

export interface ToggleSessionItemImageMessage {
  type: 'phase2.toggleSessionItemImage';
  payload: {
    itemId: string;
    includeImage: boolean;
  };
}

export interface ToggleSessionItemImageResponse {
  ok: boolean;
  error?: string;
}

export interface ClearOverlaySessionMessage {
  type: 'phase2.clearOverlaySession';
}

export interface ClearOverlaySessionResponse {
  ok: boolean;
}

export interface OpenOverlayMessage {
  type: 'phase3.openOverlay';
}

export interface OpenOverlayResponse {
  ok: boolean;
  error?: string;
}

export interface DeleteActiveArticleCacheMessage {
  type: 'phase4.deleteActiveArticleCache';
}

export interface DeleteActiveArticleCacheResponse {
  ok: boolean;
  error?: string;
}

export interface ClearSelectionBatchMessage {
  type: 'phase3.clearSelectionBatch';
}

export interface ClearSelectionBatchResponse {
  ok: boolean;
  error?: string;
}

export interface ExportMarkdownPayload {
  action: AnalysisAction;
  pageTitle: string;
  pageUrl: string;
  modelName?: string;
  translatedText?: string;
  explanation?: string | null;
  rawResponse?: string;
  selectedText?: string;
  sessionItems?: SelectionSessionItem[];
  articleContext?: ArticleContext;
  usage?: AnalyzeUsageMetrics;
}

export interface ExportMarkdownMessage {
  type: 'phase5.exportMarkdown';
  payload: ExportMarkdownPayload;
}

export interface ExportMarkdownResponse {
  ok: boolean;
  downloadId?: number;
  filename?: string;
  error?: string;
}

export type ContentScriptMessage =
  | CollectSelectionMessage
  | CollectArticleContextMessage
  | RenderOverlayMessage
  | SeedOverlaySessionMessage
  | InvokeOverlayActionMessage
  | SeedBatchOverlaySessionMessage
  | BeginRectangleSelectionMessage;

export type BackgroundRuntimeMessage =
  | RunOverlayActionMessage
  | CacheOverlaySessionMessage
  | CacheBatchOverlaySessionMessage
  | AppendSessionItemMessage
  | RemoveSessionItemMessage
  | ToggleSessionItemImageMessage
  | ClearOverlaySessionMessage
  | OpenOverlayMessage
  | DeleteActiveArticleCacheMessage
  | ClearSelectionBatchMessage
  | ExportMarkdownMessage;
