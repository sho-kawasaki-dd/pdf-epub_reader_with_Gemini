import { describe, expect, it } from 'vitest';

import {
  canAppendSelectionBatchItem,
  clearSelectionBatch,
  getSelectionBatchCapacity,
  getSelectionBatchSnapshot,
  syncSelectionBatch,
} from '../../../src/content/selection/selectionBatchController';

describe('selectionBatchController', () => {
  it('tracks the mirrored batch items and reports capacity', () => {
    clearSelectionBatch();
    syncSelectionBatch([
      {
        id: 'selection-1',
        source: 'text-selection',
        selection: {
          text: 'Selected paragraph',
          rect: { left: 1, top: 2, width: 3, height: 4 },
          viewportWidth: 100,
          viewportHeight: 100,
          devicePixelRatio: 1,
          url: 'https://example.com',
          pageTitle: 'Example',
        },
        includeImage: false,
        previewImageUrl: 'data:image/webp;base64,preview',
        cropDurationMs: 12,
      },
    ]);

    expect(getSelectionBatchSnapshot()).toHaveLength(1);
    expect(getSelectionBatchCapacity()).toEqual({ current: 1, max: 10 });
    expect(canAppendSelectionBatchItem()).toBe(true);
  });

  it('clears the mirrored batch items', () => {
    syncSelectionBatch([
      {
        id: 'selection-1',
        source: 'text-selection',
        selection: {
          text: 'Selected paragraph',
          rect: { left: 1, top: 2, width: 3, height: 4 },
          viewportWidth: 100,
          viewportHeight: 100,
          devicePixelRatio: 1,
          url: 'https://example.com',
          pageTitle: 'Example',
        },
        includeImage: false,
        previewImageUrl: 'data:image/webp;base64,preview',
        cropDurationMs: 12,
      },
    ]);

    clearSelectionBatch();

    expect(getSelectionBatchSnapshot()).toEqual([]);
    expect(getSelectionBatchCapacity()).toEqual({ current: 0, max: 10 });
  });
});