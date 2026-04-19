import {
  chromium,
  expect,
  test,
  type BrowserContext,
  type Locator,
  type Page,
  type Worker,
} from '@playwright/test';
import { promises as fs } from 'node:fs';
import http, { type Server } from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const extensionPath = path.resolve(__dirname, '..', '..', 'dist');
const fixturePath = path.resolve(__dirname, 'fixtures', 'selection-page.html');
const expectedSelectionText =
  'Gem Read validates browser selection smoke tests with a stable paragraph so the extension can capture text coordinates and render its overlay deterministically.';
const secondSelectionText =
  'A second paragraph lets Gem Read exercise ordered multi-selection batches without relying on browser-native multi-range selection support.';

type SelectionResponse = {
  ok: boolean;
  payload?: {
    text: string;
    rect: {
      left: number;
      top: number;
      width: number;
      height: number;
    };
    viewportWidth: number;
    viewportHeight: number;
    devicePixelRatio: number;
    url: string;
    pageTitle: string;
  };
  error?: string;
};

type AnalyzeRequestPayload = {
  text: string;
  mode: string;
  model_name?: string;
  custom_prompt?: string;
  images?: string[];
  selection_metadata?: {
    items?: Array<{
      id?: string;
      order?: number;
      source?: string;
      text?: string;
      include_image?: boolean;
      image_index?: number | null;
    }>;
  } | null;
};

type TokenCountRequestPayload = {
  text: string;
  model_name?: string;
};

type CreateCacheRequestPayload = {
  full_text: string;
  model_name?: string;
  display_name?: string;
};

type StubCacheState = {
  cacheName: string;
  displayName: string;
  modelName: string;
  tokenCount: number;
  ttlSeconds: number;
  expireTime: string;
};

type SeededSessionItem = {
  id: string;
  source: 'text-selection' | 'free-rectangle';
  selection: {
    text: string;
    rect: {
      left: number;
      top: number;
      width: number;
      height: number;
    };
    viewportWidth: number;
    viewportHeight: number;
    devicePixelRatio: number;
    url: string;
    pageTitle: string;
  };
  includeImage: boolean;
  previewImageUrl?: string;
  cropDurationMs?: number;
};

type StubApiState = {
  healthChecks: number;
  modelRequests: number;
  analyzeRequests: AnalyzeRequestPayload[];
  tokenRequests: TokenCountRequestPayload[];
  cacheCreateRequests: CreateCacheRequestPayload[];
  cacheDeleteRequests: string[];
  activeCache?: StubCacheState;
};

function estimateTokenCount(text: string): number {
  const normalized = text.trim();
  if (normalized.length === 0) {
    return 0;
  }

  return Math.max(12, Math.ceil(normalized.length / 4));
}

async function startFixtureServer(): Promise<{ server: Server; url: string }> {
  const html = await fs.readFile(fixturePath, 'utf8');

  return new Promise((resolve, reject) => {
    const server = http.createServer((_request, response) => {
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.end(html);
    });

    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        reject(new Error('Failed to bind fixture server.'));
        return;
      }

      resolve({
        server,
        url: `http://127.0.0.1:${address.port}`,
      });
    });
  });
}

