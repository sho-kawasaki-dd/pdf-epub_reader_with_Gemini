import { MAX_SELECTION_SESSION_ITEMS } from '../../shared/config/phase0';
import type { UiLanguage } from '../../shared/config/phase0';
import type {
  AnalysisAction,
  AppendSessionItemResponse,
  DeleteActiveArticleCacheResponse,
  ExportMarkdownPayload,
  ExportMarkdownResponse,
  OverlayPayload,
  RemoveSessionItemResponse,
  RunOverlayActionMessage,
  RunOverlayActionResponse,
  SelectionSessionItem,
  ToggleSessionItemImageResponse,
} from '../../shared/contracts/messages';
import { t } from '../../shared/i18n/translator';
import { canAppendSelectionBatchItem } from '../selection/selectionBatchController';
import { collectSelection } from '../selection/snapshotStore';

/**
 * overlay の button handler は privileged 処理を自前で持たず、background へ message を送る薄い adapter に留める。
 * こうしておくと UI 側は DOM エラー表示に集中でき、session mutation や Local API 呼び出しは background へ閉じ込められる。
 */
export async function runOverlayAction(
  action: AnalysisAction,
  modelName: string,
  customPrompt: string,
  uiLanguage: UiLanguage,
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  if (action === 'custom_prompt' && customPrompt.trim().length === 0) {
    errorBox.textContent = t(uiLanguage, 'overlayErrorCustomPromptEmpty');
    errorSection.hidden = false;
    return;
  }

  const message: RunOverlayActionMessage = {
    type: 'phase1.runOverlayAction',
    payload: {
      action,
      modelName: modelName.trim() || undefined,
      customPrompt:
        action === 'custom_prompt' ? customPrompt.trim() : undefined,
    },
  };

  // Overlay は privileged 処理を持たず、実行そのものは background に委譲する。
  const response = (await chrome.runtime.sendMessage(message)) as
    | RunOverlayActionResponse
    | undefined;
  if (response && !response.ok) {
    errorBox.textContent =
      response.error ?? t(uiLanguage, 'overlayErrorActionFailed');
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

export async function addCurrentSelection(
  errorBox: HTMLElement,
  errorSection: HTMLElement,
  payload: OverlayPayload
): Promise<void> {
  if (!canAppendSelectionBatchItem()) {
    errorBox.textContent = t(
      payload.uiLanguage ?? 'en',
      'overlayErrorBatchLimit',
      {
        count: payload.maxSessionItems ?? MAX_SELECTION_SESSION_ITEMS,
      }
    );
    errorSection.hidden = false;
    return;
  }

  const selection = collectSelection();
  if (!selection.ok || !selection.payload) {
    errorBox.textContent =
      selection.error ??
      t(payload.uiLanguage ?? 'en', 'overlayErrorSelectionRequired');
    errorSection.hidden = false;
    return;
  }

  const response = (await chrome.runtime.sendMessage({
    type: 'phase2.appendSessionItem',
    payload: {
      selection: selection.payload,
      source: 'text-selection',
    },
  })) as AppendSessionItemResponse | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ?? t(payload.uiLanguage ?? 'en', 'overlayErrorAddSelection');
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

export async function removeSelectionItem(
  itemId: string,
  uiLanguage: UiLanguage,
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: 'phase2.removeSessionItem',
    payload: { itemId },
  })) as RemoveSessionItemResponse | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ?? t(uiLanguage, 'overlayErrorRemoveSelection');
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

export async function toggleSelectionItemImage(
  itemId: string,
  includeImage: boolean,
  uiLanguage: UiLanguage,
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: 'phase2.toggleSessionItemImage',
    payload: { itemId, includeImage },
  })) as ToggleSessionItemImageResponse | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ?? t(uiLanguage, 'overlayErrorToggleImage');
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

export async function deleteActiveArticleCache(
  uiLanguage: UiLanguage,
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: 'phase4.deleteActiveArticleCache',
  })) as DeleteActiveArticleCacheResponse | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ?? t(uiLanguage, 'overlayErrorDeleteCache');
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

export async function exportCurrentMarkdown(
  payload: OverlayPayload,
  sessionItems: SelectionSessionItem[],
  selectedText: string,
  uiLanguage: UiLanguage,
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  const exportPayload = buildExportMarkdownPayload(
    payload,
    sessionItems,
    selectedText
  );
  const response = (await chrome.runtime.sendMessage({
    type: 'phase5.exportMarkdown',
    payload: exportPayload,
  })) as ExportMarkdownResponse | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ?? t(uiLanguage, 'overlayErrorExport');
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

function buildExportMarkdownPayload(
  payload: OverlayPayload,
  sessionItems: SelectionSessionItem[],
  selectedText: string
): ExportMarkdownPayload {
  const latestSelection = sessionItems.at(-1)?.selection;

  // export は overlay の表示内容を再構成せず、その時点の payload と batch snapshot をそのまま background へ渡す。
  return {
    action: payload.action ?? 'translation',
    modelName: payload.modelName,
    translatedText: payload.translatedText,
    explanation: payload.explanation,
    rawResponse: payload.rawResponse,
    selectedText: selectedText.trim() || undefined,
    sessionItems,
    articleContext: payload.articleContext,
    usage: payload.usage,
    pageTitle:
      latestSelection?.pageTitle?.trim() ||
      payload.articleContext?.title?.trim() ||
      document.title ||
      'Gem Read Export',
    pageUrl:
      latestSelection?.url?.trim() ||
      payload.articleContext?.url?.trim() ||
      window.location.href,
  };
}
