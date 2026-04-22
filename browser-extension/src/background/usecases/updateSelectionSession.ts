import { MAX_SELECTION_SESSION_ITEMS } from '../../shared/config/phase0';
import type { ExtensionSettings, UiLanguage } from '../../shared/config/phase0';
import type {
  ModelOption,
  OverlayPayload,
  SelectionCapturePayload,
  SelectionSessionItem,
  SelectionSessionSource,
} from '../../shared/contracts/messages';
import { loadExtensionSettings } from '../../shared/storage/settingsStorage';
import { t } from '../../shared/i18n/translator';
import {
  collectSelection,
  renderOverlay,
} from '../gateways/tabMessagingGateway';
import {
  getAnalysisSession,
  getLatestSelectionItem,
  setAnalysisSession,
  type SelectionAnalysisSession,
} from '../services/analysisSessionStore';
import { cropSelectionImage } from '../services/cropSelectionImage';
import { syncPayloadTokenEstimate } from '../services/payloadTokenService';

/**
 * selection batch の mutation はすべて background session に対して行う。
 * overlay はその mirror を描画するだけに留め、append/remove/toggle の正準状態は常に background が持つ。
 */
export async function appendSelectionSessionItem(
  tab: chrome.tabs.Tab,
  selection: SelectionCapturePayload,
  source: SelectionSessionSource
): Promise<SelectionSessionItem> {
  const settings = await loadExtensionSettings();
  const tabId = tab.id;
  if (tabId === undefined) {
    throw new Error(t(settings.uiLanguage, 'bgErrorNoActiveTab'));
  }

  const existingSession = await getAnalysisSession(tabId);
  if ((existingSession?.items.length ?? 0) >= MAX_SELECTION_SESSION_ITEMS) {
    throw new Error(t(settings.uiLanguage, 'overlayErrorBatchLimit', {
      count: MAX_SELECTION_SESSION_ITEMS,
    }));
  }

  const windowId = await resolveTabWindowId(tab, settings);
  const screenshotDataUrl = await chrome.tabs.captureVisibleTab(windowId, {
    format: 'png',
  });
  const cropResult = await cropSelectionImage(
    screenshotDataUrl,
    selection,
    settings.uiLanguage
  );

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
    articleCacheState: existingSession?.articleCacheState,
    payloadTokenEstimate: existingSession?.payloadTokenEstimate,
    payloadTokenModelName: existingSession?.payloadTokenModelName,
    payloadTokenError: existingSession?.payloadTokenError,
  };

  // selection item の追加では article cache 自体は作り直さず、request payload 見積りだけを batch 内容に合わせて更新する。
  const tokenAwareSession = await syncPayloadTokenEstimate(nextSession, {
    apiBaseUrl: settings.apiBaseUrl,
    modelName: nextSession.lastModelName || settings.defaultModel || undefined,
  });

  await setAnalysisSession(tabId, tokenAwareSession);
  await renderOverlay(
    tabId,
    buildOverlayPayload(tokenAwareSession, {
      uiLanguage: settings.uiLanguage,
    })
  );
  return nextItem;
}

