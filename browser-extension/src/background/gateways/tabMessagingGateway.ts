import type {
  CollectSelectionMessage,
  ContentScriptMessage,
  OverlayPayload,
  RenderOverlayMessage,
  SelectionCaptureResponse,
} from '../../shared/contracts/messages';

export interface CollectSelectionOptions {
  liveOnly?: boolean;
}

export async function collectSelection(
  tabId: number,
  fallbackText: string,
  options: CollectSelectionOptions = {},
): Promise<SelectionCaptureResponse> {
  const message: CollectSelectionMessage = {
    type: 'phase0.collectSelection',
    fallbackText,
    liveOnly: options.liveOnly,
  };
  return chrome.tabs.sendMessage(tabId, message);
}

export async function renderOverlay(tabId: number, payload: OverlayPayload): Promise<void> {
  const message: RenderOverlayMessage = {
    type: 'phase0.renderOverlay',
    payload,
  };
  await chrome.tabs.sendMessage(tabId, message as ContentScriptMessage);
}