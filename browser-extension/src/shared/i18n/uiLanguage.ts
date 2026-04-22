import type { UiLanguage } from '../config/phase0';

export function normalizeUiLanguage(
  value: string | null | undefined
): UiLanguage {
  const normalized = value?.trim().toLowerCase();
  if (normalized?.startsWith('ja')) {
    return 'ja';
  }

  return 'en';
}

export function detectDefaultUiLanguage(): UiLanguage {
  try {
    return normalizeUiLanguage(chrome.i18n?.getUILanguage?.());
  } catch {
    return 'en';
  }
}