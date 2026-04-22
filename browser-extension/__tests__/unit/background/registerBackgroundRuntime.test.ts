import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getChromeMock } from '../../mocks/chrome';

const ensurePhase0ContextMenuMock = vi.hoisted(() => vi.fn());
const openOverlaySessionMock = vi.hoisted(() => vi.fn());
const runSelectionAnalysisMock = vi.hoisted(() => vi.fn());
const appendLiveSelectionSessionItemMock = vi.hoisted(() => vi.fn());
const appendSelectionSessionItemMock = vi.hoisted(() => vi.fn());
const removeSelectionSessionItemMock = vi.hoisted(() => vi.fn());
const toggleSelectionSessionItemImageMock = vi.hoisted(() => vi.fn());
const buildOverlayPayloadMock = vi.hoisted(() => vi.fn());
const invalidateArticleCacheMock = vi.hoisted(() => vi.fn());
const buildNavigatedSessionStateMock = vi.hoisted(() => vi.fn());
const loadExtensionSettingsMock = vi.hoisted(() => vi.fn());
const renderOverlayMock = vi.hoisted(() => vi.fn());
const exportMarkdownMock = vi.hoisted(() => vi.fn());

vi.mock('../../../src/background/menus/phase0ContextMenu', () => ({
  ensurePhase0ContextMenu: ensurePhase0ContextMenuMock,
}));

vi.mock('../../../src/background/usecases/runSelectionAnalysis', () => ({
  runSelectionAnalysis: runSelectionAnalysisMock,
}));

vi.mock('../../../src/background/usecases/openOverlaySession', () => ({
  openOverlaySession: openOverlaySessionMock,
}));

vi.mock('../../../src/background/usecases/updateSelectionSession', () => ({
  appendLiveSelectionSessionItem: appendLiveSelectionSessionItemMock,
  appendSelectionSessionItem: appendSelectionSessionItemMock,
  removeSelectionSessionItem: removeSelectionSessionItemMock,
  toggleSelectionSessionItemImage: toggleSelectionSessionItemImageMock,
  buildOverlayPayload: buildOverlayPayloadMock,
}));

vi.mock('../../../src/background/services/articleCacheService', () => ({
  invalidateArticleCache: invalidateArticleCacheMock,
  buildNavigatedSessionState: buildNavigatedSessionStateMock,
}));

vi.mock('../../../src/shared/storage/settingsStorage', () => ({
  loadExtensionSettings: loadExtensionSettingsMock,
}));

vi.mock('../../../src/background/usecases/exportMarkdown', () => ({
  exportMarkdown: exportMarkdownMock,
}));

vi.mock('../../../src/background/gateways/tabMessagingGateway', () => ({
  renderOverlay: renderOverlayMock,
}));

import { registerBackgroundRuntime } from '../../../src/background/entry';
import {
  clearAnalysisSession,
  getAnalysisSession,
  setAnalysisSession,
} from '../../../src/background/services/analysisSessionStore';
import {
  PHASE0_MENU_ID,
  PHASE3_ADD_SELECTION_COMMAND_ID,
  PHASE3_OPEN_OVERLAY_COMMAND_ID,
  PHASE2_RECTANGLE_COMMAND_ID,
  PHASE2_RECTANGLE_MENU_ID,
} from '../../../src/shared/config/phase0';

