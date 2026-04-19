import { ensurePhase0ContextMenu } from './menus/phase0ContextMenu';
import { openOverlaySession } from './usecases/openOverlaySession';
import {
  clearAnalysisSession,
  getAnalysisSession,
  setAnalysisSession,
} from './services/analysisSessionStore';
import {
  buildNavigatedSessionState,
  invalidateArticleCache,
} from './services/articleCacheService';
import { runSelectionAnalysis } from './usecases/runSelectionAnalysis';
import {
  appendLiveSelectionSessionItem,
  appendSelectionSessionItem,
  removeSelectionSessionItem,
  toggleSelectionSessionItemImage,
  buildOverlayPayload,
} from './usecases/updateSelectionSession';
import { loadExtensionSettings } from '../shared/storage/settingsStorage';
import {
  PHASE0_MENU_ID,
  PHASE3_ADD_SELECTION_COMMAND_ID,
  PHASE3_OPEN_OVERLAY_COMMAND_ID,
  PHASE2_RECTANGLE_COMMAND_ID,
  PHASE2_RECTANGLE_MENU_ID,
} from '../shared/config/phase0';
import type {
  AppendSessionItemResponse,
  BeginRectangleSelectionResponse,
  BackgroundRuntimeMessage,
  CacheBatchOverlaySessionMessage,
  CacheOverlaySessionMessage,
  RemoveSessionItemResponse,
  OpenOverlayResponse,
  RunOverlayActionResponse,
  ToggleSessionItemImageResponse,
  DeleteActiveArticleCacheResponse,
} from '../shared/contracts/messages';
import { renderOverlay } from './gateways/tabMessagingGateway';

/**
 * Background runtime は権限が必要な処理の集約点であり、Local API 通信もここを通す。
 * Content script から直接 localhost を叩かせないことで、対象ページの CSP と権限境界を横断しない。
 */
export function registerBackgroundRuntime(): void {
  console.log('Gem Read Background Service Worker Loaded');

  chrome.runtime.onInstalled.addListener(() => {
    void ensurePhase0ContextMenu();
  });

  chrome.runtime.onStartup.addListener(() => {
    void ensurePhase0ContextMenu();
  });

  chrome.tabs.onRemoved?.addListener((tabId) => {
    void clearAnalysisSession(tabId);
  });

  chrome.tabs.onUpdated?.addListener((tabId, changeInfo) => {
    void handleTabUpdated(tabId, changeInfo);
  });

  chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (!tab?.id) {
      return;
    }

    if (info.menuItemId === PHASE0_MENU_ID) {
      void runSelectionAnalysis(tab, info.selectionText ?? '', {
        action: 'translation',
      });
      return;
    }

    if (info.menuItemId === PHASE2_RECTANGLE_MENU_ID) {
      void handleRectangleSelectionStart(tab, 'context-menu');
    }
  });

  chrome.commands?.onCommand.addListener((command, tab) => {
    void handleBrowserCommand(command, tab);
  });

  chrome.runtime.onMessage.addListener(
    (message: BackgroundRuntimeMessage, sender, sendResponse) => {
      if (
        message.type === 'phase1.cacheOverlaySession' &&
        sender.tab?.id !== undefined
      ) {
        void handleCacheOverlaySession(sender.tab.id, message, sendResponse);
        return true;
      }

      if (
        message.type === 'phase2.clearOverlaySession' &&
        sender.tab?.id !== undefined
      ) {
        void handleClearOverlaySession(sender.tab.id, sendResponse);
        return true;
      }

      if (
        message.type === 'phase2.cacheBatchOverlaySession' &&
        sender.tab?.id !== undefined
      ) {
        void handleCacheBatchOverlaySession(sender.tab.id, message, sendResponse);
        return true;
      }

      if (message.type === 'phase3.openOverlay') {
        void handleOpenOverlayRequest(sendResponse);
        return true;
      }

      if (message.type === 'phase2.appendSessionItem' && sender.tab) {
        void handleAppendSessionItem(message, sender.tab, sendResponse);
        return true;
      }

      if (
        message.type === 'phase2.removeSessionItem' &&
        sender.tab?.id !== undefined
      ) {
        void handleRemoveSessionItem(message, sender.tab.id, sendResponse);
        return true;
      }

      if (
        message.type === 'phase2.toggleSessionItemImage' &&
        sender.tab?.id !== undefined
      ) {
        void handleToggleSessionItemImage(message, sender.tab.id, sendResponse);
        return true;
      }

      if (
        message.type === 'phase4.deleteActiveArticleCache' &&
        sender.tab?.id !== undefined
      ) {
        void handleDeleteActiveArticleCache(sender.tab.id, sendResponse);
        return true;
      }

      if (message.type !== 'phase1.runOverlayAction' || !sender.tab) {
        return false;
      }

      void handleOverlayAction(message, sender.tab, sendResponse);
      return true;
    }
  );
}