async function startStubApiServer(): Promise<{
  server: Server;
  url: string;
  state: StubApiState;
}> {
  const state: StubApiState = {
    healthChecks: 0,
    modelRequests: 0,
    analyzeRequests: [],
    tokenRequests: [],
    cacheCreateRequests: [],
    cacheDeleteRequests: [],
  };

  return new Promise((resolve, reject) => {
    const server = http.createServer(async (request, response) => {
      if (!request.url) {
        response.writeHead(404).end();
        return;
      }

      if (request.method === 'GET' && request.url === '/health') {
        state.healthChecks += 1;
        response.writeHead(200, {
          'Content-Type': 'application/json; charset=utf-8',
        });
        response.end(JSON.stringify({ status: 'ok' }));
        return;
      }

      if (request.method === 'GET' && request.url === '/models') {
        state.modelRequests += 1;
        response.writeHead(200, {
          'Content-Type': 'application/json; charset=utf-8',
        });
        response.end(
          JSON.stringify({
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
        return;
      }

      if (request.method === 'POST' && request.url === '/analyze/translate') {
        let body = '';
        request.setEncoding('utf8');
        request.on('data', (chunk) => {
          body += chunk;
        });
        request.on('end', () => {
          const payload = JSON.parse(body) as AnalyzeRequestPayload;
          state.analyzeRequests.push(payload);
          const translatedText =
            payload.mode === 'custom_prompt'
              ? `[custom] ${payload.custom_prompt ?? '(missing prompt)'}`
              : payload.text.trim().length > 0
                ? `[ja] ${payload.text}`
                : '[ja] [image-only]';
          const explanation =
            payload.mode === 'translation_with_explanation'
              ? 'Stub explanation generated by the local API smoke server.'
              : null;
          const rawResponse = explanation
            ? `${translatedText}\n\n---\n\n${explanation}`
            : translatedText;
          const promptTokenCount = estimateTokenCount(payload.text);
          const cachedContentTokenCount = state.activeCache?.tokenCount ?? 0;
          const candidatesTokenCount = 73;
          response.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
          });
          response.end(
            JSON.stringify({
              ok: true,
              mode: payload.mode,
              translated_text: translatedText,
              explanation,
              raw_response: rawResponse,
              used_mock: false,
              image_count: payload.images?.length ?? 0,
              availability: 'live',
              degraded_reason: null,
              selection_metadata: payload.selection_metadata ?? null,
              usage: {
                prompt_token_count: promptTokenCount,
                cached_content_token_count: cachedContentTokenCount,
                candidates_token_count: candidatesTokenCount,
                total_token_count:
                  promptTokenCount +
                  cachedContentTokenCount +
                  candidatesTokenCount,
              },
            })
          );
        });
        return;
      }

      if (request.method === 'POST' && request.url === '/tokens/count') {
        let body = '';
        request.setEncoding('utf8');
        request.on('data', (chunk) => {
          body += chunk;
        });
        request.on('end', () => {
          const payload = JSON.parse(body) as TokenCountRequestPayload;
          state.tokenRequests.push(payload);
          response.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
          });
          response.end(
            JSON.stringify({
              ok: true,
              token_count: estimateTokenCount(payload.text),
              model_name: payload.model_name ?? 'gemini-2.5-flash',
            })
          );
        });
        return;
      }

      if (request.method === 'POST' && request.url === '/cache/create') {
        let body = '';
        request.setEncoding('utf8');
        request.on('data', (chunk) => {
          body += chunk;
        });
        request.on('end', () => {
          const payload = JSON.parse(body) as CreateCacheRequestPayload;
          state.cacheCreateRequests.push(payload);
          state.activeCache = {
            cacheName: 'cachedContents/article-1',
            displayName:
              payload.display_name ?? 'browser-extension:Fixture article',
            modelName: payload.model_name ?? 'gemini-2.5-flash',
            tokenCount: estimateTokenCount(payload.full_text),
            ttlSeconds: 3600,
            expireTime: '2026-04-17T10:00:00+00:00',
          };
          response.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
          });
          response.end(
            JSON.stringify({
              ok: true,
              is_active: true,
              cache_name: state.activeCache.cacheName,
              display_name: state.activeCache.displayName,
              model_name: state.activeCache.modelName,
              token_count: state.activeCache.tokenCount,
              ttl_seconds: state.activeCache.ttlSeconds,
              expire_time: state.activeCache.expireTime,
            })
          );
        });
        return;
      }

      if (request.method === 'GET' && request.url === '/cache/status') {
        response.writeHead(200, {
          'Content-Type': 'application/json; charset=utf-8',
        });
        if (!state.activeCache) {
          response.end(JSON.stringify({ ok: true, is_active: false }));
          return;
        }

        response.end(
          JSON.stringify({
            ok: true,
            is_active: true,
            cache_name: state.activeCache.cacheName,
            display_name: state.activeCache.displayName,
            model_name: state.activeCache.modelName,
            token_count: state.activeCache.tokenCount,
            ttl_seconds: state.activeCache.ttlSeconds,
            expire_time: state.activeCache.expireTime,
          })
        );
        return;
      }

      if (request.method === 'DELETE' && request.url.startsWith('/cache/')) {
        const cacheName = decodeURIComponent(
          request.url.slice('/cache/'.length)
        );
        state.cacheDeleteRequests.push(cacheName);
        if (state.activeCache?.cacheName === cacheName) {
          state.activeCache = undefined;
        }
        response.writeHead(204).end();
        return;
      }

      response.writeHead(404, {
        'Content-Type': 'application/json; charset=utf-8',
      });
      response.end(JSON.stringify({ error: 'not found' }));
    });

    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        reject(new Error('Failed to bind stub API server.'));
        return;
      }

      resolve({
        server,
        url: `http://127.0.0.1:${address.port}`,
        state,
      });
    });
  });
}

