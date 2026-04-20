import { describe, expect, it, vi } from 'vitest';

import { EXTENSION_SETTINGS_STORAGE_KEY } from '../../../src/shared/config/phase0';
import { renderPopup } from '../../../src/popup/ui/renderPopup';
import { getChromeMock } from '../../mocks/chrome';

function createJsonResponse(payload: unknown, status: number = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(payload),
    text: vi.fn().mockResolvedValue(JSON.stringify(payload)),
  } as unknown as Response;
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

// popup が設定編集と接続確認に責務を絞っていることを固定する suite。
describe('renderPopup', () => {
  it('renders markdown export checkboxes with the documented default states', async () => {
    document.body.innerHTML = '<div id="app"></div>';

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(createJsonResponse({ status: 'ok' }))
      .mockResolvedValueOnce(
        createJsonResponse({
          ok: true,
          models: [],
          source: 'storage_fallback',
          availability: 'mock',
          detail: null,
          degraded_reason: 'mock-response',
        })
      );
    vi.stubGlobal('fetch', fetchMock);

    await renderPopup(document);
    await settle();

    expect(
      (
        document.querySelector(
          '[data-role="markdown-export-section"]'
        ) as HTMLDetailsElement
      ).open
    ).toBe(false);
    expect(document.body.textContent).toContain(
      'Default: explanation + selected text'
    );

    expect(
      (
        document.querySelector(
          '[data-role="include-explanation"]'
        ) as HTMLInputElement
      ).checked
    ).toBe(true);
    expect(
      (
        document.querySelector(
          '[data-role="include-selections"]'
        ) as HTMLInputElement
      ).checked
    ).toBe(true);
    expect(
      (
        document.querySelector(
          '[data-role="include-raw-response"]'
        ) as HTMLInputElement
      ).checked
    ).toBe(false);
    expect(
      (
        document.querySelector(
          '[data-role="include-article-metadata"]'
        ) as HTMLInputElement
      ).checked
    ).toBe(false);
    expect(
      (
        document.querySelector(
          '[data-role="include-usage-metrics"]'
        ) as HTMLInputElement
      ).checked
    ).toBe(false);
    expect(
      (
        document.querySelector(
          '[data-role="include-yaml-frontmatter"]'
        ) as HTMLInputElement
      ).checked
    ).toBe(false);
  });

  it('loads saved settings and renders live popup status', async () => {
    document.body.innerHTML = '<div id="app"></div>';
    const chromeMock = getChromeMock();
    chromeMock.storage.local.set(
      {
        [EXTENSION_SETTINGS_STORAGE_KEY]: {
          apiBaseUrl: 'http://127.0.0.1:8001',
          defaultModel: 'gemini-2.5-pro',
          lastKnownModels: ['gemini-2.5-pro'],
          markdownExport: {
            includeExplanation: false,
            includeSelections: true,
            includeRawResponse: true,
            includeArticleMetadata: true,
            includeUsageMetrics: false,
            includeYamlFrontmatter: true,
          },
        },
      },
      () => undefined
    );

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

    await renderPopup(document);
    await settle();

    expect(
      document.querySelector('[data-role="status-badge"]')?.textContent
    ).toContain('Reachable');
    expect(
      (document.querySelector('#api-base-url') as HTMLInputElement).value
    ).toBe('http://127.0.0.1:8001');
    expect(
      (document.querySelector('#default-model') as HTMLInputElement).value
    ).toBe('gemini-2.5-pro');
    expect(
      (
        document.querySelector(
          '[data-role="include-explanation"]'
        ) as HTMLInputElement
      ).checked
    ).toBe(false);
    expect(
      (
        document.querySelector(
          '[data-role="include-raw-response"]'
        ) as HTMLInputElement
      ).checked
    ).toBe(true);
    expect(document.querySelectorAll('#model-options option')).toHaveLength(1);
    expect(chromeMock.storage.local.set).toHaveBeenCalledWith(
      {
        [EXTENSION_SETTINGS_STORAGE_KEY]: {
          apiBaseUrl: 'http://127.0.0.1:8001',
          defaultModel: 'gemini-2.5-pro',
          lastKnownModels: ['gemini-2.5-flash'],
          markdownExport: {
            includeExplanation: false,
            includeSelections: true,
            includeRawResponse: true,
            includeArticleMetadata: true,
            includeUsageMetrics: false,
            includeYamlFrontmatter: true,
          },
        },
      },
      expect.any(Function)
    );
  });

  it('saves popup settings with normalized values', async () => {
    document.body.innerHTML = '<div id="app"></div>';
    const chromeMock = getChromeMock();

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
      )
      .mockResolvedValueOnce(createJsonResponse({ status: 'ok' }))
      .mockResolvedValueOnce(
        createJsonResponse({
          ok: true,
          models: [
            {
              model_id: 'gemini-2.5-pro',
              display_name: 'Gemini 2.5 Pro',
            },
          ],
          source: 'live',
          availability: 'live',
          detail: null,
          degraded_reason: null,
        })
      );
    vi.stubGlobal('fetch', fetchMock);

    await renderPopup(document);
    await settle();

    const apiInput = document.querySelector(
      '#api-base-url'
    ) as HTMLInputElement;
    const defaultModelInput = document.querySelector(
      '#default-model'
    ) as HTMLInputElement;
    const form = document.querySelector(
      '[data-role="settings-form"]'
    ) as HTMLFormElement;
    const includeExplanationInput = document.querySelector(
      '[data-role="include-explanation"]'
    ) as HTMLInputElement;
    const includeSelectionsInput = document.querySelector(
      '[data-role="include-selections"]'
    ) as HTMLInputElement;
    const includeRawResponseInput = document.querySelector(
      '[data-role="include-raw-response"]'
    ) as HTMLInputElement;
    const includeArticleMetadataInput = document.querySelector(
      '[data-role="include-article-metadata"]'
    ) as HTMLInputElement;
    const includeUsageMetricsInput = document.querySelector(
      '[data-role="include-usage-metrics"]'
    ) as HTMLInputElement;
    const includeYamlFrontmatterInput = document.querySelector(
      '[data-role="include-yaml-frontmatter"]'
    ) as HTMLInputElement;

    apiInput.value = 'http://localhost:9001/';
    defaultModelInput.value = ' gemini-2.5-pro ';
    includeExplanationInput.checked = false;
    includeSelectionsInput.checked = true;
    includeRawResponseInput.checked = true;
    includeArticleMetadataInput.checked = true;
    includeUsageMetricsInput.checked = true;
    includeYamlFrontmatterInput.checked = false;
    form.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true })
    );
    await settle();

    expect(chromeMock.storage.local.set).toHaveBeenCalledWith(
      {
        [EXTENSION_SETTINGS_STORAGE_KEY]: {
          apiBaseUrl: 'http://localhost:9001',
          defaultModel: 'gemini-2.5-pro',
          lastKnownModels: ['gemini-2.5-flash'],
          markdownExport: {
            includeExplanation: false,
            includeSelections: true,
            includeRawResponse: true,
            includeArticleMetadata: true,
            includeUsageMetrics: true,
            includeYamlFrontmatter: false,
          },
        },
      },
      expect.any(Function)
    );
    expect(
      document.querySelector('[data-role="message-line"]')?.textContent
    ).toContain('Settings saved.');
    expect(document.body.textContent).toContain(
      'Filename rule is page title plus timestamp.'
    );
  });

  it('opens the overlay shortcut on the active tab', async () => {
    document.body.innerHTML = '<div id="app"></div>';
    const chromeMock = getChromeMock();
    chromeMock.runtime.sendMessage.mockResolvedValue({ ok: true });

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(createJsonResponse({ status: 'ok' }))
      .mockResolvedValueOnce(
        createJsonResponse({
          ok: true,
          models: [
            {
              model_id: 'gemini-2.5-pro',
              display_name: 'Gemini 2.5 Pro',
            },
          ],
          source: 'live',
          availability: 'live',
          detail: null,
          degraded_reason: null,
        })
      );
    vi.stubGlobal('fetch', fetchMock);

    await renderPopup(document);
    await settle();

    const defaultModelInput = document.querySelector(
      '#default-model'
    ) as HTMLInputElement;
    defaultModelInput.value = 'gemini-2.5-pro';

    (
      document.querySelector(
        '[data-role="open-overlay-button"]'
      ) as HTMLButtonElement
    ).click();
    await settle();

    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: 'phase3.openOverlay',
    });
  });
});