async function handleBrowserCommand(
  command: string,
  tab?: chrome.tabs.Tab
): Promise<void> {
  const targetTab = await resolveTargetTab(tab);
  if (!targetTab?.id) {
    return;
  }

  if (command === PHASE3_OPEN_OVERLAY_COMMAND_ID) {
    await openOverlaySession(targetTab.id);
    return;
  }

  if (command === PHASE3_ADD_SELECTION_COMMAND_ID) {
    try {
      await appendLiveSelectionSessionItem(targetTab);
    } catch {
      // Explicit overlay errors are already rendered by the usecase when possible.
    }
    return;
  }

  if (command === PHASE2_RECTANGLE_COMMAND_ID) {
    await handleRectangleSelectionStart(targetTab, 'command');
  }
}

async function cacheOverlaySession(
  tabId: number,
  message: CacheOverlaySessionMessage
): Promise<void> {
  const existingSession = await getAnalysisSession(tabId);
  await setAnalysisSession(tabId, {
    items: [message.payload.item],
    modelOptions: message.payload.modelOptions,
    lastAction: 'translation',
    lastModelName: existingSession?.lastModelName,
    lastCustomPrompt: existingSession?.lastCustomPrompt,
    articleContext: existingSession?.articleContext,
    articleContextError: existingSession?.articleContextError,
    articleCacheState: existingSession?.articleCacheState,
  });
}

async function cacheBatchOverlaySession(
  tabId: number,
  message: CacheBatchOverlaySessionMessage
): Promise<void> {
  const existingSession = await getAnalysisSession(tabId);
  await setAnalysisSession(tabId, {
    items: message.payload.items.map((item) => ({
      ...item,
      selection: {
        ...item.selection,
        rect: { ...item.selection.rect },
      },
    })),
    modelOptions: [...message.payload.modelOptions],
    lastAction: message.payload.lastAction ?? 'translation',
    lastModelName: message.payload.lastModelName,
    lastCustomPrompt: message.payload.lastCustomPrompt,
    articleContext: existingSession?.articleContext,
    articleContextError: existingSession?.articleContextError,
    articleCacheState: existingSession?.articleCacheState,
  });
}

async function handleCacheOverlaySession(
  tabId: number,
  message: CacheOverlaySessionMessage,
  sendResponse: (response: { ok: boolean; error?: string }) => void
): Promise<void> {
  try {
    await cacheOverlaySession(tabId, message);
    sendResponse({ ok: true });
  } catch (error) {
    sendResponse({
      ok: false,
      error:
        error instanceof Error ? error.message : 'Failed to cache overlay session.',
    });
  }
}

async function handleCacheBatchOverlaySession(
  tabId: number,
  message: CacheBatchOverlaySessionMessage,
  sendResponse: (response: { ok: boolean; error?: string }) => void
): Promise<void> {
  try {
    await cacheBatchOverlaySession(tabId, message);
    sendResponse({ ok: true });
  } catch (error) {
    sendResponse({
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : 'Failed to cache batch overlay session.',
    });
  }
}

async function handleClearOverlaySession(
  tabId: number,
  sendResponse: (response: { ok: boolean }) => void
): Promise<void> {
  try {
    await clearAnalysisSession(tabId);
    sendResponse({ ok: true });
  } catch {
    sendResponse({ ok: false });
  }
}

async function handleOpenOverlayRequest(
  sendResponse: (response: OpenOverlayResponse) => void
): Promise<void> {
  try {
    const targetTab = await resolveTargetTab();
    if (!targetTab?.id) {
      sendResponse({
        ok: false,
        error: 'No active browser tab is available for Gem Read.',
      });
      return;
    }

    await openOverlaySession(targetTab.id);
    sendResponse({ ok: true });
  } catch (error) {
    sendResponse({
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : 'Failed to open the Gem Read overlay.',
    });
  }
}

async function resolveTargetTab(
  tab?: chrome.tabs.Tab
): Promise<chrome.tabs.Tab | undefined> {
  if (tab?.id !== undefined) {
    return tab;
  }

  const [activeTab] = await chrome.tabs.query({
    active: true,
    lastFocusedWindow: true,
  });
  return activeTab;
}