async function closeServer(server: Server): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
}

async function getServiceWorker(context: BrowserContext): Promise<Worker> {
  const existingWorker = context.serviceWorkers()[0];
  if (existingWorker) {
    return existingWorker;
  }

  return context.waitForEvent('serviceworker');
}

async function selectFixtureText(page: Page): Promise<void> {
  await selectFixtureTextBySelector(page, '#target');
}

async function selectFixtureTextBySelector(
  page: Page,
  selector: string
): Promise<void> {
  await page.locator(selector).waitFor();
  await page.evaluate((targetSelector) => {
    const paragraph = document.querySelector(targetSelector);
    if (!(paragraph?.firstChild instanceof Text)) {
      throw new Error('Fixture paragraph text node is missing.');
    }

    const range = document.createRange();
    range.setStart(paragraph.firstChild, 0);
    range.setEnd(
      paragraph.firstChild,
      paragraph.firstChild.textContent?.length ?? 0
    );

    const selection = window.getSelection();
    if (!selection) {
      throw new Error('Selection API is unavailable.');
    }

    selection.removeAllRanges();
    selection.addRange(range);
    document.dispatchEvent(new Event('selectionchange'));
  }, selector);
}

async function addSecondFixtureParagraph(page: Page): Promise<void> {
  await page.evaluate((text) => {
    if (document.querySelector('#target-2')) {
      return;
    }

    const paragraph = document.createElement('p');
    paragraph.id = 'target-2';
    paragraph.textContent = text;
    paragraph.style.marginTop = '24px';
    document.querySelector('main')?.appendChild(paragraph);
  }, secondSelectionText);
}

async function addLongArticleContent(page: Page): Promise<void> {
  await page.evaluate(() => {
    const main = document.querySelector('main');
    if (!main || document.querySelector('[data-phase4-article]')) {
      return;
    }

    const fragment = document.createDocumentFragment();
    const paragraphText =
      'Gem Read Phase 4 smoke content expands the article body with repeated technical prose so article extraction, cache eligibility, and token comparison can be validated without depending on a live site.';

    for (let index = 0; index < 28; index += 1) {
      const paragraph = document.createElement('p');
      paragraph.dataset.phase4Article = 'true';
      paragraph.textContent = `${index + 1}. ${paragraphText}`;
      paragraph.style.marginTop = '16px';
      fragment.appendChild(paragraph);
    }

    main.appendChild(fragment);
  });
}

async function sendTabMessage<T>(worker: Worker, message: unknown): Promise<T> {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      return (await worker.evaluate(async (runtimeMessage) => {
        const [tab] = await chrome.tabs.query({
          active: true,
          lastFocusedWindow: true,
        });
        if (!tab?.id) {
          throw new Error('No active tab found.');
        }

        return chrome.tabs.sendMessage(tab.id, runtimeMessage as object);
      }, message)) as T;
    } catch (error) {
      const messageText =
        error instanceof Error ? error.message : String(error);
      if (
        !messageText.includes('Receiving end does not exist') ||
        attempt === 29
      ) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }

  throw new Error('Content script connection could not be established.');
}

async function collectSelection(worker: Worker): Promise<SelectionResponse> {
  return sendTabMessage(worker, {
    type: 'phase0.collectSelection',
    fallbackText: '',
  });
}

