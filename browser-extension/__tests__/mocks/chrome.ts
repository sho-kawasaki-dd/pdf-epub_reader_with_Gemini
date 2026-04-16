import { vi } from 'vitest';

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

  return {
    tabs: {
      captureVisibleTab: vi.fn(),
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
    commands: {
      onCommand: createEventHook(),
    },
    contextMenus: {
      create: vi.fn(),
      removeAll: vi.fn(),
      onClicked: createEventHook(),
    },
    storage: {
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
    },
  } as unknown as typeof chrome;
}

export function getChromeMock(): ReturnType<typeof createChromeMock> {
  return globalThis.chrome as unknown as ReturnType<typeof createChromeMock>;
}
