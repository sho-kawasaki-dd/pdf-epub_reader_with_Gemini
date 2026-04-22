import { beforeEach, describe, expect, it, vi } from 'vitest';

const loadExtensionSettingsMock = vi.hoisted(() => vi.fn());
const collectArticleContextMock = vi.hoisted(() => vi.fn());
const renderOverlayMock = vi.hoisted(() => vi.fn());
const mergeCollectedArticleContextMock = vi.hoisted(() => vi.fn());
const syncArticleCacheStateMock = vi.hoisted(() => vi.fn());

vi.mock('../../../src/shared/storage/settingsStorage', () => ({
  loadExtensionSettings: loadExtensionSettingsMock,
}));

vi.mock('../../../src/background/gateways/tabMessagingGateway', () => ({
  collectArticleContext: collectArticleContextMock,
  renderOverlay: renderOverlayMock,
}));

vi.mock('../../../src/background/services/articleCacheService', () => ({
  mergeCollectedArticleContext: mergeCollectedArticleContextMock,
  syncArticleCacheState: syncArticleCacheStateMock,
}));

import {
  clearAnalysisSession,
  setAnalysisSession,
} from '../../../src/background/services/analysisSessionStore';
import { openOverlaySession } from '../../../src/background/usecases/openOverlaySession';

describe('openOverlaySession', () => {
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
    });
    collectArticleContextMock.mockResolvedValue({
      ok: true,
      payload: {
        title: 'Example article',
        url: 'https://example.com/article',
        bodyText: 'Long article context',
        bodyHash: 'abc123def4567890',
        source: 'readability',
        textLength: 2048,
      },
    });
    mergeCollectedArticleContextMock.mockImplementation((session, result) => ({
      ...session,
      articleContext: result.ok ? result.payload : session.articleContext,
      articleContextError: result.ok ? undefined : result.error,
    }));
    syncArticleCacheStateMock.mockImplementation(async (session) => session);
  });

  it('renders the cached batch session when one exists', async () => {
    await setAnalysisSession(7, {
      items: [
        {
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
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
          cropDurationMs: 2.5,
        },
      ],
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'Gemini 2.5 Flash',
        },
      ],
      lastAction: 'translation_with_explanation',
      lastModelName: 'gemini-2.5-pro',
      lastCustomPrompt: 'Summarize this',
    });

    await openOverlaySession(7);

    expect(loadExtensionSettingsMock).toHaveBeenCalledTimes(1);
    expect(renderOverlayMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        sessionReady: true,
        launcherOnly: false,
        preserveDrafts: true,
        action: 'translation_with_explanation',
        selectedText: 'Selected text',
      })
    );
  });

  it('renders the full overlay when only article cache state exists', async () => {
    syncArticleCacheStateMock.mockImplementationOnce(async (session) => ({
      ...session,
      articleCacheState: {
        status: 'active',
        cacheName: 'cachedContents/article-1',
        modelName: 'gemini-2.5-flash',
        notice: 'Article cache created automatically for the current tab.',
      },
    }));
    await setAnalysisSession(7, {
      items: [],
      modelOptions: [],
      lastAction: 'translation',
    });

    await openOverlaySession(7);

    expect(renderOverlayMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        launcherOnly: false,
        sessionReady: false,
        articleCacheState: expect.objectContaining({
          status: 'active',
        }),
      })
    );
  });

  it('renders a launcher-only overlay when no cached session exists', async () => {
    await openOverlaySession(7);

    expect(loadExtensionSettingsMock).toHaveBeenCalledTimes(1);
    expect(renderOverlayMock).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        sessionReady: false,
        launcherOnly: true,
        preserveDrafts: true,
        modelName: 'gemini-2.5-flash',
      })
    );
  });

  it('passes allowAutoCreate=false to syncArticleCacheState when batch is empty', async () => {
    await setAnalysisSession(7, {
      items: [],
      modelOptions: [
        { modelId: 'gemini-2.5-flash', displayName: 'Gemini 2.5 Flash' },
      ],
      lastAction: 'translation',
      articleContext: {
        title: 'Article',
        url: 'https://example.com/article',
        bodyText: 'body text',
        bodyHash: 'hash123',
        source: 'readability',
        textLength: 100,
      },
    });

    await openOverlaySession(7);

    expect(syncArticleCacheStateMock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ allowAutoCreate: false })
    );
  });

  it('passes allowAutoCreate=true to syncArticleCacheState when batch has items', async () => {
    await setAnalysisSession(7, {
      items: [
        {
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
          includeImage: false,
        },
      ],
      modelOptions: [
        { modelId: 'gemini-2.5-flash', displayName: 'Gemini 2.5 Flash' },
      ],
      lastAction: 'translation',
    });

    await openOverlaySession(7);

    expect(syncArticleCacheStateMock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ allowAutoCreate: true })
    );
  });

  it('disables auto-create when popup settings turn article cache creation off', async () => {
    loadExtensionSettingsMock.mockResolvedValueOnce({
      apiBaseUrl: 'http://127.0.0.1:9000',
      defaultModel: 'gemini-2.5-flash',
      lastKnownModels: ['gemini-2.5-flash'],
      articleCache: {
        enableAutoCreate: false,
      },
    });
    await setAnalysisSession(7, {
      items: [
        {
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
          includeImage: false,
        },
      ],
      modelOptions: [
        { modelId: 'gemini-2.5-flash', displayName: 'Gemini 2.5 Flash' },
      ],
      lastAction: 'translation',
    });

    await openOverlaySession(7);

    expect(syncArticleCacheStateMock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        allowAutoCreate: false,
        autoCreateDisabledBySetting: true,
      })
    );
  });
});
