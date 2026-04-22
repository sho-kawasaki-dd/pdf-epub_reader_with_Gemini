import { vi } from 'vitest';

// Event target ごとの add/remove 呼び出し確認だけを行う軽量 hook。
function createEventHook() {
  return {
    addListener: vi.fn(),
    removeListener: vi.fn(),
    hasListener: vi.fn(),
  };
}

export function createChromeMock(): typeof chrome {
  // storage を含む最小 mock を共有し、suite ごとの ad hoc 実装差を避ける。
  const storageLocalState: Record<string, unknown> = {};
  const storageSessionState: Record<string, unknown> = {};

  return {
    tabs: {
      captureVisibleTab: vi.fn(),
      get: vi.fn(),
      onUpdated: createEventHook(),
      onRemoved: createEventHook(),
      query: vi.fn(),
      sendMessage: vi.fn(),
    },
    runtime: {
      lastError: undefined,
      onInstalled: createEventHook(),
      onMessage: createEventHook(),
      onStartup: createEventHook(),
      sendMessage: vi.fn(),
    },
    i18n: {
      getUILanguage: vi.fn(() => 'en-US'),
    },
    commands: {
      onCommand: createEventHook(),
    },
    contextMenus: {
      create: vi.fn(),
      removeAll: vi.fn(),
      onClicked: createEventHook(),
    },
    downloads: {
      download: vi.fn(),
    },
    storage: {
      onChanged: createEventHook(),
      local: {
        get: vi.fn(
          (
            keys: string | string[] | Record<string, unknown> | null,
            callback: (items: Record<string, unknown>) => void
          ) => {
            if (typeof keys === 'string') {
              callback({ [keys]: storageLocalState[keys] });
              return;
            }

            if (Array.isArray(keys)) {
              const items: Record<string, unknown> = {};
              for (const key of keys) {
                items[key] = storageLocalState[key];
              }
              callback(items);
              return;
            }

            if (keys && typeof keys === 'object') {
              const items: Record<string, unknown> = {};
              for (const key of Object.keys(keys)) {
                items[key] = storageLocalState[key] ?? keys[key];
              }
              callback(items);
              return;
            }

            callback({ ...storageLocalState });
          }
        ),
        set: vi.fn((items: Record<string, unknown>, callback?: () => void) => {
          Object.assign(storageLocalState, items);
          callback?.();
        }),
        remove: vi.fn((keys: string | string[], callback?: () => void) => {
          const keyList = Array.isArray(keys) ? keys : [keys];
          for (const key of keyList) {
            delete storageLocalState[key];
          }
          callback?.();
        }),
        clear: vi.fn((callback?: () => void) => {
          for (const key of Object.keys(storageLocalState)) {
            delete storageLocalState[key];
          }
          callback?.();
        }),
      },
      session: {
        get: vi.fn(
          (
            keys: string | string[] | Record<string, unknown> | null,
            callback: (items: Record<string, unknown>) => void
          ) => {
            if (typeof keys === 'string') {
              callback({ [keys]: storageSessionState[keys] });
              return;
            }

            if (Array.isArray(keys)) {
              const items: Record<string, unknown> = {};
              for (const key of keys) {
                items[key] = storageSessionState[key];
              }
              callback(items);
              return;
            }

            if (keys && typeof keys === 'object') {
              const items: Record<string, unknown> = {};
              for (const key of Object.keys(keys)) {
                items[key] = storageSessionState[key] ?? keys[key];
              }
              callback(items);
              return;
            }

            callback({ ...storageSessionState });
          }
        ),
        set: vi.fn((items: Record<string, unknown>, callback?: () => void) => {
          Object.assign(storageSessionState, items);
          callback?.();
        }),
        remove: vi.fn((keys: string | string[], callback?: () => void) => {
          const keyList = Array.isArray(keys) ? keys : [keys];
          for (const key of keyList) {
            delete storageSessionState[key];
          }
          callback?.();
        }),
        clear: vi.fn((callback?: () => void) => {
          for (const key of Object.keys(storageSessionState)) {
            delete storageSessionState[key];
          }
          callback?.();
        }),
      },
    },
  } as unknown as typeof chrome;
}

export function getChromeMock(): ReturnType<typeof createChromeMock> {
  return globalThis.chrome as unknown as ReturnType<typeof createChromeMock>;
}