async function renderBatchOverlay(
  worker: Worker,
  sessionItems: SeededSessionItem[] = []
): Promise<void> {
  const latestItem = sessionItems.at(-1);
  await sendTabMessage(worker, {
    type: 'phase0.renderOverlay',
    payload: {
      status: 'success',
      action: 'translation',
      modelName: 'gemini-2.5-flash',
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'Gemini 2.5 Flash',
        },
      ],
      sessionReady: sessionItems.length > 0,
      sessionItems,
      maxSessionItems: 10,
      selectedText: latestItem?.selection.text || '[Image region only]',
      previewImageUrl: latestItem?.previewImageUrl,
    },
  });
}

async function seedBatchOverlaySession(
  worker: Worker,
  items: SeededSessionItem[]
): Promise<void> {
  const response = await sendTabMessage(worker, {
    type: 'phase2.seedBatchOverlaySession',
    payload: {
      items,
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'Gemini 2.5 Flash',
        },
      ],
      lastAction: 'translation',
      lastModelName: 'gemini-2.5-flash',
    },
  });

  expect(response).toMatchObject({ ok: true });
}

async function seedOverlaySession(worker: Worker): Promise<void> {
  const response = await sendTabMessage(worker, {
    type: 'phase1.seedOverlaySession',
    payload: {
      previewImageUrl: 'data:image/webp;base64,preview',
      cropDurationMs: 1.5,
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'Gemini 2.5 Flash',
        },
      ],
    },
  });

  expect(response).toMatchObject({ ok: true });
}

async function getExtensionId(worker: Worker): Promise<string> {
  return new URL(worker.url()).host;
}

async function savePopupSettings(
  context: BrowserContext,
  extensionId: string,
  apiBaseUrl: string
): Promise<void> {
  const popupPage = await context.newPage();
  await popupPage.goto(`chrome-extension://${extensionId}/index.html`, {
    waitUntil: 'domcontentloaded',
  });
  await popupPage.locator('#api-base-url').fill(apiBaseUrl);
  await popupPage.locator('#default-model').fill('gemini-2.5-flash');
  await popupPage.locator('[data-role="save-button"]').click();

  await expect(popupPage.locator('[data-role="status-badge"]')).toContainText(
    'Reachable'
  );
  await expect(popupPage.locator('[data-role="message-line"]')).toContainText(
    'Settings saved.'
  );
  await popupPage.close();
}

async function openOverlayFromPopupHelper(
  context: BrowserContext,
  extensionId: string,
  targetPage: Page
): Promise<void> {
  const popupPage = await context.newPage();
  await popupPage.goto(`chrome-extension://${extensionId}/index.html`, {
    waitUntil: 'domcontentloaded',
  });
  await targetPage.bringToFront();
  const response = await popupPage.evaluate(async () => {
    return chrome.runtime.sendMessage({ type: 'phase3.openOverlay' });
  });
  expect(response).toMatchObject({ ok: true });
  await popupPage.close();
}

function shadowLocator(page: Page, selector: string): Locator {
  return page.locator(selector).first();
}

async function readShadowText(
  page: Page,
  selector: string
): Promise<string | null> {
  const textContent = await shadowLocator(page, selector).textContent();
  return textContent?.trim() ?? null;
}

async function readShadowAttribute(
  page: Page,
  selector: string,
  attributeName: string
): Promise<string | null> {
  return shadowLocator(page, selector).getAttribute(attributeName);
}

async function clickShadow(page: Page, selector: string): Promise<void> {
  await shadowLocator(page, selector).click();
}

async function fillShadowInput(
  page: Page,
  selector: string,
  value: string
): Promise<void> {
  await shadowLocator(page, selector).fill(value);
}

async function readShadowCount(page: Page, selector: string): Promise<number> {
  return page.locator(selector).count();
}

async function setShadowCheckbox(
  page: Page,
  selector: string,
  checked: boolean
): Promise<void> {
  await shadowLocator(page, selector).setChecked(checked);
}

async function readShadowChecked(
  page: Page,
  selector: string
): Promise<boolean> {
  return shadowLocator(page, selector).isChecked();
}

