import { beforeEach, describe, expect, it, vi } from 'vitest';

const loadExtensionSettingsMock = vi.hoisted(() => vi.fn());
const renderOverlayMock = vi.hoisted(() => vi.fn());
const cropSelectionImageMock = vi.hoisted(() => vi.fn());

vi.mock('../../../src/shared/storage/settingsStorage', () => ({
  loadExtensionSettings: loadExtensionSettingsMock,
}));

vi.mock('../../../src/background/gateways/tabMessagingGateway', () => ({
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
  appendSelectionSessionItem,
  removeSelectionSessionItem,
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
});