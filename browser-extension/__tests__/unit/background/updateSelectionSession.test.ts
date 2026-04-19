import { beforeEach, describe, expect, it, vi } from 'vitest';

const loadExtensionSettingsMock = vi.hoisted(() => vi.fn());
const collectSelectionMock = vi.hoisted(() => vi.fn());
const renderOverlayMock = vi.hoisted(() => vi.fn());
const cropSelectionImageMock = vi.hoisted(() => vi.fn());

vi.mock('../../../src/shared/storage/settingsStorage', () => ({
  loadExtensionSettings: loadExtensionSettingsMock,
}));

vi.mock('../../../src/background/gateways/tabMessagingGateway', () => ({
  collectSelection: collectSelectionMock,
  renderOverlay: renderOverlayMock,
}));

vi.mock('../../../src/background/services/cropSelectionImage', () => ({
  cropSelectionImage: cropSelectionImageMock,
}));

import {
  clearAnalysisSession,
  getAnalysisSession,
  setAnalysisSession,
} from '../../../src/background/services/analysisSessionStore';
import {
  appendLiveSelectionSessionItem,
  appendSelectionSessionItem,
  removeSelectionSessionItem,
  toggleSelectionSessionItemImage,
} from '../../../src/background/usecases/updateSelectionSession';
import { getChromeMock } from '../../mocks/chrome';

