import { describe, expect, it, vi } from 'vitest';

import {
  fetchPopupBootstrap,
  sendAnalyzeTranslateRequest,
} from '../../../src/shared/gateways/localApiGateway';

function createJsonResponse(payload: unknown, status: number = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(payload),
    text: vi.fn().mockResolvedValue(JSON.stringify(payload)),
  } as unknown as Response;
}

// gateway が HTTP payload と degraded fallback をどう正規化するかを固定する suite。
describe('localApiGateway', () => {
  it('sends batch analyze requests with numbered text, sparse images, and ordered metadata', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      createJsonResponse({
        ok: true,
        mode: 'custom_prompt',
        translated_text: 'custom answer',
        explanation: null,
        raw_response: 'custom answer',
        used_mock: false,
        image_count: 1,
        availability: 'live',
        degraded_reason: null,
        selection_metadata: {
          url: 'https://example.com/article',
        },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await sendAnalyzeTranslateRequest(
      [
        {
          id: 'selection-1',
          source: 'text-selection',
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview-1',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 1280,
            viewportHeight: 720,
            devicePixelRatio: 2,
            url: 'https://example.com/article',
            pageTitle: 'Example page',
          },
        },
        {
          id: 'selection-2',
          source: 'free-rectangle',
          includeImage: true,
          previewImageUrl: 'data:image/webp;base64,preview-2',
          selection: {
            text: '',
            rect: { left: 11, top: 12, width: 13, height: 14 },
            viewportWidth: 1280,
            viewportHeight: 720,
            devicePixelRatio: 2,
            url: 'https://example.com/article',
            pageTitle: 'Example page',
          },
        },
        {
          id: 'selection-3',
          source: 'text-selection',
          includeImage: true,
          previewImageUrl: 'data:image/webp;base64,preview-3',
          selection: {
            text: 'Second paragraph',
            rect: { left: 21, top: 22, width: 23, height: 24 },
            viewportWidth: 1280,
            viewportHeight: 720,
            devicePixelRatio: 2,
            url: 'https://example.com/article',
            pageTitle: 'Example page',
          },
        },
      ],
      {
        action: 'custom_prompt',
        apiBaseUrl: 'http://127.0.0.1:9000',
        modelName: 'gemini-2.5-pro',
        customPrompt: 'Summarize this',
      }
    );

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:9000/analyze/translate',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toMatchObject(
      {
        text: '1. Selected paragraph\n\n2. Second paragraph',
        mode: 'custom_prompt',
        model_name: 'gemini-2.5-pro',
        custom_prompt: 'Summarize this',
        images: [
          'data:image/webp;base64,preview-2',
          'data:image/webp;base64,preview-3',
        ],
        selection_metadata: {
          url: 'https://example.com/article',
          page_title: 'Example page',
          items: [
            {
              id: 'selection-1',
              order: 0,
              source: 'text-selection',
              text: 'Selected paragraph',
              include_image: false,
              image_index: null,
            },
            {
              id: 'selection-2',
              order: 1,
              source: 'free-rectangle',
              text: '',
              include_image: true,
              image_index: 0,
            },
            {
              id: 'selection-3',
              order: 2,
              source: 'text-selection',
              text: 'Second paragraph',
              include_image: true,
              image_index: 1,
            },
          ],
        },
      }
    );
    expect(result).toMatchObject({
      mode: 'custom_prompt',
      translated_text: 'custom answer',
      availability: 'live',
    });
  });

  it('returns reachable popup bootstrap status for live health and model responses', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(createJsonResponse({ status: 'ok' }))
      .mockResolvedValueOnce(
        createJsonResponse({
          ok: true,
          models: [
            {
              model_id: 'gemini-2.5-flash',
              display_name: 'Gemini 2.5 Flash',
            },
          ],
          source: 'live',
          availability: 'live',
          detail: null,
          degraded_reason: null,
        })
      );
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchPopupBootstrap('http://127.0.0.1:8000');

    expect(result.status.connectionStatus).toBe('reachable');
    expect(result.status.modelSource).toBe('live');
    expect(result.models).toEqual([
      {
        modelId: 'gemini-2.5-flash',
        displayName: 'Gemini 2.5 Flash',
      },
    ]);
  });

  it('falls back to mock-mode popup status when model fetch fails after health succeeds', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(createJsonResponse({ status: 'ok' }))
      .mockRejectedValueOnce(new Error('model endpoint unavailable'));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchPopupBootstrap('http://127.0.0.1:8000');

    expect(result.status.connectionStatus).toBe('mock-mode');
    expect(result.status.modelSource).toBe('storage_fallback');
    expect(result.status.detail).toContain('model endpoint unavailable');
    expect(result.models).toEqual([]);
  });
});
