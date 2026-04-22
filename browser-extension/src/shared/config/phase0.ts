/**
 * shared/config は runtime をまたいで参照される定数と設定 merge ルールを置く。
 * background/content/popup が別々に default や normalize を持たないようにして、設定解釈を 1 か所に固定する。
 */
export const PHASE0_MENU_ID = 'gem-read-phase0-translate-test';
export const PHASE2_RECTANGLE_MENU_ID = 'gem-read-phase2-start-rectangle';
export const PHASE2_RECTANGLE_COMMAND_ID = 'gem-read-phase2-start-rectangle';
export const PHASE3_OPEN_OVERLAY_COMMAND_ID = 'gem-read-phase3-open-overlay';
export const PHASE3_ADD_SELECTION_COMMAND_ID = 'gem-read-phase3-add-selection';
export const PHASE3_CLEAR_SELECTION_BATCH_COMMAND_ID =
  'gem-read-phase3-clear-selection-batch';
export const DEFAULT_LOCAL_API_PORT = 8000;
export const DEFAULT_LOCAL_API_BASE_URL = `http://127.0.0.1:${DEFAULT_LOCAL_API_PORT}`;
export const EXTENSION_SETTINGS_STORAGE_KEY = 'gem-read.settings';
export const LOCAL_API_BASE_URL_PATTERN =
  /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/;
export const PHASE0_API_BASE_URL = DEFAULT_LOCAL_API_BASE_URL;
export const OUTPUT_IMAGE_TYPE = 'image/webp';
export const OUTPUT_IMAGE_QUALITY = 0.82;
export const OUTPUT_MAX_LONG_EDGE = 768;
export const MAX_SELECTION_SESSION_ITEMS = 10;

export type UiLanguage = 'ja' | 'en';

export interface MarkdownExportSettings {
  includeExplanation: boolean;
  includeSelections: boolean;
  includeRawResponse: boolean;
  includeArticleMetadata: boolean;
  includeUsageMetrics: boolean;
  includeYamlFrontmatter: boolean;
}

export interface ArticleCacheSettings {
  enableAutoCreate: boolean;
}

/**
 * popup で保存する永続設定の canonical shape。
 * 各 runtime は storage から生値を直接解釈せず、この shape へ正規化された値だけを使う。
 */
export interface ExtensionSettings {
  apiBaseUrl: string;
  defaultModel: string;
  sharedSystemPrompt: string;
  lastKnownModels: string[];
  uiLanguage: UiLanguage;
  articleCache: ArticleCacheSettings;
  markdownExport: MarkdownExportSettings;
}

/**
 * storage から復元した未完成な値や旧バージョン設定を受けるための入力 shape。
 * backward compatibility は merge 関数側で吸収し、呼び出し側へ欠損処理を漏らさない。
 */
export interface ExtensionSettingsInput {
  apiBaseUrl?: string | null;
  defaultModel?: string | null;
  sharedSystemPrompt?: string | null;
  lastKnownModels?: readonly string[] | null;
  uiLanguage?: UiLanguage | null;
  articleCache?: Partial<ArticleCacheSettings> | null;
  markdownExport?: Partial<MarkdownExportSettings> | null;
}

export const DEFAULT_ARTICLE_CACHE_SETTINGS: ArticleCacheSettings = {
  enableAutoCreate: true,
};

export const DEFAULT_MARKDOWN_EXPORT_SETTINGS: MarkdownExportSettings = {
  includeExplanation: true,
  includeSelections: true,
  includeRawResponse: false,
  includeArticleMetadata: false,
  includeUsageMetrics: false,
  includeYamlFrontmatter: false,
};

export const DEFAULT_EXTENSION_SETTINGS: ExtensionSettings = {
  apiBaseUrl: DEFAULT_LOCAL_API_BASE_URL,
  defaultModel: '',
  sharedSystemPrompt: '',
  lastKnownModels: [],
  uiLanguage: 'en',
  articleCache: { ...DEFAULT_ARTICLE_CACHE_SETTINGS },
  markdownExport: { ...DEFAULT_MARKDOWN_EXPORT_SETTINGS },
};

function normalizeStoredUiLanguage(
  value: UiLanguage | null | undefined
): UiLanguage {
  return value === 'ja' || value === 'en'
    ? value
    : DEFAULT_EXTENSION_SETTINGS.uiLanguage;
}

export function isValidLocalApiBaseUrl(
  value: string | null | undefined
): boolean {
  const trimmed = value?.trim();
  if (!trimmed) {
    return false;
  }

  return LOCAL_API_BASE_URL_PATTERN.test(trimmed.replace(/\/$/, ''));
}

export function normalizeLocalApiBaseUrl(
  value: string | null | undefined
): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    return DEFAULT_LOCAL_API_BASE_URL;
  }

  const normalized = trimmed.replace(/\/$/, '');

  if (!LOCAL_API_BASE_URL_PATTERN.test(normalized)) {
    return DEFAULT_LOCAL_API_BASE_URL;
  }

  return normalized;
}

export function normalizeModelList(
  models: readonly string[] | null | undefined
): string[] {
  if (!models) {
    return [];
  }

  const normalizedModels: string[] = [];
  for (const modelName of models) {
    const trimmed = modelName.trim();
    if (!trimmed || normalizedModels.includes(trimmed)) {
      continue;
    }
    normalizedModels.push(trimmed);
  }

  return normalizedModels;
}

export function mergeMarkdownExportSettings(
  value: Partial<MarkdownExportSettings> | null | undefined
): MarkdownExportSettings {
  return {
    includeExplanation:
      value?.includeExplanation ??
      DEFAULT_MARKDOWN_EXPORT_SETTINGS.includeExplanation,
    includeSelections:
      value?.includeSelections ??
      DEFAULT_MARKDOWN_EXPORT_SETTINGS.includeSelections,
    includeRawResponse:
      value?.includeRawResponse ??
      DEFAULT_MARKDOWN_EXPORT_SETTINGS.includeRawResponse,
    includeArticleMetadata:
      value?.includeArticleMetadata ??
      DEFAULT_MARKDOWN_EXPORT_SETTINGS.includeArticleMetadata,
    includeUsageMetrics:
      value?.includeUsageMetrics ??
      DEFAULT_MARKDOWN_EXPORT_SETTINGS.includeUsageMetrics,
    includeYamlFrontmatter:
      value?.includeYamlFrontmatter ??
      DEFAULT_MARKDOWN_EXPORT_SETTINGS.includeYamlFrontmatter,
  };
}

export function mergeArticleCacheSettings(
  value: Partial<ArticleCacheSettings> | null | undefined
): ArticleCacheSettings {
  return {
    enableAutoCreate:
      value?.enableAutoCreate ??
      DEFAULT_ARTICLE_CACHE_SETTINGS.enableAutoCreate,
  };
}

export function mergeExtensionSettings(
  value: ExtensionSettingsInput | null | undefined
): ExtensionSettings {
  // storage 由来の部分値をここで吸収して、各 runtime では完全形だけを扱う。
  return {
    apiBaseUrl: normalizeLocalApiBaseUrl(value?.apiBaseUrl),
    defaultModel: value?.defaultModel?.trim() ?? '',
    sharedSystemPrompt: value?.sharedSystemPrompt ?? '',
    lastKnownModels: normalizeModelList(value?.lastKnownModels),
    uiLanguage: normalizeStoredUiLanguage(value?.uiLanguage),
    articleCache: mergeArticleCacheSettings(value?.articleCache),
    markdownExport: mergeMarkdownExportSettings(value?.markdownExport),
  };
}
