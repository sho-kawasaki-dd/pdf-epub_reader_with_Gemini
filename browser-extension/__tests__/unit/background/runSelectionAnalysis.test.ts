import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getChromeMock } from '../../mocks/chrome';

const collectSelectionMock = vi.hoisted(() => vi.fn());
const renderOverlayMock = vi.hoisted(() => vi.fn());
const sendAnalyzeTranslateRequestMock = vi.hoisted(() => vi.fn());
const cropSelectionImageMock = vi.hoisted(() => vi.fn());
const loadExtensionSettingsMock = vi.hoisted(() => vi.fn());

vi.mock('../../../src/background/gateways/tabMessagingGateway', () => ({
  collectSelection: collectSelectionMock,
  renderOverlay: renderOverlayMock,
}));

vi.mock('../../../src/background/gateways/localApiGateway', () => ({
  sendAnalyzeTranslateRequest: sendAnalyzeTranslateRequestMock,
}));

vi.mock('../../../src/background/services/cropSelectionImage', () => ({
  cropSelectionImage: cropSelectionImageMock,
}));

vi.mock('../../../src/shared/storage/settingsStorage', () => ({
  loadExtensionSettings: loadExtensionSettingsMock,
}));

import { clearAnalysisSession } from '../../../src/background/services/analysisSessionStore';
import { runPhase0TranslationTest } from '../../../src/background/usecases/runPhase0TranslationTest';
import { runSelectionAnalysis } from '../../../src/background/usecases/runSelectionAnalysis';

