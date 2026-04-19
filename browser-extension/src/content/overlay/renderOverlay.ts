import { MAX_SELECTION_SESSION_ITEMS } from '../../shared/config/phase0';
import type {
  AnalysisAction,
  AppendSessionItemResponse,
  BeginRectangleSelectionResponse,
  ClearOverlaySessionMessage,
  DeleteActiveArticleCacheResponse,
  OverlayPayload,
  RemoveSessionItemResponse,
  RunOverlayActionMessage,
  RunOverlayActionResponse,
  SelectionSessionItem,
  ToggleSessionItemImageResponse,
} from '../../shared/contracts/messages';
import { renderRichText, RICH_TEXT_STYLE_BLOCK } from './richTextRenderer';
import {
  isRectangleSelectionActive,
  startRectangleSelection,
} from '../selection/rectangleSelectionController';
import {
  canAppendSelectionBatchItem,
  clearSelectionBatch,
  getSelectionBatchCapacity,
  getSelectionBatchSnapshot,
  syncSelectionBatch,
} from '../selection/selectionBatchController';
import { collectSelection } from '../selection/snapshotStore';

const OVERLAY_HOST_ID = 'gem-read-phase0-overlay-host';
type OverlayTabId = 'workspace' | 'gemini';

// minimize 状態と draft 入力は再描画を跨いで維持したいので module state に置く。
let isOverlayMinimized = false;
let draftModelName = '';
let draftCustomPrompt = '';
let isRectangleModeActive = false;
let isRawResponseExpanded = false;
let activeOverlayTab: OverlayTabId = 'workspace';
let currentOverlayPayload: OverlayPayload | null = null;
let keyboardHandlerAttached = false;

/**
 * Overlay は content script 側で一元管理し、payload から都度 DOM を再構築する。
 * こうしておくと background から渡る状態だけで表示を復元でき、ページ本体の DOM 状態に依存しにくい。
 */
