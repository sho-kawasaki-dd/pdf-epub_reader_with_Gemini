import type {
  AppendSessionItemResponse,
  BeginRectangleSelectionResponse,
  CacheBatchOverlaySessionMessage,
  CacheOverlaySessionMessage,
  ContentScriptMessage,
  RunOverlayActionResponse,
  SelectionSessionItem,
  SeedBatchOverlaySessionResponse,
  SeedOverlaySessionResponse,
} from '../shared/contracts/messages';
import { renderOverlay } from './overlay/renderOverlay';
import {
  startRectangleSelection,
} from './selection/rectangleSelectionController';
import {
  clearSelectionBatch,
  syncSelectionBatch,
} from './selection/selectionBatchController';
import {
  collectSelection,
  startSelectionTracking,
} from './selection/snapshotStore';

/**
 * Content runtime は DOM と overlay の owner であり、browser API とは直接つながない。
 * 背景権限が要る処理は background へ委譲し、content 側は選択状態と UI の同期に集中する。
 */
export function registerContentRuntime(): void {
  console.log('Gem Read Content Script Loaded');
  startSelectionTracking();

  chrome.runtime.onMessage.addListener(
    (message: ContentScriptMessage, _sender, sendResponse) => {
      if (message.type === 'phase0.collectSelection') {
        sendResponse(
          collectSelection(message.fallbackText, {
            liveOnly: message.liveOnly,
          })
        );
        return false;
      }

      if (message.type === 'phase0.renderOverlay') {
        syncSelectionBatch(message.payload.sessionItems);
        renderOverlay(message.payload);
      }

      if (message.type === 'phase1.seedOverlaySession') {
        void handleSeedOverlaySession(message, sendResponse);
        return true;
      }

      if (message.type === 'phase1.invokeOverlayAction') {
        void handleInvokeOverlayAction(message, sendResponse);
        return true;
      }

      if (message.type === 'phase2.seedBatchOverlaySession') {
        void handleSeedBatchOverlaySession(message, sendResponse);
        return true;
      }

      if (message.type === 'phase2.beginRectangleSelection') {
        void handleBeginRectangleSelection(message, sendResponse);
        return true;
      }

      return false;
    }
  );
}

async function handleSeedOverlaySession(
  message: Extract<ContentScriptMessage, { type: 'phase1.seedOverlaySession' }>,
  sendResponse: (response: SeedOverlaySessionResponse) => void
): Promise<void> {
  const selection = collectSelection(message.payload.fallbackText);
  if (!selection.ok || !selection.payload) {
    sendResponse({
      ok: false,
      error:
        selection.error ?? 'Failed to collect selection for overlay session.',
    });
    return;
  }

  const item: SelectionSessionItem = {
    id: `selection-${Date.now()}`,
    source: 'text-selection',
    selection: selection.payload,
    includeImage: true,
    previewImageUrl: message.payload.previewImageUrl,
    cropDurationMs: message.payload.cropDurationMs,
  };

  const runtimeMessage: CacheOverlaySessionMessage = {
    type: 'phase1.cacheOverlaySession',
    payload: {
      item,
      modelOptions: message.payload.modelOptions ?? [],
    },
  };

  // session の canonical copy は background に置き、overlay 再実行時の単一の参照元にする。
  const response = (await chrome.runtime.sendMessage(runtimeMessage)) as
    | SeedOverlaySessionResponse
    | undefined;
  sendResponse(response ?? { ok: true });
}

async function handleInvokeOverlayAction(
  message: Extract<
    ContentScriptMessage,
    { type: 'phase1.invokeOverlayAction' }
  >,
  sendResponse: (response: RunOverlayActionResponse) => void
): Promise<void> {
  // Content script は button click を転送するだけで、再解析フロー自体は background 側に閉じ込める。
  const response = (await chrome.runtime.sendMessage({
    type: 'phase1.runOverlayAction',
    payload: message.payload,
  })) as RunOverlayActionResponse | undefined;
  sendResponse(response ?? { ok: true });
}

async function handleSeedBatchOverlaySession(
  message: Extract<ContentScriptMessage, { type: 'phase2.seedBatchOverlaySession' }>,
  sendResponse: (response: SeedBatchOverlaySessionResponse) => void
): Promise<void> {
  const runtimeMessage: CacheBatchOverlaySessionMessage = {
    type: 'phase2.cacheBatchOverlaySession',
    payload: message.payload,
  };

  const response = (await chrome.runtime.sendMessage(runtimeMessage)) as
    | SeedBatchOverlaySessionResponse
    | undefined;
  sendResponse(response ?? { ok: true });
}

async function handleBeginRectangleSelection(
  message: Extract<ContentScriptMessage, { type: 'phase2.beginRectangleSelection' }>,
  sendResponse: (response: BeginRectangleSelectionResponse) => void
): Promise<void> {
  const result = await startRectangleSelection(message.payload.triggerSource);
  if (!result.ok || !result.payload) {
    sendResponse({
      ok: false,
      error: result.error ?? 'Rectangle selection was not completed.',
    });
    return;
  }

  const response = (await chrome.runtime.sendMessage({
    type: 'phase2.appendSessionItem',
    payload: {
      selection: result.payload,
      source: 'free-rectangle',
    },
  })) as AppendSessionItemResponse | undefined;

  if (response?.ok === false) {
    sendResponse({
      ok: false,
      error: response.error ?? 'Failed to cache rectangle selection.',
    });
    return;
  }

  sendResponse({ ok: true });
}

export function clearContentSelectionBatch(): void {
  clearSelectionBatch();
}
