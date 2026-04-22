import { describe, expect, it } from 'vitest';

import {
  EXTENSION_SETTINGS_STORAGE_KEY,
  type ExtensionSettings,
} from '../../../src/shared/config/phase0';
import {
  loadExtensionSettings,
  patchExtensionSettings,
  saveExtensionSettings,
} from '../../../src/shared/storage/settingsStorage';
import { getChromeMock } from '../../mocks/chrome';

// storage schema の normalize と merge の振る舞いを固定する suite。
describe('settingsStorage', () => {
  it('returns normalized defaults when storage is empty', async () => {
    const settings = await loadExtensionSettings();

    expect(settings).toEqual({
      apiBaseUrl: 'http://127.0.0.1:8000',
      defaultModel: '',
      sharedSystemPrompt: '',
      lastKnownModels: [],
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
  });

  it('persists normalized settings to chrome.storage.local', async () => {
    const chromeMock = getChromeMock();
    const settings = await saveExtensionSettings({
      apiBaseUrl: 'http://localhost:8123/',
      defaultModel: ' gemini-2.5-pro ',
      uiLanguage: 'ja',
      lastKnownModels: [
        'gemini-2.5-pro',
        'gemini-2.5-pro',
        ' gemini-2.5-flash ',
      ],
      markdownExport: {
        includeExplanation: false,
        includeSelections: true,
        includeRawResponse: true,
        includeUsageMetrics: true,
      },
    });

    expect(settings).toEqual({
      apiBaseUrl: 'http://localhost:8123',
      defaultModel: 'gemini-2.5-pro',
      sharedSystemPrompt: '',
      lastKnownModels: ['gemini-2.5-pro', 'gemini-2.5-flash'],
      uiLanguage: 'ja',
      articleCache: {
        enableAutoCreate: true,
      },
      markdownExport: {
        includeExplanation: false,
        includeSelections: true,
        includeRawResponse: true,
        includeArticleMetadata: false,
        includeUsageMetrics: true,
        includeYamlFrontmatter: false,
      },
    });
    expect(chromeMock.storage.local.set).toHaveBeenCalledWith(
      {
        [EXTENSION_SETTINGS_STORAGE_KEY]: settings,
      },
      expect.any(Function)
    );
  });

  it('patches existing settings without losing normalized values', async () => {
    await saveExtensionSettings({
      apiBaseUrl: 'http://127.0.0.1:9000',
      defaultModel: 'gemini-2.5-flash',
      lastKnownModels: ['gemini-2.5-flash'],
      markdownExport: {
        includeExplanation: true,
        includeSelections: false,
        includeRawResponse: false,
        includeArticleMetadata: false,
        includeUsageMetrics: false,
        includeYamlFrontmatter: false,
      },
    });

    const patched = await patchExtensionSettings({
      lastKnownModels: ['gemini-2.5-flash', 'gemini-2.5-pro'],
    });

    expect(patched).toEqual({
      apiBaseUrl: 'http://127.0.0.1:9000',
      defaultModel: 'gemini-2.5-flash',
      sharedSystemPrompt: '',
      lastKnownModels: ['gemini-2.5-flash', 'gemini-2.5-pro'],
      uiLanguage: 'en',
      articleCache: {
        enableAutoCreate: true,
      },
      markdownExport: {
        includeExplanation: true,
        includeSelections: false,
        includeRawResponse: false,
        includeArticleMetadata: false,
        includeUsageMetrics: false,
        includeYamlFrontmatter: false,
      },
    } satisfies ExtensionSettings);
  });

  it('patches markdownExport fields without resetting other export toggles', async () => {
    await saveExtensionSettings({
      markdownExport: {
        includeExplanation: false,
        includeSelections: true,
        includeRawResponse: true,
        includeArticleMetadata: true,
        includeUsageMetrics: false,
        includeYamlFrontmatter: false,
      },
    });

    const patched = await patchExtensionSettings({
      markdownExport: {
        includeUsageMetrics: true,
      },
    });

    expect(patched.markdownExport).toEqual({
      includeExplanation: false,
      includeSelections: true,
      includeRawResponse: true,
      includeArticleMetadata: true,
      includeUsageMetrics: true,
      includeYamlFrontmatter: false,
    });
  });

  it('preserves sharedSystemPrompt exactly as entered', async () => {
    const settings = await saveExtensionSettings({
      sharedSystemPrompt: '  Keep leading and trailing spaces.\nLine two.  ',
    });

    expect(settings.sharedSystemPrompt).toBe(
      '  Keep leading and trailing spaces.\nLine two.  '
    );
  });

  it('patches articleCache fields without resetting markdownExport toggles', async () => {
    await saveExtensionSettings({
      articleCache: {
        enableAutoCreate: true,
      },
      markdownExport: {
        includeExplanation: false,
        includeSelections: true,
        includeRawResponse: true,
        includeArticleMetadata: true,
        includeUsageMetrics: false,
        includeYamlFrontmatter: false,
      },
    });

    const patched = await patchExtensionSettings({
      articleCache: {
        enableAutoCreate: false,
      },
    });

    expect(patched.articleCache).toEqual({
      enableAutoCreate: false,
    });
    expect(patched.markdownExport).toEqual({
      includeExplanation: false,
      includeSelections: true,
      includeRawResponse: true,
      includeArticleMetadata: true,
      includeUsageMetrics: false,
      includeYamlFrontmatter: false,
    });
  });

  it('upgrades legacy settings objects without markdownExport', async () => {
    const chromeMock = getChromeMock();
    chromeMock.storage.local.set(
      {
        [EXTENSION_SETTINGS_STORAGE_KEY]: {
          apiBaseUrl: 'http://localhost:8010/',
          defaultModel: ' gemini-2.5-flash ',
          lastKnownModels: ['gemini-2.5-flash'],
        },
      },
      () => undefined
    );

    const settings = await loadExtensionSettings();

    expect(settings).toEqual({
      apiBaseUrl: 'http://localhost:8010',
      defaultModel: 'gemini-2.5-flash',
      sharedSystemPrompt: '',
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
  });

  it('detects ja as the default UI language when storage is empty', async () => {
    const chromeMock = getChromeMock();
    chromeMock.i18n.getUILanguage.mockReturnValue('ja-JP');

    const settings = await loadExtensionSettings();

    expect(settings.uiLanguage).toBe('ja');
  });

  it.each(['en-US', 'fr-FR', ''])(
    'falls back to en for unsupported locale %s',
    async (locale) => {
      const chromeMock = getChromeMock();
      chromeMock.i18n.getUILanguage.mockReturnValue(locale);

      const settings = await loadExtensionSettings();

      expect(settings.uiLanguage).toBe('en');
    }
  );

  it('falls back to en when getUILanguage throws', async () => {
    const chromeMock = getChromeMock();
    chromeMock.i18n.getUILanguage.mockImplementation(() => {
      throw new Error('i18n unavailable');
    });

    const settings = await loadExtensionSettings();

    expect(settings.uiLanguage).toBe('en');
  });

  it('does not re-detect locale when stored uiLanguage is null', async () => {
    const chromeMock = getChromeMock();
    chromeMock.i18n.getUILanguage.mockReturnValue('ja-JP');
    chromeMock.storage.local.set(
      {
        [EXTENSION_SETTINGS_STORAGE_KEY]: {
          apiBaseUrl: 'http://localhost:8010/',
          uiLanguage: null,
        },
      },
      () => undefined
    );

    const settings = await loadExtensionSettings();

    expect(settings.uiLanguage).toBe('en');
  });
});