export function renderOverlay(payload: OverlayPayload): void {
  const previousPayload = currentOverlayPayload;

  if (payload.launcherOnly !== undefined) {
    isOverlayMinimized = payload.launcherOnly;
  }

  const sessionItems = syncSelectionBatch(payload.sessionItems);
  const maxSessionItems =
    payload.maxSessionItems ?? MAX_SELECTION_SESSION_ITEMS;
  const effectivePayload: OverlayPayload = {
    ...payload,
    launcherOnly: undefined,
  };

  if (shouldAutoOpenGeminiTab(previousPayload, effectivePayload)) {
    activeOverlayTab = 'gemini';
    isOverlayMinimized = false;
  }

  currentOverlayPayload = effectivePayload;

  if (
    payload.modelName !== undefined &&
    (!payload.preserveDrafts || draftModelName.length === 0)
  ) {
    draftModelName = payload.modelName;
  }
  if (
    payload.customPrompt !== undefined &&
    (!payload.preserveDrafts || draftCustomPrompt.length === 0)
  ) {
    draftCustomPrompt = payload.customPrompt;
  }

  const root = ensureOverlayRoot();
  ensureKeyboardHandler();
  root.innerHTML = isOverlayMinimized
    ? renderLauncherMarkup(effectivePayload)
    : renderPanelMarkup(effectivePayload, sessionItems, maxSessionItems);

  if (isOverlayMinimized) {
    const launcherButton =
      root.querySelector<HTMLButtonElement>('.launcher-button');
    const closeButton =
      root.querySelector<HTMLButtonElement>('.launcher-close');
    launcherButton?.addEventListener('click', () => {
      isOverlayMinimized = false;
      if (currentOverlayPayload) {
        renderOverlay(currentOverlayPayload);
      }
    });
    closeButton?.addEventListener('click', () => {
      void closeOverlay();
    });
    return;
  }

  const selectionBox = root.querySelector<HTMLElement>('.selection-box');
  const previewSection = root.querySelector<HTMLElement>('.preview-section');
  const previewImage = root.querySelector<HTMLImageElement>('.preview-image');
  const resultSection = root.querySelector<HTMLElement>('.result-section');
  const resultLabel = root.querySelector<HTMLElement>('.result-label');
  const resultBox = root.querySelector<HTMLElement>('.result-box');
  const explanationSection = root.querySelector<HTMLElement>(
    '.explanation-section'
  );
  const explanationBox = root.querySelector<HTMLElement>('.explanation-box');
  const rawSection = root.querySelector<HTMLElement>('.raw-section');
  const rawDetails = root.querySelector<HTMLDetailsElement>('.raw-details');
  const rawBox = root.querySelector<HTMLElement>('.raw-box');
  const errorSection = root.querySelector<HTMLElement>('.error-section');
  const errorBox = root.querySelector<HTMLElement>('.error-box');
  const metaBox = root.querySelector<HTMLElement>('.meta-box');
  const closeButton = root.querySelector<HTMLButtonElement>('.close');
  const minimizeButton = root.querySelector<HTMLButtonElement>('.minimize');
  const modelInput = root.querySelector<HTMLInputElement>('.model-input');
  const modelDatalist = root.querySelector<HTMLDataListElement>('.model-list');
  const customPromptInput = root.querySelector<HTMLTextAreaElement>(
    '.custom-prompt-input'
  );
  const customButton = root.querySelector<HTMLButtonElement>('.action-custom');
  const deleteArticleCacheButton = root.querySelector<HTMLButtonElement>(
    '.action-delete-article-cache'
  );
  const addSelectionButton = root.querySelector<HTMLButtonElement>(
    '.action-add-selection'
  );
  const addRectangleButton = root.querySelector<HTMLButtonElement>(
    '.action-add-rectangle'
  );
  const batchHint = root.querySelector<HTMLElement>('.batch-hint');
  const translationButton = root.querySelector<HTMLButtonElement>(
    '.action-translation'
  );
  const explanationButton = root.querySelector<HTMLButtonElement>(
    '.action-explanation'
  );
  const actionHint = root.querySelector<HTMLElement>('.action-hint');
  const bannerSection = root.querySelector<HTMLElement>('.banner-section');
  const bannerBox = root.querySelector<HTMLElement>('.banner-box');
  const workspaceTabButton = root.querySelector<HTMLButtonElement>(
    '.panel-tab[data-tab-id="workspace"]'
  );
  const geminiTabButton = root.querySelector<HTMLButtonElement>(
    '.panel-tab[data-tab-id="gemini"]'
  );
  const workspacePanel = root.querySelector<HTMLElement>(
    '.panel-tabpanel--workspace'
  );
  const geminiPanel = root.querySelector<HTMLElement>(
    '.panel-tabpanel--gemini'
  );
  const geminiEmptyState = root.querySelector<HTMLElement>(
    '.gemini-empty-state'
  );

  if (
    !selectionBox ||
    !previewSection ||
    !previewImage ||
    !resultSection ||
    !resultLabel ||
    !resultBox ||
    !explanationSection ||
    !explanationBox ||
    !rawSection ||
    !rawDetails ||
    !rawBox ||
    !errorSection ||
    !errorBox ||
    !metaBox ||
    !closeButton ||
    !minimizeButton ||
    !modelInput ||
    !modelDatalist ||
    !customPromptInput ||
    !customButton ||
    !addSelectionButton ||
    !addRectangleButton ||
    !batchHint ||
    !translationButton ||
    !explanationButton ||
    !actionHint ||
    !bannerSection ||
    !bannerBox ||
    !workspaceTabButton ||
    !geminiTabButton ||
    !workspacePanel ||
    !geminiPanel ||
    !geminiEmptyState
  ) {
    return;
  }

  const latestSessionItem = sessionItems.at(-1);
  const selectionText =
    effectivePayload.selectedText || buildSelectionText(sessionItems);
  const previewImageUrl =
    effectivePayload.previewImageUrl ?? latestSessionItem?.previewImageUrl;

  selectionBox.textContent = selectionText || 'No selection text captured.';

  previewSection.hidden = !previewImageUrl;
  if (previewImageUrl) {
    previewImage.src = previewImageUrl;
  }

  resultSection.hidden = !effectivePayload.translatedText;
  resultLabel.textContent = getResultLabel(effectivePayload.action);
  renderRichText(resultBox, effectivePayload.translatedText || '');

  explanationSection.hidden = !effectivePayload.explanation;
  renderRichText(explanationBox, effectivePayload.explanation || '');

  rawSection.hidden = !effectivePayload.rawResponse;
  rawBox.textContent = effectivePayload.rawResponse || '';
  rawDetails.open =
    Boolean(effectivePayload.rawResponse) && isRawResponseExpanded;

  errorSection.hidden = !effectivePayload.error;
  errorBox.textContent = effectivePayload.error || '';

  bannerSection.hidden = !shouldShowBanner(effectivePayload);
  bannerBox.textContent = buildBannerText(effectivePayload);

  const hasGeminiContent = overlayHasGeminiContent(effectivePayload);
  const geminiTabEnabled = isGeminiTabEnabled(
    effectivePayload,
    activeOverlayTab
  );
  workspacePanel.hidden = activeOverlayTab !== 'workspace';
  geminiPanel.hidden = activeOverlayTab !== 'gemini';
  configureOverlayTabButton(workspaceTabButton, 'workspace', true);
  configureOverlayTabButton(geminiTabButton, 'gemini', geminiTabEnabled);
  geminiEmptyState.hidden = hasGeminiContent;
  geminiEmptyState.textContent = buildGeminiEmptyStateText(effectivePayload);

  modelInput.value = draftModelName;
  modelDatalist.innerHTML = (effectivePayload.modelOptions ?? [])
    .map(
      (model) =>
        `<option value="${escapeHtml(model.modelId)}">${escapeHtml(model.displayName)}</option>`
    )
    .join('');
  customPromptInput.value = draftCustomPrompt;

  // cached session がない段階で action を押しても再利用できる selection がないため、button を閉じておく。
  const actionsEnabled =
    Boolean(effectivePayload.sessionReady) &&
    effectivePayload.status !== 'loading';
  translationButton.disabled = !actionsEnabled;
  explanationButton.disabled = !actionsEnabled;
  customButton.disabled =
    !actionsEnabled || customPromptInput.value.trim().length === 0;
  addSelectionButton.disabled =
    effectivePayload.status === 'loading' ||
    !canAppendSelectionBatchItem() ||
    isRectangleModeActive;
  addRectangleButton.disabled =
    effectivePayload.status === 'loading' ||
    !canAppendSelectionBatchItem() ||
    isRectangleModeActive;
  batchHint.textContent = buildBatchHint(
    maxSessionItems,
    isRectangleModeActive
  );
  actionHint.textContent = actionsEnabled
    ? 'Reuse the cached batch with a different action or model. Press Alt+R to rerun the last action or Ctrl+Enter in the custom prompt box to submit.'
    : 'Select text and run Gem Read once before action buttons become available.';

  metaBox.textContent = buildMetaText(effectivePayload);
  metaBox.classList.toggle('loading', effectivePayload.status === 'loading');
  rawDetails.addEventListener('toggle', () => {
    isRawResponseExpanded = rawDetails.open;
  });

  modelInput.addEventListener('input', () => {
    draftModelName = modelInput.value.trim();
  });
  customPromptInput.addEventListener('input', () => {
    // 再描画前でも途中入力を失わないよう、draft を module state に戻す。
    draftCustomPrompt = customPromptInput.value;
    customButton.disabled =
      !actionsEnabled || customPromptInput.value.trim().length === 0;
  });

  translationButton.addEventListener('click', () => {
    void runOverlayAction(
      'translation',
      modelInput.value,
      customPromptInput.value,
      errorBox,
      errorSection
    );
  });
  explanationButton.addEventListener('click', () => {
    void runOverlayAction(
      'translation_with_explanation',
      modelInput.value,
      customPromptInput.value,
      errorBox,
      errorSection
    );
  });
  customButton.addEventListener('click', () => {
    void runOverlayAction(
      'custom_prompt',
      modelInput.value,
      customPromptInput.value,
      errorBox,
      errorSection
    );
  });
  addSelectionButton.addEventListener('click', () => {
    void addCurrentSelection(errorBox, errorSection, effectivePayload);
  });
  addRectangleButton.addEventListener('click', () => {
    void addRectangleSelection(errorBox, errorSection, effectivePayload);
  });
  deleteArticleCacheButton?.addEventListener('click', () => {
    void deleteActiveArticleCache(errorBox, errorSection);
  });
  workspaceTabButton.addEventListener('click', () => {
    setActiveOverlayTab('workspace');
  });
  geminiTabButton.addEventListener('click', () => {
    if (geminiTabButton.disabled) {
      return;
    }

    setActiveOverlayTab('gemini');
  });
  for (const removeButton of root.querySelectorAll<HTMLButtonElement>(
    '.session-item-remove'
  )) {
    removeButton.addEventListener('click', () => {
      const itemId = removeButton.dataset.itemId;
      if (!itemId) {
        return;
      }

      void removeSelectionItem(itemId, errorBox, errorSection);
    });
  }
  for (const imageToggle of root.querySelectorAll<HTMLInputElement>(
    '.session-item-image-toggle'
  )) {
    imageToggle.addEventListener('change', () => {
      const itemId = imageToggle.dataset.itemId;
      if (!itemId) {
        return;
      }

      void toggleSelectionItemImage(
        itemId,
        imageToggle.checked,
        errorBox,
        errorSection
      );
    });
  }

  minimizeButton.addEventListener('click', () => {
    isOverlayMinimized = true;
    if (currentOverlayPayload) {
      renderOverlay(currentOverlayPayload);
    }
  });
  closeButton.addEventListener('click', () => {
    void closeOverlay();
  });
}

