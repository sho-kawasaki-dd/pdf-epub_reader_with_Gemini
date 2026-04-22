import {
  DEFAULT_EXTENSION_SETTINGS,
  EXTENSION_SETTINGS_STORAGE_KEY,
  mergeExtensionSettings,
  type ExtensionSettingsInput,
  type ExtensionSettings,
} from '../config/phase0';
import { detectDefaultUiLanguage } from '../i18n/uiLanguage';

/**
 * Popup と background が同じ保存形式を共有できるよう、storage への入出力はこの module に閉じ込める。
 * mergeExtensionSettings を必ず通すことで、古い保存値でも最新の既定値へ安全に寄せられる。
 */
export async function loadExtensionSettings(): Promise<ExtensionSettings> {
  const storedValue = await getFromStorage<ExtensionSettingsInput>(
    EXTENSION_SETTINGS_STORAGE_KEY
  );
  const normalized = mergeExtensionSettings(storedValue);

  if (shouldDetectDefaultUiLanguage(storedValue)) {
    return {
      ...normalized,
      uiLanguage: detectDefaultUiLanguage(),
    };
  }

  return normalized;
}

export async function saveExtensionSettings(
  settings: ExtensionSettingsInput
): Promise<ExtensionSettings> {
  // 永続化前に normalize して、popup と background が常に同じ完全形を読むようにする。
  const normalizedSettings = mergeExtensionSettings(settings);
  await setInStorage(EXTENSION_SETTINGS_STORAGE_KEY, normalizedSettings);
  return normalizedSettings;
}

export async function patchExtensionSettings(
  patch: ExtensionSettingsInput
): Promise<ExtensionSettings> {
  const current = await loadExtensionSettings();
  // patch 保存でも未指定フィールドを落とさないよう、常に current と merge してから永続化する。
  const next = mergeExtensionSettings({
    ...current,
    ...patch,
    articleCache: {
      ...current.articleCache,
      ...patch.articleCache,
    },
    markdownExport: {
      ...current.markdownExport,
      ...patch.markdownExport,
    },
  });
  await setInStorage(EXTENSION_SETTINGS_STORAGE_KEY, next);
  return next;
}

export function getDefaultExtensionSettings(): ExtensionSettings {
  return {
    ...DEFAULT_EXTENSION_SETTINGS,
    // 配列を複製しておかないと、呼び出し元が既定値を破壊的に更新できてしまう。
    lastKnownModels: [...DEFAULT_EXTENSION_SETTINGS.lastKnownModels],
    articleCache: { ...DEFAULT_EXTENSION_SETTINGS.articleCache },
    markdownExport: { ...DEFAULT_EXTENSION_SETTINGS.markdownExport },
  };
}

function getFromStorage<T>(key: string): Promise<T | undefined> {
  return new Promise((resolve, reject) => {
    chrome.storage.local.get(key, (result) => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }

      resolve(result[key] as T | undefined);
    });
  });
}

function setInStorage<T>(key: string, value: T): Promise<void> {
  // storage API の callback 形を Promise に閉じ込め、呼び出し側では入出力の正規化だけへ集中させる。
  return new Promise((resolve, reject) => {
    chrome.storage.local.set({ [key]: value }, () => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }

      resolve();
    });
  });
}

function shouldDetectDefaultUiLanguage(
  storedValue: ExtensionSettingsInput | undefined
): boolean {
  if (storedValue === undefined) {
    return true;
  }

  return !Object.prototype.hasOwnProperty.call(storedValue, 'uiLanguage');
}