test('reopens the cached overlay and supports keyboard reruns in Chromium', async () => {
  const userDataDir = await fs.mkdtemp(
    path.join(os.tmpdir(), 'gem-read-extension-')
  );
  const { server, url } = await startFixtureServer();
  const {
    server: apiServer,
    url: apiUrl,
    state: apiState,
  } = await startStubApiServer();
  let context: BrowserContext | undefined;

  try {
    context = await chromium.launchPersistentContext(userDataDir, {
      channel: 'chromium',
      headless: true,
      args: [
        `--disable-extensions-except=${extensionPath}`,
        `--load-extension=${extensionPath}`,
      ],
    });

    const worker = await getServiceWorker(context);
    const extensionId = await getExtensionId(worker);
    await savePopupSettings(context, extensionId, apiUrl);

    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#target')).toContainText(
      'Gem Read validates browser selection smoke tests'
    );
    await selectFixtureText(page);

    await expect
      .poll(async () => {
        const response = await collectSelection(worker);
        return response.ok ? (response.payload?.text ?? '') : '';
      })
      .toBe(expectedSelectionText);

    const response = await collectSelection(worker);
    expect(response).toMatchObject({
      ok: true,
      payload: {
        text: expectedSelectionText,
      },
    });

    await seedOverlaySession(worker);
    await openOverlayFromPopupHelper(context, extensionId, page);

    await expect
      .poll(async () => readShadowText(page, '.selection-box'))
      .toBe(expectedSelectionText);
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="workspace"]',
          'aria-selected'
        )
      )
      .toBe('true');

    await page.keyboard.press('Escape');
    await expect
      .poll(async () => readShadowText(page, '.launcher-button'))
      .toContain('Gem Read');

    await openOverlayFromPopupHelper(context, extensionId, page);
    await expect
      .poll(async () => readShadowText(page, '.badge'))
      .toContain('Live Result');
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="workspace"]',
          'aria-selected'
        )
      )
      .toBe('true');

    await page.keyboard.press('Alt+R');
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe(`[ja] 1. ${expectedSelectionText}`);
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="gemini"]',
          'aria-selected'
        )
      )
      .toBe('true');

    await page.keyboard.press('Escape');
    await expect
      .poll(async () => readShadowText(page, '.launcher-button'))
      .toContain('Gem Read');

    await sendTabMessage(worker, {
      type: 'phase1.invokeOverlayAction',
      payload: { action: 'translation' },
    });
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe(`[ja] 1. ${expectedSelectionText}`);
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="gemini"]',
          'aria-selected'
        )
      )
      .toBe('true');

    await clickShadow(page, '.panel-tab[data-tab-id="workspace"]');

    await fillShadowInput(
      page,
      '.custom-prompt-input',
      'Explain the highlighted paragraph'
    );
    await page.keyboard.press('Control+Enter');
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe('[custom] Explain the highlighted paragraph');
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="gemini"]',
          'aria-selected'
        )
      )
      .toBe('true');
    await expect
      .poll(async () => readShadowText(page, '.explanation-box'))
      .toBe('');

    expect(apiState.healthChecks).toBeGreaterThan(0);
    expect(apiState.modelRequests).toBeGreaterThan(0);
    expect(apiState.analyzeRequests).toHaveLength(3);
    expect(apiState.analyzeRequests[0]).toMatchObject({
      mode: 'translation',
      text: `1. ${expectedSelectionText}`,
      model_name: 'gemini-2.5-flash',
    });
    expect(apiState.analyzeRequests[1]).toMatchObject({
      mode: 'translation',
      text: `1. ${expectedSelectionText}`,
      model_name: 'gemini-2.5-flash',
    });
    expect(apiState.analyzeRequests[2]).toMatchObject({
      mode: 'custom_prompt',
      custom_prompt: 'Explain the highlighted paragraph',
      text: `1. ${expectedSelectionText}`,
    });
  } finally {
    await context?.close();
    await closeServer(server);
    await closeServer(apiServer);
    await fs.rm(userDataDir, { recursive: true, force: true });
  }
});