export async function appendLiveSelectionSessionItem(
  tab: chrome.tabs.Tab
): Promise<SelectionSessionItem> {
  const settings = await loadExtensionSettings();
  const tabId = tab.id;
  if (tabId === undefined) {
    throw new Error(t(settings.uiLanguage, 'bgErrorNoActiveTab'));
  }

  const selection = await collectSelection(tabId, '', { liveOnly: true });
  if (!selection.ok || !selection.payload) {
    const message =
      selection.error ?? t(settings.uiLanguage, 'bgErrorLiveSelectionRequired');
    const session = await getAnalysisSession(tabId);
    // live selection が取れないときも、既存 batch や draft を消さずに overlay 上へ明示エラーだけ返す。
    await renderOverlay(
      tabId,
      session
        ? buildOverlayPayload(session, {
            status: 'error',
            error: message,
            launcherOnly: false,
            preserveDrafts: true,
            uiLanguage: settings.uiLanguage,
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
    const settings = await loadExtensionSettings();
    throw new Error(t(settings.uiLanguage, 'bgErrorItemNotFound'));
  }

  if (nextItems.length === 0) {
    const emptyBatchSession: SelectionAnalysisSession = {
      ...session,
      items: [],
      modelOptions: [...session.modelOptions],
    };
    // batch が空でも article context / cache 状態は残し、overlay reopen や次回追加時の文脈を失わないようにする。
    await setAnalysisSession(tabId, emptyBatchSession);
    const settings = await loadExtensionSettings();
    await renderOverlay(
      tabId,
      buildOverlayPayload(emptyBatchSession, {
        uiLanguage: settings.uiLanguage,
      })
    );
    return;
  }

  const nextSession: SelectionAnalysisSession = {
    ...session,
    items: nextItems,
    modelOptions: [...session.modelOptions],
  };

  const settings = await loadExtensionSettings();
  const tokenAwareSession = await syncPayloadTokenEstimate(nextSession, {
    apiBaseUrl: settings.apiBaseUrl,
    modelName: nextSession.lastModelName || settings.defaultModel || undefined,
  });

  await setAnalysisSession(tabId, tokenAwareSession);
  await renderOverlay(
    tabId,
    buildOverlayPayload(tokenAwareSession, {
      uiLanguage: settings.uiLanguage,
    })
  );
}

export async function toggleSelectionSessionItemImage(
  tabId: number,
  itemId: string,
  includeImage: boolean
): Promise<void> {
  const settings = await loadExtensionSettings();
  const session = await getAnalysisSession(tabId);
  if (!session) {
    throw new Error(t(settings.uiLanguage, 'bgErrorSelectionSessionMissing'));
  }

  let foundItem = false;
  const nextItems = session.items.map((item) => {
    if (item.id !== itemId) {
      return item;
    }

    foundItem = true;
    if (includeImage && !item.previewImageUrl) {
      throw new Error(t(settings.uiLanguage, 'bgErrorImagePreviewRequired'));
    }

    return {
      ...item,
      includeImage,
    };
  });

  if (!foundItem) {
    throw new Error(t(settings.uiLanguage, 'bgErrorItemNotFound'));
  }

  const nextSession: SelectionAnalysisSession = {
    ...session,
    items: nextItems,
    modelOptions: [...session.modelOptions],
  };

  const tokenAwareSession = await syncPayloadTokenEstimate(nextSession, {
    apiBaseUrl: settings.apiBaseUrl,
    modelName: nextSession.lastModelName || settings.defaultModel || undefined,
  });

  await setAnalysisSession(tabId, tokenAwareSession);
  await renderOverlay(
    tabId,
    buildOverlayPayload(tokenAwareSession, {
      uiLanguage: settings.uiLanguage,
    })
  );
}

export function buildOverlayPayload(
  session: SelectionAnalysisSession,
  options: {
    status?: OverlayPayload['status'];
    error?: string;
    launcherOnly?: boolean;
    preserveDrafts?: boolean;
    uiLanguage?: UiLanguage;
  } = {}
): OverlayPayload {
  const latestItem = getLatestSelectionItem(session);

  return {
    status: options.status ?? 'success',
    uiLanguage: options.uiLanguage,
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
    // overlay は session の読み取り専用 mirror なので、nested value を複製して UI 側の変更が store へ漏れないようにする。
    maxSessionItems: MAX_SELECTION_SESSION_ITEMS,
    customPrompt: session.lastCustomPrompt,
    sessionReady: session.items.length > 0,
    launcherOnly: options.launcherOnly,
    preserveDrafts: options.preserveDrafts,
    selectedText: buildSelectedText(latestItem),
    articleContext: session.articleContext,
    articleContextError: session.articleContextError,
    articleCacheState: session.articleCacheState,
    payloadTokenEstimate: session.payloadTokenEstimate,
    payloadTokenModelName: session.payloadTokenModelName,
    payloadTokenError: session.payloadTokenError,
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
    uiLanguage?: UiLanguage;
  } = {}
): OverlayPayload {
  return {
    status: options.status ?? 'success',
    uiLanguage: options.uiLanguage ?? settings.uiLanguage,
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
    articleCacheState: undefined,
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

export async function clearSelectionBatch(tabId: number): Promise<void> {
  const session = await getAnalysisSession(tabId);
  if (!session) {
    return;
  }

  const emptyBatchSession: SelectionAnalysisSession = {
    ...session,
    items: [],
    modelOptions: [...session.modelOptions],
  };

  // clear は batch だけを落とし、article cache や設定文脈は残す。
  await setAnalysisSession(tabId, emptyBatchSession);
  const settings = await loadExtensionSettings();
  await renderOverlay(
    tabId,
    buildOverlayPayload(emptyBatchSession, {
      uiLanguage: settings.uiLanguage,
    })
  );
}

function createSessionItemId(source: SelectionSessionSource): string {
  return `${source}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function resolveTabWindowId(
  tab: chrome.tabs.Tab,
  settings: ExtensionSettings
): Promise<number> {
  if (tab.windowId !== undefined) {
    return tab.windowId;
  }

  if (tab.id === undefined) {
    throw new Error(t(settings.uiLanguage, 'bgErrorActiveTabWindow'));
  }

  const resolvedTab = await chrome.tabs.get(tab.id);
  if (resolvedTab.windowId === undefined) {
    throw new Error(t(settings.uiLanguage, 'bgErrorActiveTabWindow'));
  }

  return resolvedTab.windowId;
}