function renderPanelMarkup(
  payload: OverlayPayload,
  sessionItems: SelectionSessionItem[],
  maxSessionItems: number
): string {
  const workspaceSelected = activeOverlayTab === 'workspace';
  const geminiSelected = activeOverlayTab === 'gemini';
  const geminiTabEnabled = isGeminiTabEnabled(payload, activeOverlayTab);

  return `
    <style>
      :host {
        all: initial;
      }
      ${RICH_TEXT_STYLE_BLOCK}
      .panel {
        position: fixed;
        top: 16px;
        right: 16px;
        width: min(460px, calc(100vw - 32px));
        max-height: calc(100vh - 32px);
        overflow: auto;
        box-sizing: border-box;
        padding: 16px;
        border-radius: 18px;
        background:
          radial-gradient(circle at top right, rgba(251, 191, 36, 0.18), transparent 30%),
          linear-gradient(180deg, rgba(20, 24, 36, 0.97) 0%, rgba(10, 14, 24, 0.98) 100%);
        color: #f8fafc;
        border: 1px solid rgba(251, 191, 36, 0.18);
        box-shadow: 0 26px 70px rgba(2, 6, 23, 0.52);
        font: 13px/1.55 'Segoe UI', 'Yu Gothic UI', sans-serif;
      }
      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 12px;
      }
      .header-actions {
        display: inline-flex;
        gap: 8px;
      }
      .title {
        font-size: 16px;
        font-weight: 700;
        letter-spacing: 0.03em;
      }
      .subtitle {
        margin-top: 4px;
        color: #cbd5e1;
        font-size: 12px;
      }
      .badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(251, 191, 36, 0.18);
        color: #fde68a;
        font-size: 11px;
        font-weight: 600;
      }
      .panel-tabs {
        display: flex;
        gap: 8px;
        margin-bottom: 12px;
      }
      .panel-tab {
        flex: 1;
        min-width: 0;
        border: 1px solid rgba(148, 163, 184, 0.28);
        border-radius: 999px;
        background: rgba(30, 41, 59, 0.72);
        color: #cbd5e1;
        cursor: pointer;
        font: inherit;
        font-weight: 600;
        letter-spacing: 0.02em;
        padding: 9px 12px;
        transition:
          background-color 120ms ease,
          border-color 120ms ease,
          color 120ms ease,
          box-shadow 120ms ease;
      }
      .panel-tab:hover:not(:disabled) {
        border-color: rgba(250, 204, 21, 0.44);
        color: #f8fafc;
      }
      .panel-tab:focus-visible {
        outline: 2px solid rgba(250, 204, 21, 0.85);
        outline-offset: 2px;
      }
      .panel-tab[aria-selected='true'] {
        background: linear-gradient(180deg, rgba(250, 204, 21, 0.28), rgba(245, 158, 11, 0.18));
        border-color: rgba(250, 204, 21, 0.64);
        box-shadow: inset 0 0 0 1px rgba(250, 204, 21, 0.16);
        color: #fef3c7;
      }
      .panel-tab:disabled {
        cursor: not-allowed;
        opacity: 0.48;
      }
      .panel-tabpanel[hidden] {
        display: none;
      }
      .gemini-empty-state {
        margin-top: 12px;
        padding: 12px 14px;
        border: 1px dashed rgba(148, 163, 184, 0.28);
        border-radius: 14px;
        background: rgba(15, 23, 42, 0.55);
        color: #cbd5e1;
      }
      .close,
      .minimize {
        min-width: 36px;
        height: 36px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.76);
        color: #cbd5e1;
        cursor: pointer;
        font: inherit;
      }
      .section {
        margin-top: 12px;
      }
      .section:first-of-type {
        margin-top: 0;
      }
      .label {
        margin-bottom: 6px;
        color: #93c5fd;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .banner-box {
        padding: 10px 12px;
        border-radius: 12px;
        background: rgba(245, 158, 11, 0.14);
        border: 1px solid rgba(245, 158, 11, 0.26);
        color: #fde68a;
      }
      .article-card {
        display: grid;
        gap: 10px;
        padding: 12px;
        border-radius: 12px;
        background: rgba(15, 23, 42, 0.5);
        border: 1px solid rgba(148, 163, 184, 0.16);
      }
      .article-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
      }
      .article-title {
        font-size: 13px;
        font-weight: 700;
        color: #f8fafc;
      }
      .article-subtitle {
        margin-top: 4px;
        font-size: 11px;
        color: #cbd5e1;
      }
      .article-summary {
        color: #e2e8f0;
        font-size: 12px;
        white-space: pre-wrap;
      }
      .article-meta-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .token-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 10px;
      }
      .token-card {
        display: grid;
        gap: 6px;
        padding: 12px;
        border-radius: 12px;
        background: rgba(15, 23, 42, 0.5);
        border: 1px solid rgba(148, 163, 184, 0.16);
      }
      .token-title {
        color: #93c5fd;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }
      .token-value {
        color: #f8fafc;
        font-size: 16px;
        font-weight: 700;
      }
      .token-note {
        color: #cbd5e1;
        font-size: 12px;
        white-space: pre-wrap;
      }
      .token-note--warning {
        color: #fde68a;
      }
      .article-pill {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(37, 99, 235, 0.16);
        color: #dbeafe;
        font-size: 11px;
      }
      .box {
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(148, 163, 184, 0.16);
        white-space: pre-wrap;
        word-break: break-word;
      }
      .image {
        display: block;
        width: 100%;
        border-radius: 10px;
        border: 1px solid rgba(148, 163, 184, 0.16);
      }
      .meta {
        margin-top: 10px;
        color: #cbd5e1;
        font-size: 11px;
      }
      .error {
        color: #fecaca;
      }
      .loading {
        color: #fde68a;
      }
      .action-grid {
        display: grid;
        gap: 10px;
      }
      .action-row {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }
      .action-row--single {
        grid-template-columns: 1fr;
      }
      .batch-actions {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .input,
      .textarea,
      .action-button {
        box-sizing: border-box;
        width: 100%;
        border-radius: 12px;
        font: inherit;
      }
      .input,
      .textarea {
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: rgba(15, 23, 42, 0.82);
        color: #f8fafc;
        padding: 10px 12px;
      }
      .textarea {
        min-height: 88px;
        resize: vertical;
      }
      .action-button {
        border: 0;
        padding: 10px 12px;
        cursor: pointer;
      }
      .action-button:disabled {
        cursor: not-allowed;
        opacity: 0.55;
      }
      .action-button--primary {
        background: linear-gradient(135deg, #b45309 0%, #ea580c 100%);
        color: #fff7ed;
      }
      .action-button--secondary {
        background: rgba(37, 99, 235, 0.2);
        color: #dbeafe;
      }
      .action-button--accent {
        background: rgba(217, 70, 239, 0.18);
        color: #f5d0fe;
      }
      .action-hint {
        color: #cbd5e1;
        font-size: 12px;
      }
      .batch-counter {
        color: #cbd5e1;
        font-size: 11px;
      }
      .batch-list {
        display: grid;
        gap: 8px;
      }
      .session-item {
        display: grid;
        gap: 6px;
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(148, 163, 184, 0.16);
      }
      .session-item-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
      }
      .session-item-kind {
        display: inline-flex;
        gap: 8px;
        align-items: center;
        color: #fde68a;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }
      .session-item-text {
        color: #f8fafc;
        font-size: 12px;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .session-item-remove {
        border: 0;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(239, 68, 68, 0.18);
        color: #fecaca;
        cursor: pointer;
        font: inherit;
      }
      .batch-hint {
        color: #cbd5e1;
        font-size: 12px;
      }
      .rich-text-box {
        white-space: normal;
      }
      .details {
        border-radius: 12px;
        background: rgba(15, 23, 42, 0.45);
        border: 1px solid rgba(148, 163, 184, 0.16);
        overflow: hidden;
      }
      .details > summary {
        cursor: pointer;
        list-style: none;
        padding: 10px 12px;
        color: #cbd5e1;
        font-weight: 600;
      }
      .details > summary::-webkit-details-marker {
        display: none;
      }
      .details-body {
        padding: 0 12px 12px;
      }
      .session-item-meta {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        color: #cbd5e1;
        font-size: 11px;
      }
      .session-item-toggle {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #dbeafe;
      }
      .session-item-toggle input {
        margin: 0;
      }
    </style>
    <div class="panel">
      <div class="header">
        <div>
          <div class="title">Gem Read Overlay</div>
          <div class="subtitle">Selection actions stay on-page while the background keeps the API flow.</div>
          <div class="badge">${getStatusLabel(payload.status, payload.usedMock)}</div>
        </div>
        <div class="header-actions">
          <button class="minimize" type="button" aria-label="Minimize overlay">_</button>
          <button class="close" type="button" aria-label="Close overlay">X</button>
        </div>
      </div>
      <div class="panel-tabs" role="tablist" aria-label="Overlay sections">
        ${renderOverlayTabButton('workspace', 'Workspace', workspaceSelected, true)}
        ${renderOverlayTabButton('gemini', 'Gemini', geminiSelected, geminiTabEnabled)}
      </div>
      <div
        class="panel-tabpanel panel-tabpanel--workspace"
        id="${getOverlayTabPanelId('workspace')}"
        role="tabpanel"
        aria-labelledby="${getOverlayTabButtonId('workspace')}"
        ${workspaceSelected ? '' : 'hidden'}
      >
        <div class="section banner-section" hidden>
          <div class="label">Runtime</div>
          <div class="banner-box"></div>
        </div>
        ${renderArticleContextMarkup(payload)}
        ${renderTokenInsightsMarkup(payload)}
        <div class="section">
          <div class="label">Batch</div>
          <div class="action-grid">
            <div class="batch-counter">${sessionItems.length}/${maxSessionItems} items</div>
            <div class="action-row batch-actions">
              <button class="action-button action-button--secondary action-add-selection" type="button">Add Current Selection</button>
              <button class="action-button action-button--secondary action-add-rectangle" type="button">Add Rectangle</button>
            </div>
            <div class="batch-hint"></div>
            <div class="batch-list">${renderSessionItemsMarkup(sessionItems)}</div>
          </div>
        </div>
        <div class="section">
          <div class="label">Actions</div>
          <div class="action-grid">
            <input class="input model-input" type="text" list="gem-read-model-list" placeholder="Optional model override" />
            <datalist class="model-list" id="gem-read-model-list"></datalist>
            <div class="action-row">
              <button class="action-button action-button--primary action-translation" type="button">Translate</button>
              <button class="action-button action-button--secondary action-explanation" type="button">Translate + Explain</button>
            </div>
            <textarea class="textarea custom-prompt-input" placeholder="Custom prompt for the current selection"></textarea>
            <div class="action-row action-row--single">
              <button class="action-button action-button--accent action-custom" type="button">Run Custom Prompt</button>
            </div>
            <div class="action-hint"></div>
          </div>
        </div>
        <div class="section">
          <div class="label">Selection</div>
          <div class="box selection-box"></div>
        </div>
        <div class="section preview-section" hidden>
          <div class="label">Crop Preview</div>
          <img class="image preview-image" alt="Selection crop preview" />
        </div>
      </div>
      <div
        class="panel-tabpanel panel-tabpanel--gemini"
        id="${getOverlayTabPanelId('gemini')}"
        role="tabpanel"
        aria-labelledby="${getOverlayTabButtonId('gemini')}"
        ${geminiSelected ? '' : 'hidden'}
      >
        <div class="gemini-empty-state"></div>
        <div class="section result-section" hidden>
          <div class="label result-label">Translation</div>
          <div class="box rich-text-box result-box"></div>
        </div>
        <div class="section explanation-section" hidden>
          <div class="label">Explanation</div>
          <div class="box rich-text-box explanation-box"></div>
        </div>
        <div class="section raw-section" hidden>
          <div class="label">Details</div>
          <details class="details raw-details">
            <summary>Raw Response</summary>
            <div class="details-body">
              <div class="box raw-box"></div>
            </div>
          </details>
        </div>
      </div>
      <div class="section error-section" hidden>
        <div class="label">Error</div>
        <div class="box error error-box"></div>
      </div>
      <div class="meta meta-box"></div>
    </div>
  `;
}