test('supports ordered multi-selection batches with explanation and custom prompt reruns', async () => {
  const userDataDir = await fs.mkdtemp(
    path.join(os.tmpdir(), 'gem-read-extension-batch-')
  );
  const { server, url } = await startFixtureServer();
  const {
    server: apiServer,
    url: apiUrl,
    state: apiState,
  } = await startStubApiServer();
  let context: BrowserContext | undefined;

  try {
    context = await chromium.launchPersistentContext(userDataDir, {
      channel: 'chromium',
      headless: true,
      args: [
        `--disable-extensions-except=${extensionPath}`,
        `--load-extension=${extensionPath}`,
      ],
    });

    const worker = await getServiceWorker(context);
    const extensionId = await getExtensionId(worker);
    await savePopupSettings(context, extensionId, apiUrl);

    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await addSecondFixtureParagraph(page);
    await selectFixtureTextBySelector(page, '#target');
    const firstSelection = await collectSelection(worker);
    expect(firstSelection).toMatchObject({
      ok: true,
      payload: { text: expectedSelectionText },
    });

    await selectFixtureTextBySelector(page, '#target-2');
    const secondSelection = await collectSelection(worker);
    expect(secondSelection).toMatchObject({
      ok: true,
      payload: { text: secondSelectionText },
    });

    const seededItems: SeededSessionItem[] = [
      {
        id: 'selection-1',
        source: 'text-selection',
        selection: firstSelection.payload!,
        includeImage: false,
        previewImageUrl: 'data:image/webp;base64,preview-a',
        cropDurationMs: 1.5,
      },
      {
        id: 'selection-2',
        source: 'text-selection',
        selection: secondSelection.payload!,
        includeImage: false,
        previewImageUrl: 'data:image/webp;base64,preview-b',
        cropDurationMs: 1.8,
      },
    ];

    await seedBatchOverlaySession(worker, seededItems);
    await renderBatchOverlay(worker, seededItems);

    await expect
      .poll(async () => readShadowCount(page, '.session-item-remove'))
      .toBe(2);
    await expect
      .poll(async () => readShadowText(page, '.batch-counter'))
      .toContain('2/10');

    await setShadowCheckbox(page, '.session-item-image-toggle', true);
    await expect
      .poll(async () => readShadowChecked(page, '.session-item-image-toggle'))
      .toBe(true);

    await fillShadowInput(
      page,
      '.custom-prompt-input',
      'Summarize both paragraphs'
    );
    await page.keyboard.press('Control+Enter');
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe('[custom] Summarize both paragraphs');

    await page.keyboard.press('Alt+R');
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe('[custom] Summarize both paragraphs');

    expect(apiState.analyzeRequests).toHaveLength(2);
    expect(apiState.analyzeRequests[0]).toMatchObject({
      mode: 'custom_prompt',
      custom_prompt: 'Summarize both paragraphs',
      text: `1. ${expectedSelectionText}\n\n2. ${secondSelectionText}`,
    });
    expect(apiState.analyzeRequests[0].images?.length ?? 0).toBe(1);
    expect(apiState.analyzeRequests[0].selection_metadata?.items).toHaveLength(
      2
    );
    expect(apiState.analyzeRequests[1]).toMatchObject({
      mode: 'custom_prompt',
      custom_prompt: 'Summarize both paragraphs',
      text: `1. ${expectedSelectionText}\n\n2. ${secondSelectionText}`,
    });
  } finally {
    await context?.close();
    await closeServer(server);
    await closeServer(apiServer);
    await fs.rm(userDataDir, { recursive: true, force: true });
  }
});

