import { MAX_SELECTION_SESSION_ITEMS } from '../../shared/config/phase0';
import type { ExtensionSettings } from '../../shared/config/phase0';
import type {
  ModelOption,
  OverlayPayload,
  SelectionCapturePayload,
  SelectionSessionItem,
  SelectionSessionSource,
} from '../../shared/contracts/messages';
import { loadExtensionSettings } from '../../shared/storage/settingsStorage';
import { renderOverlay } from '../gateways/tabMessagingGateway';
import {
  clearAnalysisSession,
  getAnalysisSession,
  getLatestSelectionItem,
  setAnalysisSession,
  type SelectionAnalysisSession,
} from '../services/analysisSessionStore';
import { cropSelectionImage } from '../services/cropSelectionImage';

export async function appendSelectionSessionItem(
  tab: chrome.tabs.Tab,
  selection: SelectionCapturePayload,
  source: SelectionSessionSource
): Promise<SelectionSessionItem> {
  const tabId = tab.id;
  if (tabId === undefined) {
    throw new Error('Active tab could not be resolved.');
  }

  const existingSession = getAnalysisSession(tabId);
  if ((existingSession?.items.length ?? 0) >= MAX_SELECTION_SESSION_ITEMS) {
    throw new Error(
      `You can keep up to ${MAX_SELECTION_SESSION_ITEMS} selections in one batch.`
    );
  }

  const screenshotDataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: 'png',
  });
  const cropResult = await cropSelectionImage(screenshotDataUrl, selection);
  const settings = await loadExtensionSettings();

  const nextItem: SelectionSessionItem = {
    id: createSessionItemId(source),
    source,
    selection,
    includeImage: source === 'free-rectangle',
    previewImageUrl: cropResult.imageDataUrl,
    cropDurationMs: cropResult.durationMs,
  };

  const nextSession: SelectionAnalysisSession = {
    items: [...(existingSession?.items ?? []), nextItem],
    modelOptions: resolveModelOptions(existingSession, settings),
    lastAction: existingSession?.lastAction ?? 'translation',
    lastModelName:
      existingSession?.lastModelName || settings.defaultModel || undefined,
    lastCustomPrompt: existingSession?.lastCustomPrompt,
  };

  setAnalysisSession(tabId, nextSession);
  await renderOverlay(tabId, buildOverlayPayload(nextSession));
  return nextItem;
}

export async function removeSelectionSessionItem(
  tabId: number,
  itemId: string
): Promise<void> {
  const session = getAnalysisSession(tabId);
  if (!session) {
    return;
  }

  const nextItems = session.items.filter((item) => item.id !== itemId);
  if (nextItems.length === session.items.length) {
    throw new Error('Selection item could not be found.');
  }

  if (nextItems.length === 0) {
    clearAnalysisSession(tabId);
    await renderOverlay(tabId, {
      status: 'success',
      action: session.lastAction,
      modelName: session.lastModelName,
      modelOptions: [...session.modelOptions],
      customPrompt: session.lastCustomPrompt,
      sessionReady: false,
      sessionItems: [],
      maxSessionItems: MAX_SELECTION_SESSION_ITEMS,
      selectedText: '',
    });
    return;
  }

  const nextSession: SelectionAnalysisSession = {
    ...session,
    items: nextItems,
    modelOptions: [...session.modelOptions],
  };

  setAnalysisSession(tabId, nextSession);
  await renderOverlay(tabId, buildOverlayPayload(nextSession));
}

export function buildOverlayPayload(
  session: SelectionAnalysisSession
): OverlayPayload {
  const latestItem = getLatestSelectionItem(session);

  return {
    status: 'success',
    action: session.lastAction,
    modelName: session.lastModelName,
    modelOptions: [...session.modelOptions],
    sessionItems: session.items.map((item) => ({ ...item })),
    maxSessionItems: MAX_SELECTION_SESSION_ITEMS,
    customPrompt: session.lastCustomPrompt,
    sessionReady: session.items.length > 0,
    selectedText: buildSelectedText(latestItem),
    previewImageUrl: latestItem?.previewImageUrl,
    timingMs: latestItem?.cropDurationMs,
  };
}

function buildSelectedText(item: SelectionSessionItem | undefined): string {
  if (!item) {
    return '';
  }

  return item.selection.text || '[Image region only]';
}

function resolveModelOptions(
  session: SelectionAnalysisSession | undefined,
  settings: ExtensionSettings
): ModelOption[] {
  if (session?.modelOptions.length) {
    return [...session.modelOptions];
  }

  return settings.lastKnownModels.map((modelId) => ({
    modelId,
    displayName: modelId,
  }));
}

function createSessionItemId(source: SelectionSessionSource): string {
  return `${source}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}