function renderLauncherMarkup(payload: OverlayPayload): string {
  return `
    <style>
      :host {
        all: initial;
      }
      .launcher {
        position: fixed;
        right: 16px;
        bottom: 16px;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 10px 12px;
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.95);
        color: #f8fafc;
        border: 1px solid rgba(251, 191, 36, 0.18);
        box-shadow: 0 16px 40px rgba(2, 6, 23, 0.42);
        font: 12px/1.4 'Segoe UI', 'Yu Gothic UI', sans-serif;
      }
      .launcher-button,
      .launcher-close {
        border: 0;
        background: transparent;
        color: inherit;
        cursor: pointer;
        font: inherit;
      }
      .launcher-badge {
        display: inline-flex;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(251, 191, 36, 0.16);
        color: #fde68a;
      }
    </style>
    <div class="launcher">
      <button class="launcher-button" type="button">Gem Read</button>
      <span class="launcher-badge">${getStatusLabel(payload.status, payload.usedMock)}</span>
      <button class="launcher-close" type="button" aria-label="Close overlay">X</button>
    </div>
  `;
}

function renderOverlayTabButton(
  tabId: OverlayTabId,
  label: string,
  selected: boolean,
  enabled: boolean
): string {
  return `
    <button
      class="panel-tab"
      type="button"
      id="${getOverlayTabButtonId(tabId)}"
      role="tab"
      data-tab-id="${tabId}"
      aria-selected="${selected ? 'true' : 'false'}"
      aria-controls="${getOverlayTabPanelId(tabId)}"
      aria-disabled="${enabled ? 'false' : 'true'}"
      tabindex="${selected ? '0' : '-1'}"
      ${enabled ? '' : 'disabled'}
    >${label}</button>
  `;
}

