import {
  PHASE0_MENU_ID,
  PHASE2_RECTANGLE_MENU_ID,
  type UiLanguage,
} from '../../shared/config/phase0';
import { t } from '../../shared/i18n/translator';

export async function ensurePhase0ContextMenu(
  uiLanguage: UiLanguage
): Promise<void> {
  await removeAllContextMenus();
  await createContextMenu({
    id: PHASE0_MENU_ID,
    title: t(uiLanguage, 'menuTranslate'),
    contexts: ['selection'],
  });
  await createContextMenu({
    id: PHASE2_RECTANGLE_MENU_ID,
    title: t(uiLanguage, 'menuRectangle'),
    contexts: ['page', 'image', 'video'],
  });
}

function removeAllContextMenus(): Promise<void> {
  return new Promise((resolve, reject) => {
    chrome.contextMenus.removeAll(() => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }
      resolve();
    });
  });
}

function createContextMenu(
  createProperties: chrome.contextMenus.CreateProperties
): Promise<void> {
  return new Promise((resolve, reject) => {
    chrome.contextMenus.create(createProperties, () => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }
      resolve();
    });
  });
}