async function handleRectangleSelectionStart(
  tab: chrome.tabs.Tab,
  triggerSource: 'context-menu' | 'command'
): Promise<void> {
  if (tab.id === undefined) {
    return;
  }

  try {
    const response = (await chrome.tabs.sendMessage(tab.id, {
      type: 'phase2.beginRectangleSelection',
      payload: { triggerSource },
    })) as BeginRectangleSelectionResponse | undefined;

    if (response?.ok !== false) {
      return;
    }

    await chrome.tabs.sendMessage(tab.id, {
      type: 'phase0.renderOverlay',
      payload: {
        status: 'error',
        selectedText: '',
        error:
          response.error ??
          'Rectangle selection could not be started on this page.',
      },
    });
  } catch (error) {
    await chrome.tabs.sendMessage(tab.id, {
      type: 'phase0.renderOverlay',
      payload: {
        status: 'error',
        selectedText: '',
        error:
          error instanceof Error
            ? error.message
            : 'Rectangle selection could not be started on this page.',
      },
    });
  }
}

async function handleOverlayAction(
  message: Extract<BackgroundRuntimeMessage, { type: 'phase1.runOverlayAction' }>,
  tab: chrome.tabs.Tab,
  sendResponse: (response: RunOverlayActionResponse) => void
): Promise<void> {
  try {
    // Overlay の action button は capture をやり直さず、既存 session の再利用だけ background に依頼する。
    await runSelectionAnalysis(tab, '', {
      action: message.payload.action,
      modelName: message.payload.modelName,
      customPrompt: message.payload.customPrompt,
      reuseCachedSession: true,
    });
    sendResponse({ ok: true });
  } catch (error) {
    sendResponse({
      ok: false,
      error: error instanceof Error ? error.message : 'Overlay action failed.',
    });
  }
}

async function handleAppendSessionItem(
  message: Extract<BackgroundRuntimeMessage, { type: 'phase2.appendSessionItem' }>,
  tab: chrome.tabs.Tab,
  sendResponse: (response: AppendSessionItemResponse) => void
): Promise<void> {
  try {
    const item = await appendSelectionSessionItem(
      tab,
      message.payload.selection,
      message.payload.source
    );
    sendResponse({ ok: true, item });
  } catch (error) {
    sendResponse({
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to append selection item.',
    });
  }
}

async function handleRemoveSessionItem(
  message: Extract<BackgroundRuntimeMessage, { type: 'phase2.removeSessionItem' }>,
  tabId: number,
  sendResponse: (response: RemoveSessionItemResponse) => void
): Promise<void> {
  try {
    await removeSelectionSessionItem(tabId, message.payload.itemId);
    sendResponse({ ok: true });
  } catch (error) {
    sendResponse({
      ok: false,
      error: error instanceof Error ? error.message : 'Failed to remove selection item.',
    });
  }
}

async function handleToggleSessionItemImage(
  message: Extract<BackgroundRuntimeMessage, { type: 'phase2.toggleSessionItemImage' }>,
  tabId: number,
  sendResponse: (response: ToggleSessionItemImageResponse) => void
): Promise<void> {
  try {
    await toggleSelectionSessionItemImage(
      tabId,
      message.payload.itemId,
      message.payload.includeImage
    );
    sendResponse({ ok: true });
  } catch (error) {
    sendResponse({
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : 'Failed to update selection image inclusion.',
    });
  }
}

async function handleDeleteActiveArticleCache(
  tabId: number,
  sendResponse: (response: DeleteActiveArticleCacheResponse) => void
): Promise<void> {
  try {
    const session = await getAnalysisSession(tabId);
    if (!session) {
      sendResponse({ ok: true });
      return;
    }

    const settings = await loadExtensionSettings();
    const nextSession = await invalidateArticleCache(session, {
      apiBaseUrl: settings.apiBaseUrl,
      reason: 'manual-delete',
      notice: 'Article cache was deleted manually for this tab.',
    });
    await setAnalysisSession(tabId, nextSession);
    await renderOverlay(
      tabId,
      buildOverlayPayload(nextSession, {
        launcherOnly: false,
        preserveDrafts: true,
      })
    );
    sendResponse({ ok: true });
  } catch (error) {
    sendResponse({
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : 'Failed to delete the active article cache.',
    });
  }
}

async function handleTabUpdated(
  tabId: number,
  changeInfo: chrome.tabs.TabChangeInfo
): Promise<void> {
  if (!changeInfo.url) {
    return;
  }

  const session = await getAnalysisSession(tabId);
  if (!session) {
    return;
  }

  // URL 変化時にキャッシュを即削除しない。SPA ではセクション切り替えで URL が
  // 変わるが本文が同じ場合があるため、次回翻訳時の syncArticleCacheState で
  // 本文ハッシュを比較してから判断する。
  await setAnalysisSession(
    tabId,
    buildNavigatedSessionState(session, changeInfo.url)
  );
}