function getOverlayTabButtonId(tabId: OverlayTabId): string {
  return `gem-read-overlay-tab-${tabId}`;
}

function getOverlayTabPanelId(tabId: OverlayTabId): string {
  return `gem-read-overlay-panel-${tabId}`;
}

function overlayHasGeminiContent(
  payload: OverlayPayload | null | undefined
): boolean {
  return Boolean(
    payload?.translatedText || payload?.explanation || payload?.rawResponse
  );
}

function shouldAutoOpenGeminiTab(
  previousPayload: OverlayPayload | null,
  nextPayload: OverlayPayload
): boolean {
  return (
    previousPayload?.status === 'loading' &&
    nextPayload.status === 'success' &&
    overlayHasGeminiContent(nextPayload)
  );
}

function isGeminiTabEnabled(
  payload: OverlayPayload,
  currentTab: OverlayTabId
): boolean {
  return (
    overlayHasGeminiContent(payload) ||
    currentTab === 'gemini'
  );
}

function configureOverlayTabButton(
  button: HTMLButtonElement,
  tabId: OverlayTabId,
  enabled: boolean
): void {
  const selected = activeOverlayTab === tabId;
  button.setAttribute('aria-selected', selected ? 'true' : 'false');
  button.setAttribute('aria-disabled', enabled ? 'false' : 'true');
  button.tabIndex = selected ? 0 : -1;
  button.disabled = !enabled;
}

function buildGeminiEmptyStateText(payload: OverlayPayload): string {
  if (payload.status === 'loading') {
    return 'Gemini response is on the way. This tab will fill in when the current run finishes.';
  }
  if (payload.status === 'error') {
    return 'No Gemini response is available for the latest run.';
  }
  return 'Run Translate or Translate + Explain to show Gemini output here.';
}

function setActiveOverlayTab(
  tabId: OverlayTabId,
  options: { focus?: boolean } = {}
): void {
  if (activeOverlayTab === tabId && !options.focus) {
    return;
  }

  activeOverlayTab = tabId;
  if (!currentOverlayPayload) {
    return;
  }

  renderOverlay(currentOverlayPayload);
  if (options.focus) {
    focusOverlayTabButton(tabId);
  }
}

function focusOverlayTabButton(tabId: OverlayTabId): void {
  const host = document.getElementById(OVERLAY_HOST_ID);
  const root = host?.shadowRoot;
  root
    ?.querySelector<HTMLButtonElement>(
      `.panel-tab[data-tab-id="${tabId}"]`
    )
    ?.focus();
}

function buildMetaText(payload: OverlayPayload): string {
  const items: string[] = [];
  if (payload.status === 'loading') {
    items.push('Background workflow is running.');
  }
  if (payload.imageCount !== undefined) {
    items.push(`images=${payload.imageCount}`);
  }
  if (payload.timingMs !== undefined) {
    items.push(`crop=${payload.timingMs.toFixed(1)}ms`);
  }
  if (payload.usedMock) {
    items.push('mock-response');
  }
  if (payload.availability) {
    items.push(`availability=${payload.availability}`);
  }
  if (payload.degradedReason) {
    items.push(`reason=${payload.degradedReason}`);
  }
  if (payload.action) {
    items.push(`action=${payload.action}`);
  }
  if (payload.payloadTokenEstimate !== undefined) {
    items.push(`requestTokens=${payload.payloadTokenEstimate}`);
  }
  if (payload.articleContext) {
    items.push(`article=${payload.articleContext.textLength} chars`);
  }
  if (payload.articleCacheState?.status) {
    items.push(`cache=${payload.articleCacheState.status}`);
  }
  if (payload.articleCacheState?.tokenEstimate !== undefined) {
    items.push(`articleTokens=${payload.articleCacheState.tokenEstimate}`);
  }
  if (payload.usage?.totalTokenCount !== undefined) {
    items.push(`totalTokens=${payload.usage.totalTokenCount}`);
  }
  if (payload.usage?.cachedContentTokenCount !== undefined) {
    items.push(`cachedTokens=${payload.usage.cachedContentTokenCount}`);
  }
  return items.join(' | ');
}

function getStatusLabel(
  status: OverlayPayload['status'],
  usedMock?: boolean
): string {
  if (status === 'loading') {
    return 'Running';
  }
  if (status === 'error') {
    return 'Error';
  }
  return usedMock ? 'Mock Result' : 'Live Result';
}

function getResultLabel(action: OverlayPayload['action']): string {
  if (action === 'custom_prompt') {
    return 'Custom Prompt Result';
  }
  if (action === 'translation_with_explanation') {
    return 'Translation';
  }
  return 'Translation';
}

function shouldShowBanner(payload: OverlayPayload): boolean {
  return (
    !payload.sessionReady ||
    payload.usedMock ||
    Boolean(payload.degradedReason) ||
    Boolean(payload.articleContextError) ||
    Boolean(payload.articleCacheState?.notice)
  );
}

function buildBannerText(payload: OverlayPayload): string {
  if (payload.articleCacheState?.notice) {
    return payload.articleCacheState.notice;
  }
  if (payload.articleContextError) {
    return payload.articleContextError;
  }
  if (!payload.sessionReady) {
    return 'No cached selection session is ready yet. Select text on the page and run Gem Read once before using overlay actions.';
  }
  if (payload.usedMock) {
    return 'Mock mode is active. The Local API is reachable, but Gemini credentials are not configured.';
  }
  if (payload.degradedReason) {
    return `Runtime is degraded: ${payload.degradedReason}.`;
  }
  return '';
}