test('supports image-only rectangle sessions with custom prompt reruns', async () => {
  const userDataDir = await fs.mkdtemp(
    path.join(os.tmpdir(), 'gem-read-extension-rectangle-')
  );
  const { server, url } = await startFixtureServer();
  const {
    server: apiServer,
    url: apiUrl,
    state: apiState,
  } = await startStubApiServer();
  let context: BrowserContext | undefined;

  try {
    context = await chromium.launchPersistentContext(userDataDir, {
      channel: 'chromium',
      headless: true,
      args: [
        `--disable-extensions-except=${extensionPath}`,
        `--load-extension=${extensionPath}`,
      ],
    });

    const worker = await getServiceWorker(context);
    const extensionId = await getExtensionId(worker);
    await savePopupSettings(context, extensionId, apiUrl);

    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    const rectangleSelection = await page.evaluate(() => ({
      text: '',
      rect: {
        left: 80,
        top: 120,
        width: 160,
        height: 140,
      },
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio || 1,
      url: window.location.href,
      pageTitle: document.title,
    }));

    const seededItems: SeededSessionItem[] = [
      {
        id: 'rectangle-1',
        source: 'free-rectangle',
        selection: rectangleSelection,
        includeImage: true,
        previewImageUrl: 'data:image/webp;base64,preview-rectangle',
        cropDurationMs: 2.1,
      },
    ];

    await seedBatchOverlaySession(worker, seededItems);
    await renderBatchOverlay(worker, seededItems);

    await expect
      .poll(async () => readShadowCount(page, '.session-item-remove'))
      .toBe(1);
    await expect
      .poll(async () => readShadowText(page, '.session-item-text'))
      .toContain('[Image region only]');
    await expect
      .poll(async () => readShadowChecked(page, '.session-item-image-toggle'))
      .toBe(true);

    await fillShadowInput(
      page,
      '.custom-prompt-input',
      'Describe the selected figure'
    );
    await clickShadow(page, '.action-custom');
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe('[custom] Describe the selected figure');
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="gemini"]',
          'aria-selected'
        )
      )
      .toBe('true');

    expect(apiState.analyzeRequests).toHaveLength(1);
    expect(apiState.analyzeRequests[0]).toMatchObject({
      mode: 'custom_prompt',
      text: '',
      custom_prompt: 'Describe the selected figure',
    });
    expect(apiState.analyzeRequests[0].images?.length).toBe(1);
    expect(
      apiState.analyzeRequests[0].selection_metadata?.items?.[0]
    ).toMatchObject({
      source: 'free-rectangle',
      include_image: true,
      image_index: 0,
    });
  } finally {
    await context?.close();
    await closeServer(server);
    await closeServer(apiServer);
    await fs.rm(userDataDir, { recursive: true, force: true });
  }
});

test('surfaces article context, cache state, token estimates, and result usage together', async () => {
  const userDataDir = await fs.mkdtemp(
    path.join(os.tmpdir(), 'gem-read-extension-phase4-')
  );
  const { server, url } = await startFixtureServer();
  const {
    server: apiServer,
    url: apiUrl,
    state: apiState,
  } = await startStubApiServer();
  let context: BrowserContext | undefined;

  try {
    context = await chromium.launchPersistentContext(userDataDir, {
      channel: 'chromium',
      headless: true,
      args: [
        `--disable-extensions-except=${extensionPath}`,
        `--load-extension=${extensionPath}`,
      ],
    });

    const worker = await getServiceWorker(context);
    const extensionId = await getExtensionId(worker);
    await savePopupSettings(context, extensionId, apiUrl);

    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await addLongArticleContent(page);
    await selectFixtureText(page);

    const selection = await collectSelection(worker);
    expect(selection).toMatchObject({
      ok: true,
      payload: { text: expectedSelectionText },
    });

    await seedBatchOverlaySession(worker, [
      {
        id: 'selection-1',
        source: 'text-selection',
        selection: selection.payload!,
        includeImage: false,
        previewImageUrl: 'data:image/webp;base64,preview-a',
        cropDurationMs: 1.5,
      },
    ]);

    await openOverlayFromPopupHelper(context, extensionId, page);

    await expect
      .poll(async () => readShadowText(page, '.article-title'))
      .toContain('Gem Read Playwright Fixture');
    await expect
      .poll(async () => readShadowText(page, '.panel'))
      .toContain('Current Request');
    await expect
      .poll(async () => readShadowText(page, '.panel'))
      .toContain('Article Baseline');
    await expect
      .poll(async () => readShadowText(page, '.panel'))
      .toContain('Cache active');

    await page.keyboard.press('Alt+R');
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe(`[ja] 1. ${expectedSelectionText}`);
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="gemini"]',
          'aria-selected'
        )
      )
      .toBe('true');
    await expect
      .poll(async () => readShadowText(page, '.panel'))
      .toContain('Last Response');
    await expect
      .poll(async () => readShadowText(page, '.panel'))
      .toContain('cached');

    await clickShadow(page, '.panel-tab[data-tab-id="workspace"]');
    await clickShadow(page, '.action-delete-article-cache');
    await expect
      .poll(async () => readShadowText(page, '.panel'))
      .toContain('Invalidated');

    expect(apiState.tokenRequests.length).toBeGreaterThanOrEqual(2);
    expect(apiState.cacheCreateRequests).toHaveLength(1);
    expect(apiState.analyzeRequests).toHaveLength(1);
    expect(apiState.cacheDeleteRequests).toContain('cachedContents/article-1');
  } finally {
    await context?.close();
    await closeServer(server);
    await closeServer(apiServer);
    await fs.rm(userDataDir, { recursive: true, force: true });
  }
});

