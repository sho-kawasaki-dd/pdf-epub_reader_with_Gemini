import {
  DEFAULT_EXTENSION_SETTINGS,
  EXTENSION_SETTINGS_STORAGE_KEY,
  mergeExtensionSettings,
  type ExtensionSettingsInput,
  type ExtensionSettings,
} from '../config/phase0';

/**
 * Popup と background が同じ保存形式を共有できるよう、storage への入出力はこの module に閉じ込める。
 * mergeExtensionSettings を必ず通すことで、古い保存値でも最新の既定値へ安全に寄せられる。
 */
export async function loadExtensionSettings(): Promise<ExtensionSettings> {
  const storedValue = await getFromStorage<ExtensionSettingsInput>(
    EXTENSION_SETTINGS_STORAGE_KEY
  );
  return mergeExtensionSettings(storedValue);
}

export async function saveExtensionSettings(
  settings: ExtensionSettingsInput
): Promise<ExtensionSettings> {
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