function renderArticleContextMarkup(payload: OverlayPayload): string {
  if (
    !payload.articleContext &&
    !payload.articleContextError &&
    !payload.articleCacheState
  ) {
    return '';
  }

  const articleTitle =
    payload.articleContext?.title ?? 'Article context unavailable';
  const articleSubtitle = payload.articleContext
    ? [
        payload.articleContext.source,
        payload.articleContext.siteName,
        payload.articleContext.byline,
        `${formatCount(payload.articleContext.textLength)} chars`,
      ]
        .filter((value) => Boolean(value))
        .join(' | ')
    : (payload.articleContextError ??
      'Article extraction is not available for this page.');
  const summary = payload.articleContext?.excerpt
    ? payload.articleContext.excerpt
    : payload.articleContext
      ? `Hash ${payload.articleContext.bodyHash}`
      : (payload.articleContextError ?? 'No extracted article context yet.');
  const cacheState = payload.articleCacheState;
  const cacheStatus = cacheState
    ? formatArticleCacheStatus(cacheState)
    : 'No article cache state yet.';

  return `
    <div class="section">
      <div class="label">Article Context</div>
      <div class="article-card">
        <div class="article-header">
          <div>
            <div class="article-title">${escapeHtml(articleTitle)}</div>
            <div class="article-subtitle">${escapeHtml(articleSubtitle)}</div>
          </div>
          ${cacheState?.cacheName ? '<button class="action-button action-button--secondary action-delete-article-cache" type="button">Delete Cache</button>' : ''}
        </div>
        <div class="article-summary">${escapeHtml(summary)}</div>
        <div class="article-meta-row">
          <span class="article-pill">${escapeHtml(cacheStatus)}</span>
          ${cacheState?.tokenEstimate !== undefined ? `<span class="article-pill">Article ${escapeHtml(formatCount(cacheState.tokenEstimate))} tokens</span>` : ''}
          ${payload.payloadTokenEstimate !== undefined ? `<span class="article-pill">Request ${escapeHtml(formatCount(payload.payloadTokenEstimate))} tokens</span>` : ''}
          ${cacheState?.ttlSeconds !== undefined ? `<span class="article-pill">TTL ${escapeHtml(String(cacheState.ttlSeconds))}s</span>` : ''}
        </div>
      </div>
    </div>
  `;
}

function renderTokenInsightsMarkup(payload: OverlayPayload): string {
  const cards: string[] = [];
  const articleTokenCount =
    payload.articleCacheState?.tokenEstimate ??
    payload.articleCacheState?.tokenCount;

  if (payload.payloadTokenEstimate !== undefined || payload.payloadTokenError) {
    cards.push(
      renderTokenCard(
        'Current Request',
        payload.payloadTokenEstimate !== undefined
          ? `${formatCount(payload.payloadTokenEstimate)} estimated`
          : 'Unavailable',
        payload.payloadTokenEstimate !== undefined
          ? `Counted against ${payload.payloadTokenModelName ?? payload.modelName ?? 'the selected model'}.`
          : (payload.payloadTokenError ??
              'Token counting is not available for the current request.'),
        payload.payloadTokenEstimate === undefined
      )
    );
  }

  if (articleTokenCount !== undefined || payload.articleContext) {
    cards.push(
      renderTokenCard(
        'Article Baseline',
        articleTokenCount !== undefined
          ? `${formatCount(articleTokenCount)} article tokens`
          : 'Long article candidate',
        articleTokenCount !== undefined
          ? 'Used to decide whether automatic cache creation is worth it for this tab.'
          : 'Article extraction succeeded, but token counting is not available yet.',
        articleTokenCount === undefined
      )
    );
  }

  if (payload.articleCacheState) {
    cards.push(
      renderTokenCard(
        'Cache Impact',
        buildCacheImpactValue(payload),
        buildCacheImpactNote(payload),
        payload.articleCacheState.status === 'degraded'
      )
    );
  }

  if (payload.usage) {
    cards.push(
      renderTokenCard(
        'Last Response',
        payload.usage.totalTokenCount !== undefined
          ? `${formatCount(payload.usage.totalTokenCount)} total`
          : 'Usage recorded',
        buildUsageNote(payload),
        false
      )
    );
  }

  if (cards.length === 0) {
    return '';
  }

  return `
    <div class="section">
      <div class="label">Tokens</div>
      <div class="token-grid">${cards.join('')}</div>
    </div>
  `;
}

function formatArticleCacheStatus(
  cacheState: NonNullable<OverlayPayload['articleCacheState']>
): string {
  if (cacheState.status === 'active') {
    return `Cache active${cacheState.modelName ? ` on ${cacheState.modelName}` : ''}`;
  }
  if (cacheState.status === 'candidate') {
    return cacheState.autoCreateEligible
      ? 'Cache eligible for auto-create'
      : 'Cache below auto-create threshold';
  }
  if (cacheState.status === 'creating') {
    return 'Creating article cache';
  }
  if (cacheState.status === 'invalidated') {
    return cacheState.invalidationReason
      ? `Cache invalidated: ${cacheState.invalidationReason}`
      : 'Cache invalidated';
  }
  if (cacheState.status === 'unsupported') {
    return 'Cache unsupported for this model';
  }
  if (cacheState.status === 'degraded') {
    return 'Cache state degraded';
  }
  return 'Cache idle';
}

function renderTokenCard(
  title: string,
  value: string,
  note: string,
  warning: boolean
): string {
  return `
    <div class="token-card">
      <div class="token-title">${escapeHtml(title)}</div>
      <div class="token-value">${escapeHtml(value)}</div>
      <div class="token-note ${warning ? 'token-note--warning' : ''}">${escapeHtml(note)}</div>
    </div>
  `;
}

function buildCacheImpactValue(payload: OverlayPayload): string {
  const cacheState = payload.articleCacheState;
  if (!cacheState) {
    return 'No cache state';
  }

  if (cacheState.status === 'active') {
    return cacheState.tokenCount !== undefined
      ? `${formatCount(cacheState.tokenCount)} cached once`
      : 'Cache active';
  }

  if (cacheState.status === 'candidate' && cacheState.autoCreateEligible) {
    return 'Auto-create candidate';
  }

  if (cacheState.status === 'creating') {
    return 'Creating cache';
  }

  if (cacheState.status === 'unsupported') {
    return 'Model unsupported';
  }

  if (cacheState.status === 'degraded') {
    return 'Degraded';
  }

  if (cacheState.status === 'invalidated') {
    return 'Invalidated';
  }

  return 'Idle';
}

function buildCacheImpactNote(payload: OverlayPayload): string {
  const cacheState = payload.articleCacheState;
  if (!cacheState) {
    return 'No article cache state has been resolved for this tab yet.';
  }

  if (cacheState.status === 'active') {
    const cachedTokens = payload.usage?.cachedContentTokenCount;
    if (cachedTokens !== undefined && cachedTokens > 0) {
      return `The last response reused ${formatCount(cachedTokens)} cached tokens from the article context.`;
    }
    if (payload.payloadTokenEstimate !== undefined) {
      return `Selection reruns stay near ${formatCount(payload.payloadTokenEstimate)} request tokens while Gemini reuses the cached article context.`;
    }
    return 'Article context is already cached for this tab and model.';
  }

  if (cacheState.status === 'candidate' && cacheState.autoCreateEligible) {
    const articleTokens = cacheState.tokenEstimate ?? cacheState.tokenCount;
    if (
      articleTokens !== undefined &&
      payload.payloadTokenEstimate !== undefined
    ) {
      return `Creating cache stores about ${formatCount(articleTokens)} article tokens once, then reruns stay near ${formatCount(payload.payloadTokenEstimate)} selection tokens.`;
    }
    return (
      cacheState.notice ??
      'This article is large enough to justify automatic cache creation.'
    );
  }

  return (
    cacheState.notice ??
    'Cache state is available, but no token comparison is ready yet.'
  );
}

