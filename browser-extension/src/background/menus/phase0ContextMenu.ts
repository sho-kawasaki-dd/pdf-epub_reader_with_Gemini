import {
  PHASE0_MENU_ID,
  PHASE2_RECTANGLE_MENU_ID,
} from '../../shared/config/phase0';

export async function ensurePhase0ContextMenu(): Promise<void> {
  await removeAllContextMenus();
  await createContextMenu({
    id: PHASE0_MENU_ID,
    title: 'Gem Read で翻訳',
    contexts: ['selection'],
  });
  await createContextMenu({
    id: PHASE2_RECTANGLE_MENU_ID,
    title: 'Gem Read で自由矩形選択を開始',
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
