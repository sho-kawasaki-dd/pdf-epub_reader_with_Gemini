import { describe, expect, it, vi } from 'vitest';

import { renderOverlay } from '../../../src/content/overlay/renderOverlay';
import { getChromeMock } from '../../mocks/chrome';

function getShadowRoot(): ShadowRoot {
  const host = document.getElementById('gem-read-phase0-overlay-host');
  if (!host?.shadowRoot) {
    throw new Error('Overlay host was not rendered.');
  }
  return host.shadowRoot;
}

// overlay が payload から状態を再構成し、action を background に委譲する契約を固定する suite。
describe('renderOverlay', () => {
  it('renders a loading overlay with action controls and selection text', () => {
    renderOverlay({
      status: 'loading',
      action: 'translation',
      sessionItems: [],
      maxSessionItems: 10,
      modelName: 'gemini-2.5-flash',
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'Gemini 2.5 Flash',
        },
      ],
      selectedText: 'Selected paragraph',
    });

    const root = getShadowRoot();
    expect(root.querySelector('.badge')?.textContent).toContain('Running');
    expect(root.querySelector('.selection-box')?.textContent).toBe(
      'Selected paragraph'
    );
    expect(root.querySelector('.meta-box')?.textContent).toContain(
      'Background workflow is running.'
    );
    expect(
      (root.querySelector('.action-translation') as HTMLButtonElement).disabled
    ).toBe(true);
    expect((root.querySelector('.model-input') as HTMLInputElement).value).toBe(
      'gemini-2.5-flash'
    );
    expect((root.querySelector('.result-section') as HTMLElement).hidden).toBe(
      true
    );
    expect((root.querySelector('.error-section') as HTMLElement).hidden).toBe(
      true
    );
    expect(root.querySelector('.batch-counter')?.textContent).toContain('0/10');
  });

  it('renders success details, shows runtime banner, and reuses the same host element', () => {
    renderOverlay({
      status: 'success',
      action: 'translation_with_explanation',
      sessionItems: [
        {
          id: 'selection-1',
          source: 'text-selection',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
          cropDurationMs: 12.3,
        },
      ],
      maxSessionItems: 10,
      modelName: 'gemini-2.5-flash',
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'Gemini 2.5 Flash',
        },
      ],
      sessionReady: true,
      selectedText: 'Selected paragraph',
      translatedText: '翻訳結果',
      explanation: '補足説明',
      previewImageUrl: 'data:image/webp;base64,preview',
      rawResponse: '翻訳結果\n\n---\n\n補足説明',
      imageCount: 1,
      timingMs: 12.3,
      usedMock: true,
      availability: 'mock',
      degradedReason: 'mock-response',
    });
    renderOverlay({
      status: 'success',
      action: 'translation_with_explanation',
      sessionItems: [
        {
          id: 'selection-1',
          source: 'text-selection',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
          cropDurationMs: 12.3,
        },
      ],
      maxSessionItems: 10,
      modelName: 'gemini-2.5-flash',
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'Gemini 2.5 Flash',
        },
      ],
      sessionReady: true,
      selectedText: 'Selected paragraph',
      translatedText: '翻訳結果',
      explanation: '補足説明',
      previewImageUrl: 'data:image/webp;base64,preview',
      rawResponse: '翻訳結果\n\n---\n\n補足説明',
      imageCount: 1,
      timingMs: 12.3,
      usedMock: true,
      availability: 'mock',
      degradedReason: 'mock-response',
    });

    const root = getShadowRoot();
    expect(
      document.querySelectorAll('#gem-read-phase0-overlay-host')
    ).toHaveLength(1);
    expect(root.querySelector('.badge')?.textContent).toContain('Mock Result');
    expect(root.querySelector('.banner-box')?.textContent).toContain(
      'Mock mode is active'
    );
    expect(root.querySelector('.result-box')?.textContent?.trim()).toBe('翻訳結果');
    expect(root.querySelector('.explanation-box')?.textContent?.trim()).toBe(
      '補足説明'
    );
    expect(root.querySelector('.raw-details')).not.toBeNull();
    expect(
      (root.querySelector('.raw-details') as HTMLDetailsElement).open
    ).toBe(false);
    expect(root.querySelector('.raw-box')?.textContent).toContain('---');
    expect((root.querySelector('.preview-section') as HTMLElement).hidden).toBe(
      false
    );
    expect((root.querySelector('.preview-image') as HTMLImageElement).src).toBe(
      'data:image/webp;base64,preview'
    );
    expect(
      (root.querySelector('.action-translation') as HTMLButtonElement).disabled
    ).toBe(false);
    expect(root.querySelector('.meta-box')?.textContent).toContain('images=1');
    expect(root.querySelector('.meta-box')?.textContent).toContain(
      'crop=12.3ms'
    );
    expect(root.querySelector('.meta-box')?.textContent).toContain(
      'mock-response'
    );
    expect(root.querySelector('.session-item-text')?.textContent).toContain(
      'Selected paragraph'
    );
  });

  it('renders markdown safely and applies KaTeX outside code blocks', () => {
    renderOverlay({
      status: 'success',
      action: 'translation_with_explanation',
      sessionReady: true,
      sessionItems: [
        {
          id: 'selection-1',
          source: 'text-selection',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
        },
      ],
      translatedText:
        '# Heading\n\nInline math $a^2+b^2=c^2$\n\n```txt\n$should_stay_literal$\n```\n\n<img src=x onerror="alert(1)">',
      rawResponse: 'raw',
    });

    const root = getShadowRoot();
    const resultBox = root.querySelector('.result-box') as HTMLElement;

    expect(resultBox.querySelector('h1')?.textContent).toBe('Heading');
    expect(resultBox.querySelector('.katex')).not.toBeNull();
    expect(resultBox.innerHTML.includes('onerror')).toBe(false);
    expect(resultBox.querySelector('code')?.textContent).toContain(
      '$should_stay_literal$'
    );
  });

  it('sends overlay action messages to the background runtime', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.runtime.sendMessage as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true });

    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionItems: [
        {
          id: 'selection-1',
          source: 'text-selection',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
          cropDurationMs: 12.3,
        },
      ],
      maxSessionItems: 10,
      modelName: 'gemini-2.5-flash',
      modelOptions: [
        {
          modelId: 'gemini-2.5-flash',
          displayName: 'Gemini 2.5 Flash',
        },
      ],
      customPrompt: 'Summarize this',
      sessionReady: true,
      selectedText: 'Selected paragraph',
      translatedText: '翻訳結果',
      rawResponse: '翻訳結果',
    });

    const root = getShadowRoot();
    const modelInput = root.querySelector('.model-input') as HTMLInputElement;
    const customPromptInput = root.querySelector(
      '.custom-prompt-input'
    ) as HTMLTextAreaElement;
    modelInput.value = 'gemini-2.5-pro';
    customPromptInput.value = 'Explain the terminology';
    modelInput.dispatchEvent(new Event('input', { bubbles: true }));
    customPromptInput.dispatchEvent(new Event('input', { bubbles: true }));

    (root.querySelector('.action-custom') as HTMLButtonElement).click();
    await Promise.resolve();

    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: 'phase1.runOverlayAction',
      payload: {
        action: 'custom_prompt',
        modelName: 'gemini-2.5-pro',
        customPrompt: 'Explain the terminology',
      },
    });
  });

  it('minimizes to a launcher and reopens from the launcher button', () => {
    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionItems: [],
      maxSessionItems: 10,
      sessionReady: true,
      selectedText: 'Selected paragraph',
      translatedText: '翻訳結果',
      rawResponse: '翻訳結果',
    });

    let root = getShadowRoot();
    (root.querySelector('.minimize') as HTMLButtonElement).click();

    root = getShadowRoot();
    expect(root.querySelector('.launcher-button')?.textContent).toContain(
      'Gem Read'
    );

    (root.querySelector('.launcher-button') as HTMLButtonElement).click();
    root = getShadowRoot();
    expect(root.querySelector('.panel')).not.toBeNull();
  });

  it('minimizes the overlay when Escape is pressed outside rectangle mode', () => {
    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionItems: [],
      maxSessionItems: 10,
      sessionReady: true,
      selectedText: 'Selected paragraph',
      translatedText: '翻訳結果',
      rawResponse: '翻訳結果',
    });

    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
    );

    const root = getShadowRoot();
    expect(root.querySelector('.launcher')).not.toBeNull();
  });

  it('closes the overlay and clears the session when Shift+Escape is pressed', () => {
    const chromeMock = getChromeMock();
    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionItems: [],
      maxSessionItems: 10,
      sessionReady: true,
      selectedText: 'Selected paragraph',
      translatedText: '翻訳結果',
      rawResponse: '翻訳結果',
    });

    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Escape',
        shiftKey: true,
        bubbles: true,
      })
    );

    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: 'phase2.clearOverlaySession',
    });
    expect(document.getElementById('gem-read-phase0-overlay-host')).toBeNull();
  });

  it('submits the custom prompt with Ctrl+Enter from the textarea', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.runtime.sendMessage as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true });

    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionReady: true,
      sessionItems: [
        {
          id: 'selection-1',
          source: 'text-selection',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
          cropDurationMs: 12.3,
        },
      ],
      maxSessionItems: 10,
      modelName: 'gemini-2.5-flash',
      customPrompt: 'Summarize this',
      selectedText: 'Selected paragraph',
      translatedText: '翻訳結果',
      rawResponse: '翻訳結果',
    });

    const root = getShadowRoot();
    const modelInput = root.querySelector('.model-input') as HTMLInputElement;
    const customPromptInput = root.querySelector(
      '.custom-prompt-input'
    ) as HTMLTextAreaElement;
    modelInput.value = 'gemini-2.5-pro';
    customPromptInput.value = 'Explain the terminology';
    modelInput.dispatchEvent(new Event('input', { bubbles: true }));
    customPromptInput.dispatchEvent(new Event('input', { bubbles: true }));

    customPromptInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Enter',
        ctrlKey: true,
        bubbles: true,
        composed: true,
      })
    );
    await Promise.resolve();

    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: 'phase1.runOverlayAction',
      payload: {
        action: 'custom_prompt',
        modelName: 'gemini-2.5-pro',
        customPrompt: 'Explain the terminology',
      },
    });
  });

  it('reruns the last action with Alt+R when focus is outside editable controls', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.runtime.sendMessage as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true });

    renderOverlay({
      status: 'success',
      action: 'custom_prompt',
      sessionReady: true,
      sessionItems: [
        {
          id: 'selection-1',
          source: 'text-selection',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
          cropDurationMs: 12.3,
        },
      ],
      maxSessionItems: 10,
      modelName: 'gemini-2.5-pro',
      customPrompt: 'Summarize this',
      selectedText: 'Selected paragraph',
      translatedText: 'custom answer',
      rawResponse: 'custom answer',
    });

    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'r',
        altKey: true,
        bubbles: true,
      })
    );
    await Promise.resolve();

    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: 'phase1.runOverlayAction',
      payload: {
        action: 'custom_prompt',
        modelName: 'gemini-2.5-pro',
        customPrompt: 'Summarize this',
      },
    });
  });

  it('removes the overlay when the close button is clicked', () => {
    const chromeMock = getChromeMock();
    renderOverlay({
      status: 'error',
      sessionItems: [],
      maxSessionItems: 10,
      sessionReady: false,
      selectedText: 'Selected paragraph',
      error: 'Something failed',
    });

    const root = getShadowRoot();
    (root.querySelector('.close') as HTMLButtonElement).click();

    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: 'phase2.clearOverlaySession',
    });
    expect(document.getElementById('gem-read-phase0-overlay-host')).toBeNull();
  });

  it('sends remove-session-item messages from batch controls', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.runtime.sendMessage as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true });

    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionReady: true,
      sessionItems: [
        {
          id: 'selection-1',
          source: 'text-selection',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
          cropDurationMs: 12.3,
        },
      ],
      maxSessionItems: 10,
      selectedText: 'Selected paragraph',
    });

    const root = getShadowRoot();
    (root.querySelector('.session-item-remove') as HTMLButtonElement).click();
    await Promise.resolve();

    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: 'phase2.removeSessionItem',
      payload: { itemId: 'selection-1' },
    });
  });

  it('sends include-image toggle messages from batch controls', async () => {
    const chromeMock = getChromeMock();
    (chromeMock.runtime.sendMessage as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true });

    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionReady: true,
      sessionItems: [
        {
          id: 'selection-1',
          source: 'text-selection',
          selection: {
            text: 'Selected paragraph',
            rect: { left: 1, top: 2, width: 3, height: 4 },
            viewportWidth: 100,
            viewportHeight: 100,
            devicePixelRatio: 1,
            url: 'https://example.com',
            pageTitle: 'Example',
          },
          includeImage: false,
          previewImageUrl: 'data:image/webp;base64,preview',
          cropDurationMs: 12.3,
        },
      ],
      maxSessionItems: 10,
      selectedText: 'Selected paragraph',
    });

    const root = getShadowRoot();
    const toggle = root.querySelector(
      '.session-item-image-toggle'
    ) as HTMLInputElement;
    toggle.checked = true;
    toggle.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: 'phase2.toggleSessionItemImage',
      payload: { itemId: 'selection-1', includeImage: true },
    });
  });

  it('preserves draft values when reopening a cached session payload', () => {
    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionReady: true,
      sessionItems: [],
      maxSessionItems: 10,
      modelName: 'gemini-2.5-flash',
      selectedText: 'Selected paragraph',
      translatedText: 'First result',
      rawResponse: 'First result',
    });

    let root = getShadowRoot();
    const modelInput = root.querySelector('.model-input') as HTMLInputElement;
    const customPromptInput = root.querySelector(
      '.custom-prompt-input'
    ) as HTMLTextAreaElement;
    modelInput.value = 'gemini-2.5-pro';
    customPromptInput.value = 'Draft prompt';
    modelInput.dispatchEvent(new Event('input', { bubbles: true }));
    customPromptInput.dispatchEvent(new Event('input', { bubbles: true }));

    renderOverlay({
      status: 'success',
      action: 'translation',
      sessionReady: true,
      sessionItems: [],
      maxSessionItems: 10,
      modelName: 'gemini-2.5-flash',
      customPrompt: 'Saved prompt',
      preserveDrafts: true,
      selectedText: 'Selected paragraph',
      translatedText: 'Reopened result',
      rawResponse: 'Reopened result',
    });

    root = getShadowRoot();
    expect((root.querySelector('.model-input') as HTMLInputElement).value).toBe(
      'gemini-2.5-pro'
    );
    expect(
      (root.querySelector('.custom-prompt-input') as HTMLTextAreaElement).value
    ).toBe('Draft prompt');
  });
});