describe('registerBackgroundRuntime', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await clearAnalysisSession(7);
    loadExtensionSettingsMock.mockResolvedValue({
      apiBaseUrl: 'http://127.0.0.1:9000',
      defaultModel: 'gemini-2.5-flash',
      lastKnownModels: ['gemini-2.5-flash'],
      uiLanguage: 'en',
      articleCache: {
        enableAutoCreate: true,
      },
      markdownExport: {
        includeExplanation: true,
        includeSelections: true,
        includeRawResponse: false,
        includeArticleMetadata: false,
        includeUsageMetrics: false,
        includeYamlFrontmatter: false,
      },
    });
    invalidateArticleCacheMock.mockImplementation(async (session) => session);
    buildNavigatedSessionStateMock.mockImplementation((session) => session);
    buildOverlayPayloadMock.mockImplementation((session, options) => ({
      ...session,
      ...options,
    }));
    exportMarkdownMock.mockResolvedValue({
      downloadId: 17,
      filename: 'Example-20260420-103000.md',
    });
  });

  function getContextMenuHandler() {
    return (
      getChromeMock().contextMenus.onClicked
        .addListener as unknown as ReturnType<typeof vi.fn>
    ).mock.calls[0][0];
  }

  function getCommandHandler() {
    return (
      getChromeMock().commands.onCommand.addListener as unknown as ReturnType<
        typeof vi.fn
      >
    ).mock.calls[0][0];
  }

  function getRuntimeMessageHandler() {
    return (
      getChromeMock().runtime.onMessage.addListener as unknown as ReturnType<
        typeof vi.fn
      >
    ).mock.calls[0][0];
  }

  function getTabUpdatedHandler() {
    return (
      getChromeMock().tabs.onUpdated.addListener as unknown as ReturnType<
        typeof vi.fn
      >
    ).mock.calls[0][0];
  }

  async function flushAsyncWork(iterations = 8) {
    for (let index = 0; index < iterations; index += 1) {
      await Promise.resolve();
    }
  }

  it('registers startup hooks and the background listeners', () => {
    const chromeMock = getChromeMock();

    registerBackgroundRuntime();

    expect(chromeMock.runtime.onInstalled.addListener).toHaveBeenCalledTimes(1);
    expect(chromeMock.runtime.onStartup.addListener).toHaveBeenCalledTimes(1);
    expect(chromeMock.contextMenus.onClicked.addListener).toHaveBeenCalledTimes(
      1
    );
    expect(chromeMock.tabs.onRemoved.addListener).toHaveBeenCalledTimes(1);
    expect(chromeMock.tabs.onUpdated.addListener).toHaveBeenCalledTimes(1);
    expect(chromeMock.runtime.onMessage.addListener).toHaveBeenCalledTimes(1);
    expect(chromeMock.commands.onCommand.addListener).toHaveBeenCalledTimes(1);
  });

  it('runs translation when the selection context menu is clicked', () => {
    registerBackgroundRuntime();

    const handler = getContextMenuHandler();
    handler(
      {
        menuItemId: PHASE0_MENU_ID,
        selectionText: 'Selected text',
      },
      { id: 7, windowId: 3 }
    );

    expect(runSelectionAnalysisMock).toHaveBeenCalledWith(
      { id: 7, windowId: 3 },
      'Selected text',
      { action: 'translation' }
    );
  });

  it('forwards free-rectangle starts from the context menu to the content script', async () => {
    (
      getChromeMock().tabs.sendMessage as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      ok: true,
    });
    registerBackgroundRuntime();

    const handler = getContextMenuHandler();
    handler(
      {
        menuItemId: PHASE2_RECTANGLE_MENU_ID,
      },
      { id: 7, windowId: 3 }
    );
    await Promise.resolve();

    expect(getChromeMock().tabs.sendMessage).toHaveBeenCalledWith(7, {
      type: 'phase2.beginRectangleSelection',
      payload: { triggerSource: 'context-menu' },
    });
  });

  it('forwards free-rectangle starts from the keyboard command to the content script', async () => {
    (
      getChromeMock().tabs.sendMessage as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      ok: true,
    });
    registerBackgroundRuntime();

    const handler = getCommandHandler();
    handler(PHASE2_RECTANGLE_COMMAND_ID, { id: 7, windowId: 3 });
    await flushAsyncWork();

    expect(getChromeMock().tabs.sendMessage).toHaveBeenCalledWith(7, {
      type: 'phase2.beginRectangleSelection',
      payload: { triggerSource: 'command' },
    });
  });

  it('dispatches the overlay reopen command to the open-overlay usecase', async () => {
    openOverlaySessionMock.mockResolvedValue(undefined);
    registerBackgroundRuntime();

    const handler = getCommandHandler();
    handler(PHASE3_OPEN_OVERLAY_COMMAND_ID, { id: 7, windowId: 3 });
    await Promise.resolve();

    expect(openOverlaySessionMock).toHaveBeenCalledWith(7);
  });

  it('dispatches the add-selection command to the live-selection append usecase', async () => {
    appendLiveSelectionSessionItemMock.mockResolvedValue({
      id: 'selection-live',
    });
    registerBackgroundRuntime();

    const handler = getCommandHandler();
    handler(PHASE3_ADD_SELECTION_COMMAND_ID, { id: 7, windowId: 3 });
    await Promise.resolve();

    expect(appendLiveSelectionSessionItemMock).toHaveBeenCalledWith({
      id: 7,
      windowId: 3,
    });
  });

  it('stores the cached overlay session as a batch item', async () => {
    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();
    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase1.cacheOverlaySession',
        payload: {
          item: {
            id: 'selection-1',
            source: 'text-selection',
            selection: {
              text: 'Selected text',
              rect: { left: 1, top: 2, width: 3, height: 4 },
              viewportWidth: 100,
              viewportHeight: 100,
              devicePixelRatio: 1,
              url: 'https://example.com',
              pageTitle: 'Example',
            },
            includeImage: true,
            previewImageUrl: 'data:image/webp;base64,crop',
            cropDurationMs: 12,
          },
          modelOptions: [],
        },
      },
      { tab: { id: 7 } },
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork();
    expect((await getAnalysisSession(7))?.items).toHaveLength(1);
    expect((await getAnalysisSession(7))?.items[0]?.id).toBe('selection-1');
  });

  it('clears the cached session when the overlay closes', async () => {
    await setAnalysisSession(7, {
      items: [],
      modelOptions: [],
      lastAction: 'translation',
      articleCacheState: {
        status: 'active',
        cacheName: 'cachedContents/article-1',
      },
    });
    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();

    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase2.clearOverlaySession',
      },
      { tab: { id: 7 } },
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork(16);
    expect(sendResponse).toHaveBeenCalledWith({ ok: true });
    expect(invalidateArticleCacheMock).toHaveBeenCalledWith(
      expect.objectContaining({
        articleCacheState: expect.objectContaining({
          cacheName: 'cachedContents/article-1',
        }),
      }),
      expect.objectContaining({ reason: 'manual-delete' })
    );
    expect(await getAnalysisSession(7)).toBeUndefined();
  });

  it('delegates session item append requests to the updateSelectionSession usecase', async () => {
    appendSelectionSessionItemMock.mockResolvedValue({ id: 'selection-2' });
    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();
    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase2.appendSessionItem',
        payload: {
          source: 'text-selection',
          selection: {
            text: 'Selected text',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
        },
      },
      { tab: { id: 7 } },
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork();
    expect(appendSelectionSessionItemMock).toHaveBeenCalledWith(
      { id: 7 },
      expect.objectContaining({ text: 'Selected text' }),
      'text-selection'
    );
    expect(sendResponse).toHaveBeenCalledWith({
      ok: true,
      item: { id: 'selection-2' },
    });
  });

  it('delegates session item removal requests to the updateSelectionSession usecase', async () => {
    removeSelectionSessionItemMock.mockResolvedValue(undefined);
    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();
    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase2.removeSessionItem',
        payload: { itemId: 'selection-2' },
      },
      { tab: { id: 7 } },
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork();
    expect(removeSelectionSessionItemMock).toHaveBeenCalledWith(
      7,
      'selection-2'
    );
    expect(sendResponse).toHaveBeenCalledWith({ ok: true });
  });

  it('delegates session item image toggles to the updateSelectionSession usecase', async () => {
    toggleSelectionSessionItemImageMock.mockResolvedValue(undefined);
    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();
    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase2.toggleSessionItemImage',
        payload: {
          itemId: 'selection-2',
          includeImage: true,
        },
      },
      { tab: { id: 7 } },
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork();
    expect(toggleSelectionSessionItemImageMock).toHaveBeenCalledWith(
      7,
      'selection-2',
      true
    );
    expect(sendResponse).toHaveBeenCalledWith({ ok: true });
  });

  it('opens the overlay on the active tab for popup-triggered requests', async () => {
    openOverlaySessionMock.mockResolvedValue(undefined);
    (
      getChromeMock().tabs.query as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([{ id: 7, windowId: 3 }]);
    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();
    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase3.openOverlay',
      },
      {},
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork();
    expect(getChromeMock().tabs.query).toHaveBeenCalledWith({
      active: true,
      lastFocusedWindow: true,
    });
    expect(openOverlaySessionMock).toHaveBeenCalledWith(7);
    expect(sendResponse).toHaveBeenCalledWith({ ok: true });
  });

  it('clears the cached session when the tab is removed', async () => {
    await setAnalysisSession(7, {
      items: [],
      modelOptions: [],
      lastAction: 'translation',
      articleCacheState: {
        status: 'active',
        cacheName: 'cachedContents/article-1',
      },
    });
    registerBackgroundRuntime();

    const onRemovedHandler = (
      getChromeMock().tabs.onRemoved.addListener as unknown as ReturnType<
        typeof vi.fn
      >
    ).mock.calls[0][0] as (tabId: number) => void;

    onRemovedHandler(7);
    await flushAsyncWork();

    expect(invalidateArticleCacheMock).toHaveBeenCalledWith(
      expect.objectContaining({
        articleCacheState: expect.objectContaining({
          cacheName: 'cachedContents/article-1',
        }),
      }),
      expect.objectContaining({ reason: 'manual-delete' })
    );
    expect(await getAnalysisSession(7)).toBeUndefined();
  });

  it('preserves the cached article state when the tab URL changes', async () => {
    await setAnalysisSession(7, {
      items: [],
      modelOptions: [],
      lastAction: 'translation',
      articleCacheState: {
        status: 'active',
        cacheName: 'cachedContents/article-1',
      },
    });
    buildNavigatedSessionStateMock.mockImplementationOnce(
      (session, nextUrl) => ({
        ...session,
        items: [],
        articleContextError: `Page changed to ${nextUrl}. Article context will be refreshed on the next run.`,
      })
    );

    registerBackgroundRuntime();

    const handler = getTabUpdatedHandler();
    handler(7, { url: 'https://example.com/updated' });
    await flushAsyncWork();

    expect(invalidateArticleCacheMock).not.toHaveBeenCalled();
    expect(buildNavigatedSessionStateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        articleCacheState: expect.objectContaining({ status: 'active' }),
      }),
      'https://example.com/updated'
    );
  });

  it('handles manual article cache deletion from runtime messages', async () => {
    await setAnalysisSession(7, {
      items: [],
      modelOptions: [],
      lastAction: 'translation',
      articleCacheState: {
        status: 'active',
        cacheName: 'cachedContents/article-1',
      },
    });
    invalidateArticleCacheMock.mockImplementationOnce(async (session) => ({
      ...session,
      articleCacheState: {
        status: 'invalidated',
        invalidationReason: 'manual-delete',
        notice: 'Article cache was deleted manually for this tab.',
      },
    }));

    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();
    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase4.deleteActiveArticleCache',
      },
      { tab: { id: 7 } },
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork();

    expect(invalidateArticleCacheMock).toHaveBeenCalledWith(
      expect.objectContaining({
        articleCacheState: expect.objectContaining({ status: 'active' }),
      }),
      expect.objectContaining({ reason: 'manual-delete' })
    );
    expect(renderOverlayMock).toHaveBeenCalled();
    expect(sendResponse).toHaveBeenCalledWith({ ok: true });
  });

  it('exports markdown through the background runtime with stored export settings', async () => {
    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();
    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase5.exportMarkdown',
        payload: {
          action: 'translation_with_explanation',
          modelName: 'gemini-2.5-pro',
          pageTitle: 'Example article',
          pageUrl: 'https://example.com/article',
          translatedText: 'Translated body',
          explanation: 'Why this was translated that way.',
          rawResponse: 'raw payload',
          selectedText: 'Original selection',
          sessionItems: [],
        },
      },
      { tab: { id: 7 } },
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork();

    expect(loadExtensionSettingsMock).toHaveBeenCalled();
    expect(exportMarkdownMock).toHaveBeenCalledWith(
      expect.objectContaining({
        pageTitle: 'Example article',
        pageUrl: 'https://example.com/article',
      }),
      expect.objectContaining({
        includeExplanation: true,
        includeSelections: true,
      })
    );
    expect(sendResponse).toHaveBeenCalledWith({
      ok: true,
      downloadId: 17,
      filename: 'Example-20260420-103000.md',
    });
  });

  it('maps markdown export failures to an error runtime response', async () => {
    exportMarkdownMock.mockRejectedValueOnce(
      new Error('Markdown download failed: The download was blocked.')
    );
    registerBackgroundRuntime();

    const handler = getRuntimeMessageHandler();
    const sendResponse = vi.fn();
    const keepChannelOpen = handler(
      {
        type: 'phase5.exportMarkdown',
        payload: {
          action: 'translation',
          pageTitle: 'Example article',
          pageUrl: 'https://example.com/article',
          translatedText: 'Translated body',
        },
      },
      { tab: { id: 7 } },
      sendResponse
    );

    expect(keepChannelOpen).toBe(true);
    await flushAsyncWork();

    expect(sendResponse).toHaveBeenCalledWith({
      ok: false,
      error: 'Markdown download failed: The download was blocked.',
    });
  });
});