function buildUsageNote(payload: OverlayPayload): string {
  const usage = payload.usage;
  if (!usage) {
    return 'No response usage metadata is available.';
  }

  const parts: string[] = [];
  if (usage.promptTokenCount !== undefined) {
    parts.push(`prompt ${formatCount(usage.promptTokenCount)}`);
  }
  if (usage.cachedContentTokenCount !== undefined) {
    parts.push(`cached ${formatCount(usage.cachedContentTokenCount)}`);
  }
  if (usage.candidatesTokenCount !== undefined) {
    parts.push(`output ${formatCount(usage.candidatesTokenCount)}`);
  }

  return parts.length > 0
    ? parts.join(' | ')
    : 'The response completed, but Gemini did not return per-stage token counts.';
}

function formatCount(value: number): string {
  return value.toLocaleString('en-US');
}

function buildSelectionText(sessionItems: SelectionSessionItem[]): string {
  const latestItem = sessionItems.at(-1);
  if (!latestItem) {
    return '';
  }

  return latestItem.selection.text || '[Image region only]';
}

function buildBatchHint(
  maxSessionItems: number,
  rectangleActive: boolean
): string {
  const { current } = getSelectionBatchCapacity();
  if (rectangleActive) {
    return 'Rectangle selection is active. Drag on the page to capture a region or press Esc to cancel.';
  }
  if (current >= maxSessionItems) {
    return `The batch is full. Remove an item before adding another one.`;
  }
  if (current === 0) {
    return 'Add the current text selection with Ctrl+Shift+9 or capture an image region with Ctrl+Shift+Y to start a reusable batch.';
  }
  return 'Batch items keep their own cached crop preview so later analysis does not depend on live page selection.';
}

function renderSessionItemsMarkup(
  sessionItems: SelectionSessionItem[]
): string {
  if (sessionItems.length === 0) {
    return '<div class="session-item"><div class="session-item-text">No items in the current batch.</div></div>';
  }

  return sessionItems
    .map((item, index) => {
      const itemText = item.selection.text || '[Image region only]';
      const itemKind =
        item.source === 'free-rectangle' ? 'Rectangle' : 'Selection';
      const toggleDisabled = !item.previewImageUrl;
      return `
        <div class="session-item">
          <div class="session-item-header">
            <div class="session-item-kind">${index + 1}. ${itemKind}</div>
            <button class="session-item-remove" type="button" data-item-id="${escapeHtml(item.id)}">Remove</button>
          </div>
          <div class="session-item-text">${escapeHtml(itemText)}</div>
          <div class="session-item-meta">
            <span>${item.previewImageUrl ? 'Cached crop ready' : 'No cached crop'}</span>
            <label class="session-item-toggle">
              <input
                class="session-item-image-toggle"
                type="checkbox"
                data-item-id="${escapeHtml(item.id)}"
                ${item.includeImage ? 'checked' : ''}
                ${toggleDisabled ? 'disabled' : ''}
              />
              Include image
            </label>
          </div>
        </div>
      `;
    })
    .join('');
}

async function toggleSelectionItemImage(
  itemId: string,
  includeImage: boolean,
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: 'phase2.toggleSessionItemImage',
    payload: { itemId, includeImage },
  })) as ToggleSessionItemImageResponse | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ??
      'Failed to update image inclusion for the selection item.';
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

async function addCurrentSelection(
  errorBox: HTMLElement,
  errorSection: HTMLElement,
  payload: OverlayPayload
): Promise<void> {
  if (!canAppendSelectionBatchItem()) {
    errorBox.textContent = `You can keep up to ${payload.maxSessionItems ?? MAX_SELECTION_SESSION_ITEMS} selections in one batch.`;
    errorSection.hidden = false;
    return;
  }

  const selection = collectSelection();
  if (!selection.ok || !selection.payload) {
    errorBox.textContent =
      selection.error ??
      'A page selection is required before adding it to the batch.';
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
      response.error ?? 'Failed to add the current selection.';
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

async function addRectangleSelection(
  errorBox: HTMLElement,
  errorSection: HTMLElement,
  payload: OverlayPayload
): Promise<void> {
  if (!canAppendSelectionBatchItem()) {
    errorBox.textContent = `You can keep up to ${payload.maxSessionItems ?? MAX_SELECTION_SESSION_ITEMS} selections in one batch.`;
    errorSection.hidden = false;
    return;
  }

  isRectangleModeActive = true;
  renderOverlay({
    ...payload,
    sessionItems: getSelectionBatchSnapshot(),
  });

  const selection = await startRectangleSelection('overlay');
  isRectangleModeActive = false;

  if (!selection.ok || !selection.payload) {
    if (
      selection.error &&
      selection.error !== 'Rectangle selection was cancelled.'
    ) {
      errorBox.textContent = selection.error;
      errorSection.hidden = false;
    }
    renderOverlay({
      ...payload,
      sessionItems: getSelectionBatchSnapshot(),
    });
    return;
  }

  const response = (await chrome.runtime.sendMessage({
    type: 'phase2.appendSessionItem',
    payload: {
      selection: selection.payload,
      source: 'free-rectangle',
    },
  })) as
    | AppendSessionItemResponse
    | BeginRectangleSelectionResponse
    | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ?? 'Failed to add the rectangle selection.';
    errorSection.hidden = false;
    renderOverlay({
      ...payload,
      sessionItems: getSelectionBatchSnapshot(),
    });
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

async function removeSelectionItem(
  itemId: string,
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: 'phase2.removeSessionItem',
    payload: { itemId },
  })) as RemoveSessionItemResponse | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ?? 'Failed to remove the selection item.';
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

async function runOverlayAction(
  action: AnalysisAction,
  modelName: string,
  customPrompt: string,
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  if (action === 'custom_prompt' && customPrompt.trim().length === 0) {
    errorBox.textContent = 'Custom prompt cannot be empty.';
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
    errorBox.textContent = response.error ?? 'Overlay action failed.';
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

async function deleteActiveArticleCache(
  errorBox: HTMLElement,
  errorSection: HTMLElement
): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: 'phase4.deleteActiveArticleCache',
  })) as DeleteActiveArticleCacheResponse | undefined;

  if (response?.ok === false) {
    errorBox.textContent =
      response.error ?? 'Failed to delete the active article cache.';
    errorSection.hidden = false;
    return;
  }

  errorBox.textContent = '';
  errorSection.hidden = true;
}

