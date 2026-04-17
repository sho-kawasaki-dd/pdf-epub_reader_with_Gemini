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
import {
  collectSelection,
  renderOverlay,
} from '../gateways/tabMessagingGateway';
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

  const existingSession = await getAnalysisSession(tabId);
  if ((existingSession?.items.length ?? 0) >= MAX_SELECTION_SESSION_ITEMS) {
    throw new Error(
      `You can keep up to ${MAX_SELECTION_SESSION_ITEMS} selections in one batch.`
    );
  }

  const windowId = await resolveTabWindowId(tab);
  const screenshotDataUrl = await chrome.tabs.captureVisibleTab(windowId, {
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
    articleContext: existingSession?.articleContext,
    articleContextError: existingSession?.articleContextError,
  };

  await setAnalysisSession(tabId, nextSession);
  await renderOverlay(tabId, buildOverlayPayload(nextSession));
  return nextItem;
}

export async function appendLiveSelectionSessionItem(
  tab: chrome.tabs.Tab
): Promise<SelectionSessionItem> {
  const tabId = tab.id;
  if (tabId === undefined) {
    throw new Error('Active tab could not be resolved.');
  }

  const selection = await collectSelection(tabId, '', { liveOnly: true });
  if (!selection.ok || !selection.payload) {
    const message =
      selection.error ??
      'A live text selection is required. Select text on the page and try again.';
    const settings = await loadExtensionSettings();
    const session = await getAnalysisSession(tabId);
    await renderOverlay(
      tabId,
      session
        ? buildOverlayPayload(session, {
            status: 'error',
            error: message,
            launcherOnly: false,
            preserveDrafts: true,
          })
        : buildEmptyOverlayPayload(settings, {
            status: 'error',
            error: message,
            launcherOnly: false,
            preserveDrafts: true,
          })
    );
    throw new Error(message);
  }

  return appendSelectionSessionItem(tab, selection.payload, 'text-selection');
}

export async function removeSelectionSessionItem(
  tabId: number,
  itemId: string
): Promise<void> {
  const session = await getAnalysisSession(tabId);
  if (!session) {
    return;
  }

  const nextItems = session.items.filter((item) => item.id !== itemId);
  if (nextItems.length === session.items.length) {
    throw new Error('Selection item could not be found.');
  }

  if (nextItems.length === 0) {
    await clearAnalysisSession(tabId);
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

  await setAnalysisSession(tabId, nextSession);
  await renderOverlay(tabId, buildOverlayPayload(nextSession));
}

export async function toggleSelectionSessionItemImage(
  tabId: number,
  itemId: string,
  includeImage: boolean
): Promise<void> {
  const session = await getAnalysisSession(tabId);
  if (!session) {
    throw new Error('Analysis session could not be found.');
  }

  let foundItem = false;
  const nextItems = session.items.map((item) => {
    if (item.id !== itemId) {
      return item;
    }

    foundItem = true;
    if (includeImage && !item.previewImageUrl) {
      throw new Error('A cached crop preview is required before enabling image inclusion.');
    }

    return {
      ...item,
      includeImage,
    };
  });

  if (!foundItem) {
    throw new Error('Selection item could not be found.');
  }

  const nextSession: SelectionAnalysisSession = {
    ...session,
    items: nextItems,
    modelOptions: [...session.modelOptions],
  };

  await setAnalysisSession(tabId, nextSession);
  await renderOverlay(tabId, buildOverlayPayload(nextSession));
}

export function buildOverlayPayload(
  session: SelectionAnalysisSession,
  options: {
    status?: OverlayPayload['status'];
    error?: string;
    launcherOnly?: boolean;
    preserveDrafts?: boolean;
  } = {}
): OverlayPayload {
  const latestItem = getLatestSelectionItem(session);

  return {
    status: options.status ?? 'success',
    action: session.lastAction,
    modelName: session.lastModelName,
    modelOptions: [...session.modelOptions],
    sessionItems: session.items.map((item) => ({
      ...item,
      selection: {
        ...item.selection,
        rect: { ...item.selection.rect },
      },
    })),
    maxSessionItems: MAX_SELECTION_SESSION_ITEMS,
    customPrompt: session.lastCustomPrompt,
    sessionReady: session.items.length > 0,
    launcherOnly: options.launcherOnly,
    preserveDrafts: options.preserveDrafts,
    selectedText: buildSelectedText(latestItem),
    articleContext: session.articleContext,
    articleContextError: session.articleContextError,
    previewImageUrl: latestItem?.previewImageUrl,
    timingMs: latestItem?.cropDurationMs,
    error: options.error,
  };
}

export function buildEmptyOverlayPayload(
  settings: ExtensionSettings,
  options: {
    status?: OverlayPayload['status'];
    error?: string;
    launcherOnly?: boolean;
    preserveDrafts?: boolean;
  } = {}
): OverlayPayload {
  return {
    status: options.status ?? 'success',
    modelName: settings.defaultModel || undefined,
    modelOptions: settings.lastKnownModels.map((modelId) => ({
      modelId,
      displayName: modelId,
    })),
    sessionItems: [],
    maxSessionItems: MAX_SELECTION_SESSION_ITEMS,
    sessionReady: false,
    launcherOnly: options.launcherOnly,
    preserveDrafts: options.preserveDrafts,
    selectedText: '',
    error: options.error,
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

async function resolveTabWindowId(tab: chrome.tabs.Tab): Promise<number> {
  if (tab.windowId !== undefined) {
    return tab.windowId;
  }

  if (tab.id === undefined) {
    throw new Error('Active tab window could not be resolved.');
  }

  const resolvedTab = await chrome.tabs.get(tab.id);
  if (resolvedTab.windowId === undefined) {
    throw new Error('Active tab window could not be resolved.');
  }

  return resolvedTab.windowId;
}