// selection capture、crop、API 呼び出し、overlay 更新の orchestration を固定する suite。
describe('runSelectionAnalysis', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearAnalysisSession(7);
    loadExtensionSettingsMock.mockResolvedValue({
      apiBaseUrl: 'http://127.0.0.1:9000',
      defaultModel: 'gemini-2.5-flash',
      lastKnownModels: ['gemini-2.5-flash'],
    });
  });

  it('renders loading then success overlay using stored settings', async () => {
    const chromeMock = getChromeMock();
    chromeMock.tabs.captureVisibleTab.mockResolvedValue(
      'data:image/png;base64,shot'
    );
    collectSelectionMock.mockResolvedValue({
      ok: true,
      payload: {
        text: 'selection from content script',
        rect: { left: 10, top: 20, width: 30, height: 40 },
        viewportWidth: 1440,
        viewportHeight: 900,
        devicePixelRatio: 2,
        url: 'https://example.com/article',
        pageTitle: 'Example page',
      },
    });
    cropSelectionImageMock.mockResolvedValue({
      imageDataUrl: 'data:image/webp;base64,crop',
      durationMs: 12.5,
    });
    sendAnalyzeTranslateRequestMock.mockResolvedValue({
      ok: true,
      mode: 'translation',
      translated_text: '翻訳結果',
      explanation: null,
      raw_response: '翻訳結果',
      used_mock: false,
      availability: 'live',
      degraded_reason: null,
      image_count: 1,
    });

    await runSelectionAnalysis(
      { id: 7, windowId: 9 } as chrome.tabs.Tab,
      '  fallback text  '
    );

    expect(loadExtensionSettingsMock).toHaveBeenCalledTimes(1);
    expect(renderOverlayMock).toHaveBeenNthCalledWith(
      1,
      7,
      expect.objectContaining({
        status: 'loading',
        action: 'translation',
        modelName: 'gemini-2.5-flash',
        modelOptions: [
          {
            modelId: 'gemini-2.5-flash',
            displayName: 'gemini-2.5-flash',
          },
        ],
        customPrompt: undefined,
        sessionReady: false,
        selectedText: '  fallback text  ',
      })
    );
    expect(collectSelectionMock).toHaveBeenCalledWith(7, '  fallback text  ');
    expect(chromeMock.tabs.captureVisibleTab).toHaveBeenCalledWith(9, {
      format: 'png',
    });
    expect(cropSelectionImageMock).toHaveBeenCalledWith(
      'data:image/png;base64,shot',
      expect.objectContaining({ text: 'fallback text' })
    );
    expect(sendAnalyzeTranslateRequestMock).toHaveBeenCalledWith(
      expect.objectContaining({ text: 'fallback text' }),
      'data:image/webp;base64,crop',
      {
        action: 'translation',
        apiBaseUrl: 'http://127.0.0.1:9000',
        modelName: 'gemini-2.5-flash',
        customPrompt: undefined,
      }
    );
    expect(renderOverlayMock).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({
        status: 'success',
        action: 'translation',
        modelName: 'gemini-2.5-flash',
        modelOptions: [
          {
            modelId: 'gemini-2.5-flash',
            displayName: 'gemini-2.5-flash',
          },
        ],
        sessionReady: true,
        selectedText: 'fallback text',
        translatedText: '翻訳結果',
        previewImageUrl: 'data:image/webp;base64,crop',
        imageCount: 1,
        timingMs: 12.5,
      })
    );
  });

  it('accepts explicit action overrides for custom prompt requests', async () => {
    const chromeMock = getChromeMock();
    chromeMock.tabs.captureVisibleTab.mockResolvedValue(
      'data:image/png;base64,shot'
    );
    collectSelectionMock.mockResolvedValue({
      ok: true,
      payload: {
        text: 'selection from content script',
        rect: { left: 10, top: 20, width: 30, height: 40 },
        viewportWidth: 1440,
        viewportHeight: 900,
        devicePixelRatio: 2,
        url: 'https://example.com/article',
        pageTitle: 'Example page',
      },
    });
    cropSelectionImageMock.mockResolvedValue({
      imageDataUrl: 'data:image/webp;base64,crop',
      durationMs: 12.5,
    });
    sendAnalyzeTranslateRequestMock.mockResolvedValue({
      ok: true,
      mode: 'custom_prompt',
      translated_text: 'custom answer',
      explanation: null,
      raw_response: 'custom answer',
      used_mock: true,
      availability: 'mock',
      degraded_reason: 'mock-response',
      image_count: 1,
    });

    await runSelectionAnalysis(
      { id: 7, windowId: 9 } as chrome.tabs.Tab,
      'fallback',
      {
        action: 'custom_prompt',
        apiBaseUrl: 'http://localhost:9010',
        modelName: 'gemini-2.5-pro',
        customPrompt: 'Summarize this',
      }
    );

    expect(sendAnalyzeTranslateRequestMock).toHaveBeenCalledWith(
      expect.objectContaining({ text: 'fallback' }),
      'data:image/webp;base64,crop',
      {
        action: 'custom_prompt',
        apiBaseUrl: 'http://localhost:9010',
        modelName: 'gemini-2.5-pro',
        customPrompt: 'Summarize this',
      }
    );
    expect(renderOverlayMock).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({
        status: 'success',
        action: 'custom_prompt',
        modelName: 'gemini-2.5-pro',
        modelOptions: [
          {
            modelId: 'gemini-2.5-flash',
            displayName: 'gemini-2.5-flash',
          },
        ],
        customPrompt: 'Summarize this',
        sessionReady: true,
        usedMock: true,
        availability: 'mock',
        degradedReason: 'mock-response',
      })
    );
  });

  it('renders an error overlay when selection payload is unavailable', async () => {
    const chromeMock = getChromeMock();
    collectSelectionMock.mockResolvedValue({
      ok: false,
      error: '選択テキストを取得できませんでした。',
    });

    await runSelectionAnalysis(
      { id: 7, windowId: 9 } as chrome.tabs.Tab,
      'fallback',
      {
        action: 'translation_with_explanation',
      }
    );

    expect(chromeMock.tabs.captureVisibleTab).not.toHaveBeenCalled();
    expect(renderOverlayMock).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({
        status: 'error',
        action: 'translation_with_explanation',
        modelName: 'gemini-2.5-flash',
        modelOptions: [
          {
            modelId: 'gemini-2.5-flash',
            displayName: 'gemini-2.5-flash',
          },
        ],
        customPrompt: undefined,
        sessionReady: false,
        selectedText: 'fallback',
        error: '選択テキストを取得できませんでした。',
      })
    );
  });

  it('reuses the cached session for overlay-triggered reruns', async () => {
    const chromeMock = getChromeMock();
    chromeMock.tabs.captureVisibleTab.mockResolvedValue(
      'data:image/png;base64,shot'
    );
    collectSelectionMock.mockResolvedValue({
      ok: true,
      payload: {
        text: 'selection from content script',
        rect: { left: 10, top: 20, width: 30, height: 40 },
        viewportWidth: 1440,
        viewportHeight: 900,
        devicePixelRatio: 2,
        url: 'https://example.com/article',
        pageTitle: 'Example page',
      },
    });
    cropSelectionImageMock.mockResolvedValue({
      imageDataUrl: 'data:image/webp;base64,crop',
      durationMs: 12.5,
    });
    sendAnalyzeTranslateRequestMock
      .mockResolvedValueOnce({
        ok: true,
        mode: 'translation',
        translated_text: '翻訳結果',
        explanation: null,
        raw_response: '翻訳結果',
        used_mock: false,
        availability: 'live',
        degraded_reason: null,
        image_count: 1,
      })
      .mockResolvedValueOnce({
        ok: true,
        mode: 'translation_with_explanation',
        translated_text: '翻訳結果',
        explanation: '補足説明',
        raw_response: '翻訳結果\n\n---\n\n補足説明',
        used_mock: false,
        availability: 'live',
        degraded_reason: null,
        image_count: 1,
      });

    await runSelectionAnalysis(
      { id: 7, windowId: 9 } as chrome.tabs.Tab,
      'fallback'
    );

    await runSelectionAnalysis({ id: 7, windowId: 9 } as chrome.tabs.Tab, '', {
      action: 'translation_with_explanation',
      reuseCachedSession: true,
    });

    expect(collectSelectionMock).toHaveBeenCalledTimes(1);
    expect(chromeMock.tabs.captureVisibleTab).toHaveBeenCalledTimes(1);
    expect(cropSelectionImageMock).toHaveBeenCalledTimes(1);
    expect(sendAnalyzeTranslateRequestMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ text: 'fallback' }),
      'data:image/webp;base64,crop',
      expect.objectContaining({ action: 'translation_with_explanation' })
    );
  });

  it('keeps the phase0 wrapper delegating to translation action', async () => {
    const chromeMock = getChromeMock();
    chromeMock.tabs.captureVisibleTab.mockResolvedValue(
      'data:image/png;base64,shot'
    );
    collectSelectionMock.mockResolvedValue({
      ok: true,
      payload: {
        text: 'selection from content script',
        rect: { left: 10, top: 20, width: 30, height: 40 },
        viewportWidth: 1440,
        viewportHeight: 900,
        devicePixelRatio: 2,
        url: 'https://example.com/article',
        pageTitle: 'Example page',
      },
    });
    cropSelectionImageMock.mockResolvedValue({
      imageDataUrl: 'data:image/webp;base64,crop',
      durationMs: 12.5,
    });
    sendAnalyzeTranslateRequestMock.mockResolvedValue({
      ok: true,
      mode: 'translation',
      translated_text: '翻訳結果',
      explanation: null,
      raw_response: '翻訳結果',
      used_mock: false,
      availability: 'live',
      degraded_reason: null,
      image_count: 1,
    });

    await runPhase0TranslationTest(
      { id: 7, windowId: 9 } as chrome.tabs.Tab,
      'fallback'
    );

    expect(sendAnalyzeTranslateRequestMock).toHaveBeenCalledWith(
      expect.any(Object),
      'data:image/webp;base64,crop',
      expect.objectContaining({ action: 'translation' })
    );
  });
});