function disposeOverlay(): void {
  const host = document.getElementById(OVERLAY_HOST_ID);
  host?.remove();
  isOverlayMinimized = false;
  isRectangleModeActive = false;
  isRawResponseExpanded = false;
  activeOverlayTab = 'workspace';
  draftModelName = '';
  draftCustomPrompt = '';
  currentOverlayPayload = null;
  clearSelectionBatch();
  if (keyboardHandlerAttached) {
    window.removeEventListener('keydown', handleOverlayKeyDown, true);
    keyboardHandlerAttached = false;
  }
}

async function closeOverlay(): Promise<void> {
  const message: ClearOverlaySessionMessage = {
    type: 'phase2.clearOverlaySession',
  };

  disposeOverlay();

  try {
    await chrome.runtime.sendMessage(message);
  } catch {
    // close 自体は background 応答に依存させず、UI 側は先に閉じる。
  }
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function ensureOverlayRoot(): ShadowRoot {
  let host = document.getElementById(OVERLAY_HOST_ID);
  if (!host) {
    host = document.createElement('div');
    host.id = OVERLAY_HOST_ID;
    host.style.position = 'fixed';
    host.style.top = '0';
    host.style.left = '0';
    host.style.zIndex = '2147483647';
    document.documentElement.appendChild(host);
  }

  // Shadow DOM に閉じ込めて、対象ページの CSS と overlay の見た目が干渉しないようにする。
  return host.shadowRoot ?? host.attachShadow({ mode: 'open' });
}

function ensureKeyboardHandler(): void {
  if (keyboardHandlerAttached) {
    return;
  }

  window.addEventListener('keydown', handleOverlayKeyDown, true);
  keyboardHandlerAttached = true;
}

function handleOverlayKeyDown(event: KeyboardEvent): void {
  const host = document.getElementById(OVERLAY_HOST_ID);
  const root = host?.shadowRoot;
  if (!root || !currentOverlayPayload) {
    return;
  }

  const isEscapeKey = event.key === 'Escape';
  if (isEscapeKey && (isRectangleModeActive || isRectangleSelectionActive())) {
    return;
  }

  if (isEscapeKey) {
    event.preventDefault();
    event.stopPropagation();

    if (event.shiftKey) {
      void closeOverlay();
      return;
    }

    if (!isOverlayMinimized) {
      isOverlayMinimized = true;
      renderOverlay(currentOverlayPayload);
    }
    return;
  }

  const focusedTabButton = getFocusedOverlayTabButton(root);
  if (focusedTabButton) {
    const nextTabId = resolveKeyboardOverlayTab(
      root,
      focusedTabButton,
      event.key
    );
    if (nextTabId) {
      event.preventDefault();
      event.stopPropagation();
      setActiveOverlayTab(nextTabId, { focus: true });
      return;
    }
  }

  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    const customPromptInput = root.querySelector<HTMLTextAreaElement>(
      '.custom-prompt-input'
    );
    const customButton =
      root.querySelector<HTMLButtonElement>('.action-custom');
    const errorSection = root.querySelector<HTMLElement>('.error-section');
    const errorBox = root.querySelector<HTMLElement>('.error-box');
    if (
      !customPromptInput ||
      !customButton ||
      !errorSection ||
      !errorBox ||
      customButton.disabled ||
      !event.composedPath().includes(customPromptInput)
    ) {
      return;
    }

    const modelInput = root.querySelector<HTMLInputElement>('.model-input');
    event.preventDefault();
    event.stopPropagation();
    void runOverlayAction(
      'custom_prompt',
      modelInput?.value ?? '',
      customPromptInput.value,
      errorBox,
      errorSection
    );
    return;
  }

  if (
    event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    event.key.toLowerCase() === 'r'
  ) {
    if (
      !currentOverlayPayload.sessionReady ||
      currentOverlayPayload.status === 'loading' ||
      isEditableTarget(event)
    ) {
      return;
    }

    const errorSection = root.querySelector<HTMLElement>('.error-section');
    const errorBox = root.querySelector<HTMLElement>('.error-box');
    if (!errorSection || !errorBox) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    void runOverlayAction(
      currentOverlayPayload.action ?? 'translation',
      currentOverlayPayload.modelName ?? '',
      currentOverlayPayload.customPrompt ?? '',
      errorBox,
      errorSection
    );
  }
}

function getFocusedOverlayTabButton(
  root: ShadowRoot
): HTMLButtonElement | null {
  const activeElement = root.activeElement;
  if (
    activeElement instanceof HTMLButtonElement &&
    activeElement.matches('.panel-tab[data-tab-id]')
  ) {
    return activeElement;
  }

  return null;
}

function resolveKeyboardOverlayTab(
  root: ShadowRoot,
  focusedTabButton: HTMLButtonElement,
  key: string
): OverlayTabId | null {
  const enabledButtons = Array.from(
    root.querySelectorAll<HTMLButtonElement>('.panel-tab[data-tab-id]')
  ).filter((button) => !button.disabled);
  if (enabledButtons.length === 0) {
    return null;
  }

  const currentIndex = enabledButtons.indexOf(focusedTabButton);
  if (currentIndex === -1) {
    return null;
  }

  if (key === 'Home') {
    return readOverlayTabId(enabledButtons[0]);
  }
  if (key === 'End') {
    return readOverlayTabId(enabledButtons.at(-1) ?? null);
  }
  if (key !== 'ArrowLeft' && key !== 'ArrowRight') {
    return null;
  }

  const direction = key === 'ArrowRight' ? 1 : -1;
  const nextIndex =
    (currentIndex + direction + enabledButtons.length) % enabledButtons.length;
  return readOverlayTabId(enabledButtons[nextIndex]);
}

function readOverlayTabId(
  button: HTMLButtonElement | null
): OverlayTabId | null {
  const tabId = button?.dataset.tabId;
  return tabId === 'workspace' || tabId === 'gemini' ? tabId : null;
}

function isEditableTarget(event: KeyboardEvent): boolean {
  for (const entry of event.composedPath()) {
    if (!(entry instanceof HTMLElement)) {
      continue;
    }

    const tagName = entry.tagName;
    if (
      tagName === 'INPUT' ||
      tagName === 'TEXTAREA' ||
      tagName === 'SELECT' ||
      entry.isContentEditable
    ) {
      return true;
    }
  }

  const activeElement = document.activeElement;
  return activeElement instanceof HTMLElement
    ? activeElement.isContentEditable ||
        ['INPUT', 'TEXTAREA', 'SELECT'].includes(activeElement.tagName)
    : false;
}
