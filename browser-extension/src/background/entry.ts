import { ensurePhase0ContextMenu } from './menus/phase0ContextMenu';
import {
  clearAnalysisSession,
  setAnalysisSession,
} from './services/analysisSessionStore';
import { runSelectionAnalysis } from './usecases/runSelectionAnalysis';
import {
  appendSelectionSessionItem,
  removeSelectionSessionItem,
} from './usecases/updateSelectionSession';
import {
  PHASE0_MENU_ID,
  PHASE2_RECTANGLE_COMMAND_ID,
  PHASE2_RECTANGLE_MENU_ID,
} from '../shared/config/phase0';
import type {
  AppendSessionItemResponse,
  BeginRectangleSelectionResponse,
  BackgroundRuntimeMessage,
  CacheOverlaySessionMessage,
  RemoveSessionItemResponse,
  RunOverlayActionResponse,
} from '../shared/contracts/messages';

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
    if (command !== PHASE2_RECTANGLE_COMMAND_ID || !tab?.id) {
      return;
    }

    void handleRectangleSelectionStart(tab, 'command');
  });

  chrome.runtime.onMessage.addListener(
    (message: BackgroundRuntimeMessage, sender, sendResponse) => {
      if (
        message.type === 'phase1.cacheOverlaySession' &&
        sender.tab?.id !== undefined
      ) {
        // Overlay 上の再実行は再選択を要求しないため、直前の selection/crop 結果を tab 単位で保持する。
        cacheOverlaySession(sender.tab.id, message);
        sendResponse({ ok: true });
        return false;
      }

      if (
        message.type === 'phase2.clearOverlaySession' &&
        sender.tab?.id !== undefined
      ) {
        clearAnalysisSession(sender.tab.id);
        sendResponse({ ok: true });
        return false;
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

      if (message.type !== 'phase1.runOverlayAction' || !sender.tab) {
        return false;
      }

      void handleOverlayAction(message, sender.tab, sendResponse);
      return true;
    }
  );
}

function cacheOverlaySession(
  tabId: number,
  message: CacheOverlaySessionMessage
): void {
  setAnalysisSession(tabId, {
    items: [message.payload.item],
    modelOptions: message.payload.modelOptions,
    lastAction: 'translation',
  });
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
