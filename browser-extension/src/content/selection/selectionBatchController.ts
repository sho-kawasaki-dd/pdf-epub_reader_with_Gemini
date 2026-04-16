import { MAX_SELECTION_SESSION_ITEMS } from '../../shared/config/phase0';
import type { SelectionSessionItem } from '../../shared/contracts/messages';

let sessionItems: SelectionSessionItem[] = [];

export function syncSelectionBatch(
  items: SelectionSessionItem[] | undefined
): SelectionSessionItem[] {
  sessionItems = (items ?? []).map((item) => ({ ...item }));
  return getSelectionBatchSnapshot();
}

export function getSelectionBatchSnapshot(): SelectionSessionItem[] {
  return sessionItems.map((item) => ({ ...item }));
}

export function clearSelectionBatch(): void {
  sessionItems = [];
}

export function canAppendSelectionBatchItem(): boolean {
  return sessionItems.length < MAX_SELECTION_SESSION_ITEMS;
}

export function getSelectionBatchCapacity(): {
  current: number;
  max: number;
} {
  return {
    current: sessionItems.length,
    max: MAX_SELECTION_SESSION_ITEMS,
  };
}