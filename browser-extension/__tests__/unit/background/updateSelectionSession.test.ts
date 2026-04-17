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
} from '../../../src/background/services/analysisSessionStore';
import {
  appendLiveSelectionSessionItem,
  appendSelectionSessionItem,
  removeSelectionSessionItem,
  toggleSelectionSessionItemImage,
} from '../../../src/background/usecases/updateSelectionSession';
import { getChromeMock } from '../../mocks/chrome';

describe('updateSelectionSession', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearAnalysisSession(7);
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
    expect(getAnalysisSession(7)?.items).toHaveLength(1);
    expect(renderOverlayMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        sessionReady: true,
        sessionItems: [expect.objectContaining({ id: item.id })],
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

    expect(getAnalysisSession(7)).toBeUndefined();
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

    expect(getAnalysisSession(7)?.items[0].includeImage).toBe(true);
    expect(chromeMock.tabs.captureVisibleTab).toHaveBeenCalledTimes(1);
    expect(renderOverlayMock).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({
        sessionItems: [expect.objectContaining({ id: item.id, includeImage: true })],
      })
    );
  });
});