export const PHASE0_MENU_ID = 'gem-read-phase0-translate-test';
export const PHASE2_RECTANGLE_MENU_ID = 'gem-read-phase2-start-rectangle';
export const PHASE2_RECTANGLE_COMMAND_ID = 'gem-read-phase2-start-rectangle';
export const DEFAULT_LOCAL_API_PORT = 8000;
export const DEFAULT_LOCAL_API_BASE_URL = `http://127.0.0.1:${DEFAULT_LOCAL_API_PORT}`;
export const EXTENSION_SETTINGS_STORAGE_KEY = 'gem-read.settings';
export const LOCAL_API_BASE_URL_PATTERN = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/;
export const PHASE0_API_BASE_URL = DEFAULT_LOCAL_API_BASE_URL;
export const OUTPUT_IMAGE_TYPE = 'image/webp';
export const OUTPUT_IMAGE_QUALITY = 0.82;
export const OUTPUT_MAX_LONG_EDGE = 768;
export const MAX_SELECTION_SESSION_ITEMS = 10;

export interface ExtensionSettings {
	apiBaseUrl: string;
	defaultModel: string;
	lastKnownModels: string[];
}

export const DEFAULT_EXTENSION_SETTINGS: ExtensionSettings = {
	apiBaseUrl: DEFAULT_LOCAL_API_BASE_URL,
	defaultModel: '',
	lastKnownModels: [],
};

export function isValidLocalApiBaseUrl(value: string | null | undefined): boolean {
	const trimmed = value?.trim();
	if (!trimmed) {
		return false;
	}

	return LOCAL_API_BASE_URL_PATTERN.test(trimmed.replace(/\/$/, ''));
}

export function normalizeLocalApiBaseUrl(value: string | null | undefined): string {
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

export function normalizeModelList(models: readonly string[] | null | undefined): string[] {
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

export function mergeExtensionSettings(
	value: Partial<ExtensionSettings> | null | undefined,
): ExtensionSettings {
	return {
		apiBaseUrl: normalizeLocalApiBaseUrl(value?.apiBaseUrl),
		defaultModel: value?.defaultModel?.trim() ?? '',
		lastKnownModels: normalizeModelList(value?.lastKnownModels),
	};
}