test('reuses one article cache across all three action modes without recreation', async () => {
  const userDataDir = await fs.mkdtemp(
    path.join(os.tmpdir(), 'gem-read-extension-crossmode-')
  );
  const { server, url } = await startFixtureServer();
  const {
    server: apiServer,
    url: apiUrl,
    state: apiState,
  } = await startStubApiServer();
  let context: BrowserContext | undefined;

  try {
    context = await chromium.launchPersistentContext(userDataDir, {
      channel: 'chromium',
      headless: true,
      args: [
        `--disable-extensions-except=${extensionPath}`,
        `--load-extension=${extensionPath}`,
      ],
    });

    const worker = await getServiceWorker(context);
    const extensionId = await getExtensionId(worker);
    await savePopupSettings(context, extensionId, apiUrl);

    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await addLongArticleContent(page);
    await selectFixtureText(page);

    const selection = await collectSelection(worker);
    expect(selection).toMatchObject({
      ok: true,
      payload: { text: expectedSelectionText },
    });

    await seedBatchOverlaySession(worker, [
      {
        id: 'selection-1',
        source: 'text-selection',
        selection: selection.payload!,
        includeImage: false,
        previewImageUrl: 'data:image/webp;base64,preview-a',
        cropDurationMs: 1.5,
      },
    ]);

    await openOverlayFromPopupHelper(context, extensionId, page);

    // Wait for article cache to auto-create and become active
    await expect
      .poll(async () => readShadowText(page, '.panel'))
      .toContain('Cache active');

    // Exactly one cache creation so far
    expect(apiState.cacheCreateRequests).toHaveLength(1);

    // Mode 1: translation
    await page.keyboard.press('Alt+R');
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe(`[ja] 1. ${expectedSelectionText}`);
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="gemini"]',
          'aria-selected'
        )
      )
      .toBe('true');

    // Mode 2: translation_with_explanation
    await clickShadow(page, '.panel-tab[data-tab-id="workspace"]');
    await clickShadow(page, '.action-explanation');
    await expect
      .poll(async () => readShadowText(page, '.explanation-box'))
      .toContain('Stub explanation');
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="gemini"]',
          'aria-selected'
        )
      )
      .toBe('true');

    // Mode 3: custom_prompt
    await clickShadow(page, '.panel-tab[data-tab-id="workspace"]');
    await fillShadowInput(
      page,
      '.custom-prompt-input',
      'Cross-mode cache reuse test'
    );
    await clickShadow(page, '.action-custom');
    await expect
      .poll(async () => readShadowText(page, '.result-box'))
      .toBe('[custom] Cross-mode cache reuse test');
    await expect
      .poll(async () =>
        readShadowAttribute(
          page,
          '.panel-tab[data-tab-id="gemini"]',
          'aria-selected'
        )
      )
      .toBe('true');

    // All three modes completed — still only one cache creation
    expect(apiState.analyzeRequests).toHaveLength(3);
    expect(apiState.cacheCreateRequests).toHaveLength(1);
    expect(apiState.analyzeRequests[0]).toMatchObject({ mode: 'translation' });
    expect(apiState.analyzeRequests[1]).toMatchObject({
      mode: 'translation_with_explanation',
    });
    expect(apiState.analyzeRequests[2]).toMatchObject({ mode: 'custom_prompt' });
  } finally {
    await context?.close();
    await closeServer(server);
    await closeServer(apiServer);
    await fs.rm(userDataDir, { recursive: true, force: true });
  }
});