describe('updateSelectionSession', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await clearAnalysisSession(7);
    loadExtensionSettingsMock.mockResolvedValue({
      apiBaseUrl: 'http://127.0.0.1:9000',
      defaultModel: 'gemini-2.5-flash',
      lastKnownModels: ['gemini-2.5-flash'],
    });
    cropSelectionImageMock.mockResolvedValue({
      imageDataUrl: 'data:image/webp;base64,crop',
      durationMs: 12.5,
    });
    collectSelectionMock.mockResolvedValue({
      ok: true,
      payload: {
        text: 'Selected text',
        rect: { left: 1, top: 2, width: 3, height: 4 },
        viewportWidth: 100,
        viewportHeight: 100,
        devicePixelRatio: 1,
        url: 'https://example.com',
        pageTitle: 'Example',
      },
    });
  });

  it('appends a text selection item with image-off by default and rerenders the overlay', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.tabs.captureVisibleTab as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      'data:image/png;base64,shot'
    );

    const item = await appendSelectionSessionItem(
      { id: 7, windowId: 3 } as chrome.tabs.Tab,
      {
        text: 'Selected text',
        rect: { left: 1, top: 2, width: 3, height: 4 },
        viewportWidth: 100,
        viewportHeight: 100,
        devicePixelRatio: 1,
        url: 'https://example.com',
        pageTitle: 'Example',
      },
      'text-selection'
    );

    expect(item.includeImage).toBe(false);
    expect((await getAnalysisSession(7))?.items).toHaveLength(1);
    expect(renderOverlayMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        sessionReady: true,
        sessionItems: [expect.objectContaining({ id: item.id })],
      })
    );
  });

  it('preserves article cache state when appending a new selection item', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.tabs.captureVisibleTab as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      'data:image/png;base64,shot'
    );
    await setAnalysisSession(7, {
      items: [],
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'gemini-2.5-flash',
        },
      ],
      lastAction: 'translation',
      lastModelName: 'gemini-2.5-flash',
      articleContext: {
        title: 'Example article',
        url: 'https://example.com/article',
        bodyText: 'Long article body',
        bodyHash: 'abc123def4567890',
        source: 'readability',
        textLength: 1800,
      },
      articleCacheState: {
        status: 'active',
        cacheName: 'cachedContents/article-1',
        modelName: 'gemini-2.5-flash',
        articleUrl: 'https://example.com/article',
        articleIdentity: 'example.com/article::example article',
        articleHash: 'abc123def4567890',
        tokenEstimate: 1400,
        tokenCount: 1500,
        ttlSeconds: 3600,
      },
      payloadTokenEstimate: 42,
      payloadTokenModelName: 'gemini-2.5-flash',
    });

    await appendSelectionSessionItem(
      { id: 7, windowId: 3 } as chrome.tabs.Tab,
      {
        text: 'Selected text',
        rect: { left: 1, top: 2, width: 3, height: 4 },
        viewportWidth: 100,
        viewportHeight: 100,
        devicePixelRatio: 1,
        url: 'https://example.com',
        pageTitle: 'Example',
      },
      'text-selection'
    );

    expect(await getAnalysisSession(7)).toEqual(
      expect.objectContaining({
        articleCacheState: expect.objectContaining({
          status: 'active',
          cacheName: 'cachedContents/article-1',
        }),
        payloadTokenModelName: 'gemini-2.5-flash',
      })
    );
  });

  it('appends the current live selection through the content capture gateway', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.tabs.captureVisibleTab as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      'data:image/png;base64,shot'
    );

    const item = await appendLiveSelectionSessionItem({
      id: 7,
      windowId: 3,
    } as chrome.tabs.Tab);

    expect(collectSelectionMock).toHaveBeenCalledWith(7, '', {
      liveOnly: true,
    });
    expect(item.selection.text).toBe('Selected text');
    expect(renderOverlayMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        sessionReady: true,
        sessionItems: [expect.objectContaining({ id: item.id })],
      })
    );
  });

  it('renders an explicit overlay error when no live selection exists for batch append', async () => {
    collectSelectionMock.mockResolvedValueOnce({
      ok: false,
      error: 'A live text selection is required. Select text on the page and try again.',
    });

    await expect(
      appendLiveSelectionSessionItem({ id: 7, windowId: 3 } as chrome.tabs.Tab)
    ).rejects.toThrow(
      'A live text selection is required. Select text on the page and try again.'
    );

    expect(renderOverlayMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        status: 'error',
        sessionReady: false,
        error: 'A live text selection is required. Select text on the page and try again.',
      })
    );
  });

  it('resolves the tab window id before capturing when the sender tab omits it', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.tabs.get as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 7,
      windowId: 3,
    });
    (chromeMock.tabs.captureVisibleTab as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      'data:image/png;base64,shot'
    );

    await appendSelectionSessionItem(
      { id: 7 } as chrome.tabs.Tab,
      {
        text: 'Selected text',
        rect: { left: 1, top: 2, width: 3, height: 4 },
        viewportWidth: 100,
        viewportHeight: 100,
        devicePixelRatio: 1,
        url: 'https://example.com',
        pageTitle: 'Example',
      },
      'text-selection'
    );

    expect(chromeMock.tabs.get).toHaveBeenCalledWith(7);
    expect(chromeMock.tabs.captureVisibleTab).toHaveBeenCalledWith(3, {
      format: 'png',
    });
  });

  it('removes a session item and rerenders the overlay with an empty batch', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.tabs.captureVisibleTab as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      'data:image/png;base64,shot'
    );

    const item = await appendSelectionSessionItem(
      { id: 7, windowId: 3 } as chrome.tabs.Tab,
      {
        text: 'Selected text',
        rect: { left: 1, top: 2, width: 3, height: 4 },
        viewportWidth: 100,
        viewportHeight: 100,
        devicePixelRatio: 1,
        url: 'https://example.com',
        pageTitle: 'Example',
      },
      'text-selection'
    );

    await removeSelectionSessionItem(7, item.id);

    expect(await getAnalysisSession(7)).toBeUndefined();
    expect(renderOverlayMock).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({
        sessionReady: false,
        sessionItems: [],
      })
    );
  });

  it('toggles image inclusion for an existing session item without recapturing', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.tabs.captureVisibleTab as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      'data:image/png;base64,shot'
    );

    const item = await appendSelectionSessionItem(
      { id: 7, windowId: 3 } as chrome.tabs.Tab,
      {
        text: 'Selected text',
        rect: { left: 1, top: 2, width: 3, height: 4 },
        viewportWidth: 100,
        viewportHeight: 100,
        devicePixelRatio: 1,
        url: 'https://example.com',
        pageTitle: 'Example',
      },
      'text-selection'
    );

    await toggleSelectionSessionItemImage(7, item.id, true);

    expect((await getAnalysisSession(7))?.items[0].includeImage).toBe(true);
    expect(chromeMock.tabs.captureVisibleTab).toHaveBeenCalledTimes(1);
    expect(renderOverlayMock).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({
        sessionItems: [expect.objectContaining({ id: item.id, includeImage: true })],
      })
    );
  });
});