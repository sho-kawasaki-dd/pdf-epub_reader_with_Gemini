import type {
  AnalysisAction,
  ArticleContext,
  ModelOption,
  SelectionSessionItem,
} from '../../shared/contracts/messages';

export interface SelectionAnalysisSession {
  items: SelectionSessionItem[];
  modelOptions: ModelOption[];
  lastAction: AnalysisAction;
  lastModelName?: string;
  lastCustomPrompt?: string;
  articleContext?: ArticleContext;
  articleContextError?: string;
}

const SESSION_STORAGE_KEY_PREFIX = 'gem-read.analysis-session.';
const sessionStore = new Map<number, SelectionAnalysisSession>();

export async function getAnalysisSession(
  tabId: number
): Promise<SelectionAnalysisSession | undefined> {
  const cachedSession = sessionStore.get(tabId);
  if (cachedSession) {
    return cloneSession(cachedSession);
  }

  const storedSession = await storageSessionGet<SelectionAnalysisSession>(
    getSessionStorageKey(tabId)
  );
  if (!storedSession) {
    return undefined;
  }

  const normalizedSession = cloneSession(storedSession);
  sessionStore.set(tabId, normalizedSession);
  return cloneSession(normalizedSession);
}

export async function setAnalysisSession(
  tabId: number,
  session: SelectionAnalysisSession
): Promise<void> {
  const normalizedSession = cloneSession(session);
  sessionStore.set(tabId, normalizedSession);
  await storageSessionSet({
    [getSessionStorageKey(tabId)]: normalizedSession,
  });
}

export async function clearAnalysisSession(tabId: number): Promise<void> {
  sessionStore.delete(tabId);
  await storageSessionRemove(getSessionStorageKey(tabId));
}

export function getLatestSelectionItem(
  session: SelectionAnalysisSession
): SelectionSessionItem | undefined {
  return session.items.at(-1);
}

function getSessionStorageKey(tabId: number): string {
  return `${SESSION_STORAGE_KEY_PREFIX}${tabId}`;
}

function cloneSession(session: SelectionAnalysisSession): SelectionAnalysisSession {
  return {
    ...session,
    items: session.items.map((item) => ({
      ...item,
      selection: {
        ...item.selection,
        rect: { ...item.selection.rect },
      },
    })),
    modelOptions: session.modelOptions.map((modelOption) => ({
      ...modelOption,
    })),
    articleContext: session.articleContext
      ? {
          ...session.articleContext,
        }
      : undefined,
  };
}

async function storageSessionGet<T>(key: string): Promise<T | undefined> {
  const storageArea = getStorageSessionArea();

  return new Promise<T | undefined>((resolve, reject) => {
    storageArea.get(key, (items) => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }

      resolve(items[key] as T | undefined);
    });
  });
}

async function storageSessionSet(items: Record<string, unknown>): Promise<void> {
  const storageArea = getStorageSessionArea();

  return new Promise<void>((resolve, reject) => {
    storageArea.set(items, () => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }

      resolve();
    });
  });
}

async function storageSessionRemove(key: string): Promise<void> {
  const storageArea = getStorageSessionArea();

  return new Promise<void>((resolve, reject) => {
    storageArea.remove(key, () => {
      const lastError = chrome.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }

      resolve();
    });
  });
}

function getStorageSessionArea(): chrome.storage.StorageArea {
  if (chrome.storage.session) {
    return chrome.storage.session;
  }

  throw new Error('chrome.storage.session is unavailable.');
}
