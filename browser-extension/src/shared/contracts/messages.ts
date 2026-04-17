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
  selectedText?: string;
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
}

/**
 * Phase 0 は単発 translation の message 群、Phase 1 は capture 済み session の再利用 message 群を表す。
 * contract を shared に集約しておくと、background/content/popup が同じ payload 形状を前提に進化できる。
 */
export interface CollectSelectionMessage {
  type: 'phase0.collectSelection';
  fallbackText?: string;
}

export interface RenderOverlayMessage {
  type: 'phase0.renderOverlay';
  payload: OverlayPayload;
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

export type ContentScriptMessage =
  | CollectSelectionMessage
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
  | ClearOverlaySessionMessage;
