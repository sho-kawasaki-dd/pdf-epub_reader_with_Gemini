import {
  MAX_SELECTION_SESSION_ITEMS,
  type UiLanguage,
} from '../../shared/config/phase0';
import type {
  AppendSessionItemResponse,
  BeginRectangleSelectionResponse,
  ClearOverlaySessionMessage,
  ClearSelectionBatchMessage,
  OverlayPayload,
  SelectionSessionItem,
} from '../../shared/contracts/messages';
import { t } from '../../shared/i18n/translator';
import { renderRichText } from './richTextRenderer';
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
import { PANEL_STYLE_BLOCK, LAUNCHER_STYLE_BLOCK } from './overlayStyles';
import {
  runOverlayAction,
  addCurrentSelection,
  removeSelectionItem,
  toggleSelectionItemImage,
  deleteActiveArticleCache,
  exportCurrentMarkdown,
} from './overlayActions';
import type { OverlayTabId } from './overlayKeyboard';
import {
  isEditableTarget,
  getFocusedOverlayTabButton,
  resolveKeyboardOverlayTab,
} from './overlayKeyboard';

const OVERLAY_HOST_ID = 'gem-read-phase0-overlay-host';

// minimize 状態と draft 入力は再描画を跨いで維持したいので module state に置く。
// これは overlay 表示専用の UI state であり、selection batch の canonical copy ではない。
let isOverlayMinimized = false;
let draftModelName = '';
let draftCustomPrompt = '';
let isRectangleModeActive = false;
let isRawResponseExpanded = false;
let activeOverlayTab: OverlayTabId = 'workspace';
let currentOverlayPayload: OverlayPayload | null = null;
let keyboardHandlerAttached = false;

function getOverlayLanguage(
  payload?: OverlayPayload | null | undefined
): UiLanguage {
  const resolved = payload?.uiLanguage ?? currentOverlayPayload?.uiLanguage;
  return resolved === 'ja' ? 'ja' : 'en';
}

function overlayText(
  key: Parameters<typeof t>[1],
  params?: Record<string, string | number>,
  payload?: OverlayPayload | null
): string {
  return t(getOverlayLanguage(payload), key, params);
}

/**
 * Overlay は content script 側で一元管理し、payload から都度 DOM を再構築する。
 * こうしておくと background から渡る状態だけで表示を復元でき、ページ本体の DOM 状態に依存しにくい。
 */
export function renderOverlay(payload: OverlayPayload): void {
  const previousPayload = currentOverlayPayload;

  if (payload.launcherOnly !== undefined) {
    isOverlayMinimized = payload.launcherOnly;
  }

  // background session をそのまま握り続けず、content 側では描画用の mirror を毎回同期し直す。
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
    // 部分的に壊れた DOM を相手に続行すると event binding が不整合になるため、描画を fail-closed にする。
    return;
  }

  const latestSessionItem = sessionItems.at(-1);
  const selectionText =
    effectivePayload.selectedText || buildSelectionText(sessionItems);
  const previewImageUrl =
    effectivePayload.previewImageUrl ?? latestSessionItem?.previewImageUrl;

  selectionBox.textContent =
    selectionText || overlayText('overlayEmptySelectionText', undefined, effectivePayload);

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
    ? overlayText('overlayActionHintReady', undefined, effectivePayload)
    : overlayText('overlayActionHintUnavailable', undefined, effectivePayload);

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
      getOverlayLanguage(effectivePayload),
      errorBox,
      errorSection
    );
  });
  explanationButton.addEventListener('click', () => {
    void runOverlayAction(
      'translation_with_explanation',
      modelInput.value,
      customPromptInput.value,
      getOverlayLanguage(effectivePayload),
      errorBox,
      errorSection
    );
  });
  customButton.addEventListener('click', () => {
    void runOverlayAction(
      'custom_prompt',
      modelInput.value,
      customPromptInput.value,
      getOverlayLanguage(effectivePayload),
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
    void deleteActiveArticleCache(
      getOverlayLanguage(effectivePayload),
      errorBox,
      errorSection
    );
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
  root
    .querySelector<HTMLButtonElement>('.action-export-markdown')
    ?.addEventListener('click', () => {
      void exportCurrentMarkdown(
        effectivePayload,
        sessionItems,
        selectionText,
        getOverlayLanguage(effectivePayload),
        errorBox,
        errorSection
      );
    });
  for (const removeButton of root.querySelectorAll<HTMLButtonElement>(
    '.session-item-remove'
  )) {
    removeButton.addEventListener('click', () => {
      const itemId = removeButton.dataset.itemId;
      if (!itemId) {
        return;
      }

      void removeSelectionItem(
        itemId,
        getOverlayLanguage(effectivePayload),
        errorBox,
        errorSection
      );
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
        getOverlayLanguage(effectivePayload),
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
  const language = getOverlayLanguage(payload);
  const workspaceSelected = activeOverlayTab === 'workspace';
  const geminiSelected = activeOverlayTab === 'gemini';
  const geminiTabEnabled = isGeminiTabEnabled(payload, activeOverlayTab);

  return `
    <style>${PANEL_STYLE_BLOCK}</style>
    <div class="panel">
      <div class="header">
        <div>
          <div class="title">${t(language, 'overlayTitle')}</div>
          <div class="subtitle">${t(language, 'overlaySubtitle')}</div>
          <div class="badge">${getStatusLabel(payload.status, payload.usedMock)}</div>
        </div>
        <div class="header-actions">
          <button class="minimize" type="button" aria-label="${escapeHtml(t(language, 'overlayMinimizeAria'))}">_</button>
          <button class="close" type="button" aria-label="${escapeHtml(t(language, 'overlayCloseAria'))}">X</button>
        </div>
      </div>
      <div class="panel-tabs" role="tablist" aria-label="${escapeHtml(t(language, 'overlayTablistLabel'))}">
        ${renderOverlayTabButton('workspace', t(language, 'overlayTabWorkspace'), workspaceSelected, true)}
        ${renderOverlayTabButton('gemini', t(language, 'overlayTabGemini'), geminiSelected, geminiTabEnabled)}
      </div>
      <div
        class="panel-tabpanel panel-tabpanel--workspace"
        id="${getOverlayTabPanelId('workspace')}"
        role="tabpanel"
        aria-labelledby="${getOverlayTabButtonId('workspace')}"
        ${workspaceSelected ? '' : 'hidden'}
      >
        <div class="section banner-section" hidden>
          <div class="label">${t(language, 'overlaySectionRuntime')}</div>
          <div class="banner-box"></div>
        </div>
        ${renderArticleContextMarkup(payload)}
        ${renderTokenInsightsMarkup(payload)}
        <div class="section">
          <div class="label">${t(language, 'overlaySectionBatch')}</div>
          <div class="action-grid">
            <div class="batch-counter">${t(language, 'overlayBatchCounter', {
              count: sessionItems.length,
              max: maxSessionItems,
            })}</div>
            <div class="action-row batch-actions">
              <button class="action-button action-button--secondary action-add-selection" type="button">${t(language, 'overlayActionAddSelection')}</button>
              <button class="action-button action-button--secondary action-add-rectangle" type="button">${t(language, 'overlayActionAddRectangle')}</button>
            </div>
            <div class="batch-hint"></div>
            <div class="batch-list">${renderSessionItemsMarkup(sessionItems)}</div>
          </div>
        </div>
        <div class="section">
          <div class="label">${t(language, 'overlaySectionActions')}</div>
          <div class="action-grid">
            <input class="input model-input" type="text" list="gem-read-model-list" placeholder="${escapeHtml(t(language, 'overlayModelPlaceholder'))}" />
            <datalist class="model-list" id="gem-read-model-list"></datalist>
            <div class="action-row">
              <button class="action-button action-button--primary action-translation" type="button">${t(language, 'overlayActionTranslate')}</button>
              <button class="action-button action-button--secondary action-explanation" type="button">${t(language, 'overlayActionTranslateExplain')}</button>
            </div>
            <textarea class="textarea custom-prompt-input" placeholder="${escapeHtml(t(language, 'overlayCustomPromptPlaceholder'))}"></textarea>
            <div class="action-row action-row--single">
              <button class="action-button action-button--accent action-custom" type="button">${t(language, 'overlayActionRunCustom')}</button>
            </div>
            <div class="action-hint"></div>
          </div>
        </div>
        <div class="section">
          <div class="label">${t(language, 'overlaySectionSelection')}</div>
          <div class="box selection-box"></div>
        </div>
        <div class="section preview-section" hidden>
          <div class="label">${t(language, 'overlaySectionCropPreview')}</div>
          <img class="image preview-image" alt="${escapeHtml(t(language, 'overlayAltCropPreview'))}" />
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
        ${renderMarkdownExportAction(payload)}
        <div class="section result-section" hidden>
          <div class="label result-label">${t(language, 'overlayResultTranslation')}</div>
          <div class="box rich-text-box result-box"></div>
        </div>
        <div class="section explanation-section" hidden>
          <div class="label">${t(language, 'overlaySectionExplanation')}</div>
          <div class="box rich-text-box explanation-box"></div>
        </div>
        <div class="section raw-section" hidden>
          <div class="label">${t(language, 'overlaySectionDetails')}</div>
          <details class="details raw-details">
            <summary>${t(language, 'overlayRawResponseSummary')}</summary>
            <div class="details-body">
              <div class="box raw-box"></div>
            </div>
          </details>
        </div>
      </div>
      <div class="section error-section" hidden>
        <div class="label">${t(language, 'overlaySectionError')}</div>
        <div class="box error error-box"></div>
      </div>
      <div class="meta meta-box"></div>
    </div>
  `;
}

function renderLauncherMarkup(payload: OverlayPayload): string {
  const language = getOverlayLanguage(payload);
  return `
    <style>${LAUNCHER_STYLE_BLOCK}</style>
    <div class="launcher">
      <button class="launcher-button" type="button">Gem Read</button>
      <span class="launcher-badge">${getStatusLabel(payload.status, payload.usedMock)}</span>
      <button class="launcher-close" type="button" aria-label="${escapeHtml(t(language, 'overlayCloseAria'))}">X</button>
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

function hasMarkdownExportableResult(
  payload: OverlayPayload | null | undefined
): boolean {
  return Boolean(
    payload?.status === 'success' &&
    (payload.translatedText || payload.explanation)
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
  return overlayHasGeminiContent(payload) || currentTab === 'gemini';
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
    return overlayText('overlayGeminiLoading', undefined, payload);
  }
  if (payload.status === 'error') {
    return overlayText('overlayGeminiError', undefined, payload);
  }
  return overlayText('overlayGeminiIdle', undefined, payload);
}

function renderMarkdownExportAction(payload: OverlayPayload): string {
  if (!hasMarkdownExportableResult(payload)) {
    return '';
  }

  const language = getOverlayLanguage(payload);

  return `
    <div class="section export-section">
      <div class="label">${t(language, 'overlaySectionExport')}</div>
      <div class="action-row action-row--single">
        <button class="action-button action-button--secondary action-export-markdown" type="button">${t(language, 'overlayActionDownloadMarkdown')}</button>
      </div>
    </div>
  `;
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

  // tab 切替も payload からの全再描画で揃え、差分 DOM 更新ロジックを増やさない。
  renderOverlay(currentOverlayPayload);
  if (options.focus) {
    focusOverlayTabButton(tabId);
  }
}

function focusOverlayTabButton(tabId: OverlayTabId): void {
  const host = document.getElementById(OVERLAY_HOST_ID);
  const root = host?.shadowRoot;
  root
    ?.querySelector<HTMLButtonElement>(`.panel-tab[data-tab-id="${tabId}"]`)
    ?.focus();
}

function buildMetaText(payload: OverlayPayload): string {
  const items: string[] = [];
  if (payload.status === 'loading') {
    items.push(overlayText('overlayMetaLoading', undefined, payload));
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
    items.push(
      `article=${payload.articleContext.textLength} ${overlayText('overlayArticleCharsSuffix', undefined, payload)}`
    );
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
    return overlayText('overlayStatusRunning');
  }
  if (status === 'error') {
    return overlayText('overlayStatusError');
  }
  return usedMock
    ? overlayText('overlayStatusMockResult')
    : overlayText('overlayStatusLiveResult');
}

function getResultLabel(action: OverlayPayload['action']): string {
  if (action === 'custom_prompt') {
    return overlayText('overlayResultCustomPrompt');
  }
  return overlayText('overlayResultTranslation');
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
  if (
    payload.articleCacheState?.status === 'invalidated' &&
    payload.articleCacheState.invalidationReason === 'remote-missing'
  ) {
    return (
      payload.articleCacheState.notice ??
      overlayText('overlayBannerRemoteMissing', undefined, payload)
    );
  }
  if (payload.articleCacheState?.notice) {
    return payload.articleCacheState.notice;
  }
  if (payload.articleContextError) {
    return payload.articleContextError;
  }
  if (!payload.sessionReady) {
    return overlayText('overlayBannerNoSession', undefined, payload);
  }
  if (payload.usedMock) {
    return overlayText('overlayBannerMockMode', undefined, payload);
  }
  if (payload.degradedReason) {
    return overlayText(
      'overlayBannerDegraded',
      { reason: payload.degradedReason },
      payload
    );
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
    payload.articleContext?.title ??
    overlayText('overlayArticleUnavailableTitle', undefined, payload);
  const articleSubtitle = payload.articleContext
    ? [
        payload.articleContext.source,
        payload.articleContext.siteName,
        payload.articleContext.byline,
        `${formatCount(payload.articleContext.textLength, payload)} ${overlayText('overlayArticleCharsSuffix', undefined, payload)}`,
      ]
        .filter((value) => Boolean(value))
        .join(' | ')
    : (payload.articleContextError ??
      overlayText('overlayArticleUnavailableSubtitle', undefined, payload));
  const summary = payload.articleContext?.excerpt
    ? payload.articleContext.excerpt
    : payload.articleContext
      ? `${overlayText('overlayArticleHashPrefix', undefined, payload)} ${payload.articleContext.bodyHash}`
      : (payload.articleContextError ??
        overlayText('overlayArticleNoSummary', undefined, payload));
  const cacheState = payload.articleCacheState;
  const cacheStatus = cacheState
    ? formatArticleCacheStatus(cacheState)
    : overlayText('overlayArticleCacheNone', undefined, payload);
  const language = getOverlayLanguage(payload);

  return `
    <div class="section">
      <div class="label">${t(language, 'overlaySectionArticleContext')}</div>
      <div class="article-card">
        <div class="article-header">
          <div>
            <div class="article-title">${escapeHtml(articleTitle)}</div>
            <div class="article-subtitle">${escapeHtml(articleSubtitle)}</div>
          </div>
          ${cacheState?.cacheName ? `<button class="action-button action-button--secondary action-delete-article-cache" type="button">${t(language, 'overlayActionDeleteCache')}</button>` : ''}
        </div>
        <div class="article-summary">${escapeHtml(summary)}</div>
        <div class="article-meta-row">
          <span class="article-pill">${escapeHtml(cacheStatus)}</span>
          ${cacheState?.tokenEstimate !== undefined ? `<span class="article-pill">${t(language, 'overlayArticleTokensPill', { count: formatCount(cacheState.tokenEstimate, payload) })}</span>` : ''}
          ${payload.payloadTokenEstimate !== undefined ? `<span class="article-pill">${t(language, 'overlayRequestTokensPill', { count: formatCount(payload.payloadTokenEstimate, payload) })}</span>` : ''}
          ${cacheState?.ttlSeconds !== undefined ? `<span class="article-pill">${t(language, 'overlayTtlPill', { count: cacheState.ttlSeconds })}</span>` : ''}
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
        overlayText('overlayTokenCurrentRequest', undefined, payload),
        payload.payloadTokenEstimate !== undefined
          ? overlayText(
              'overlayTokenEstimatedValue',
              { count: formatCount(payload.payloadTokenEstimate, payload) },
              payload
            )
          : overlayText('overlayTokenUnavailable', undefined, payload),
        payload.payloadTokenEstimate !== undefined
          ? overlayText(
              'overlayTokenCountedAgainst',
              {
                model:
                  payload.payloadTokenModelName ??
                  payload.modelName ??
                  overlayText('overlayTokenSelectedModel', undefined, payload),
              },
              payload
            )
          : (payload.payloadTokenError ??
              overlayText('overlayTokenRequestUnavailableNote', undefined, payload)),
        payload.payloadTokenEstimate === undefined
      )
    );
  }

  if (articleTokenCount !== undefined || payload.articleContext) {
    cards.push(
      renderTokenCard(
        overlayText('overlayTokenArticleBaseline', undefined, payload),
        articleTokenCount !== undefined
          ? overlayText(
              'overlayTokenArticleValue',
              { count: formatCount(articleTokenCount, payload) },
              payload
            )
          : overlayText('overlayTokenLongArticleCandidate', undefined, payload),
        articleTokenCount !== undefined
          ? overlayText('overlayTokenArticleNote', undefined, payload)
          : overlayText('overlayTokenArticleUnavailableNote', undefined, payload),
        articleTokenCount === undefined
      )
    );
  }

  if (payload.articleCacheState) {
    cards.push(
      renderTokenCard(
        overlayText('overlayTokenCacheImpact', undefined, payload),
        buildCacheImpactValue(payload),
        buildCacheImpactNote(payload),
        payload.articleCacheState.status === 'degraded'
      )
    );
  }

  if (payload.usage) {
    cards.push(
      renderTokenCard(
        overlayText('overlayTokenLastResponse', undefined, payload),
        payload.usage.totalTokenCount !== undefined
          ? overlayText(
              'overlayTokenTotalValue',
              { count: formatCount(payload.usage.totalTokenCount, payload) },
              payload
            )
          : overlayText('overlayTokenUsageRecorded', undefined, payload),
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
      <div class="label">${overlayText('overlaySectionTokens', undefined, payload)}</div>
      <div class="token-grid">${cards.join('')}</div>
    </div>
  `;
}

function formatArticleCacheStatus(
  cacheState: NonNullable<OverlayPayload['articleCacheState']>
): string {
  if (cacheState.status === 'active') {
    return overlayText('overlayCacheStatusActive', {
      suffix: cacheState.modelName ? ` ${cacheState.modelName}` : '',
    });
  }
  if (cacheState.status === 'candidate') {
    return cacheState.autoCreateEligible
      ? overlayText('overlayCacheStatusCandidateEligible')
      : overlayText('overlayCacheStatusCandidateBelowThreshold');
  }
  if (cacheState.status === 'creating') {
    return overlayText('overlayCacheStatusCreating');
  }
  if (cacheState.status === 'invalidated') {
    if (cacheState.invalidationReason === 'remote-missing') {
      return overlayText('overlayCacheStatusRemoteMissing');
    }
    return cacheState.invalidationReason
      ? overlayText('overlayCacheStatusInvalidatedReason', {
          reason: cacheState.invalidationReason,
        })
      : overlayText('overlayCacheStatusInvalidated');
  }
  if (cacheState.status === 'unsupported') {
    return overlayText('overlayCacheStatusUnsupported');
  }
  if (cacheState.status === 'degraded') {
    return overlayText('overlayCacheStatusDegraded');
  }
  return overlayText('overlayCacheStatusIdle');
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
    return overlayText('overlayCacheImpactNone', undefined, payload);
  }

  if (cacheState.status === 'active') {
    return cacheState.tokenCount !== undefined
      ? overlayText(
          'overlayCacheImpactCachedOnce',
          { count: formatCount(cacheState.tokenCount, payload) },
          payload
        )
      : overlayText('overlayCacheImpactActive', undefined, payload);
  }

  if (cacheState.status === 'candidate' && cacheState.autoCreateEligible) {
    return overlayText('overlayCacheImpactCandidate', undefined, payload);
  }

  if (cacheState.status === 'creating') {
    return overlayText('overlayCacheImpactCreating', undefined, payload);
  }

  if (cacheState.status === 'unsupported') {
    return overlayText('overlayCacheImpactUnsupported', undefined, payload);
  }

  if (cacheState.status === 'degraded') {
    return overlayText('overlayCacheImpactDegraded', undefined, payload);
  }

  if (cacheState.status === 'invalidated') {
    if (cacheState.invalidationReason === 'remote-missing') {
      return overlayText('overlayCacheImpactFallback', undefined, payload);
    }
    return overlayText('overlayCacheImpactInvalidated', undefined, payload);
  }

  return overlayText('overlayCacheImpactIdle', undefined, payload);
}

function buildCacheImpactNote(payload: OverlayPayload): string {
  const cacheState = payload.articleCacheState;
  if (!cacheState) {
    return overlayText('overlayArticleCacheNoneNote', undefined, payload);
  }

  if (cacheState.status === 'active') {
    const cachedTokens = payload.usage?.cachedContentTokenCount;
    if (cachedTokens !== undefined && cachedTokens > 0) {
      return overlayText(
        'overlayTokenCacheReuse',
        { count: formatCount(cachedTokens, payload) },
        payload
      );
    }
    if (payload.payloadTokenEstimate !== undefined) {
      return overlayText(
        'overlayTokenCacheReuseEstimate',
        { count: formatCount(payload.payloadTokenEstimate, payload) },
        payload
      );
    }
    return overlayText('overlayTokenCacheActive', undefined, payload);
  }

  if (cacheState.status === 'candidate' && cacheState.autoCreateEligible) {
    const articleTokens = cacheState.tokenEstimate ?? cacheState.tokenCount;
    if (
      articleTokens !== undefined &&
      payload.payloadTokenEstimate !== undefined
    ) {
      return overlayText(
        'overlayTokenCacheCreateCompare',
        {
          articleTokens: formatCount(articleTokens, payload),
          requestTokens: formatCount(payload.payloadTokenEstimate, payload),
        },
        payload
      );
    }
    return (
      cacheState.notice ??
      overlayText('overlayTokenCacheCreateDefault', undefined, payload)
    );
  }

  if (
    cacheState.status === 'invalidated' &&
    cacheState.invalidationReason === 'remote-missing'
  ) {
    return (
      cacheState.notice ??
      overlayText('overlayTokenCacheRetryWithout', undefined, payload)
    );
  }

  return (
    cacheState.notice ??
    overlayText('overlayTokenCachePending', undefined, payload)
  );
}

function buildUsageNote(payload: OverlayPayload): string {
  const usage = payload.usage;
  if (!usage) {
    return overlayText('overlayUsageUnavailable', undefined, payload);
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
    : overlayText('overlayUsageMissingStageCounts', undefined, payload);
}

function formatCount(value: number, payload?: OverlayPayload): string {
  return value.toLocaleString(
    getOverlayLanguage(payload) === 'ja' ? 'ja-JP' : 'en-US'
  );
}

function buildSelectionText(sessionItems: SelectionSessionItem[]): string {
  const latestItem = sessionItems.at(-1);
  if (!latestItem) {
    return '';
  }

  return latestItem.selection.text || overlayText('overlaySessionImageOnly');
}

function buildBatchHint(
  maxSessionItems: number,
  rectangleActive: boolean
): string {
  const { current } = getSelectionBatchCapacity();
  if (rectangleActive) {
    return overlayText('overlayRectangleActive');
  }
  if (current >= maxSessionItems) {
    return overlayText('overlayBatchHintFull', { count: maxSessionItems });
  }
  if (current === 0) {
    return overlayText('overlayBatchHintStart');
  }
  return overlayText('overlayBatchHintReuse');
}

function renderSessionItemsMarkup(
  sessionItems: SelectionSessionItem[]
): string {
  if (sessionItems.length === 0) {
    return `<div class="session-item"><div class="session-item-text">${escapeHtml(overlayText('overlaySessionEmpty'))}</div></div>`;
  }

  return sessionItems
    .map((item, index) => {
      const itemText =
        item.selection.text || overlayText('overlaySessionImageOnly');
      const itemKind =
        item.source === 'free-rectangle'
          ? overlayText('overlaySessionKindRectangle')
          : overlayText('overlaySessionKindSelection');
      const toggleDisabled = !item.previewImageUrl;
      return `
        <div class="session-item">
          <div class="session-item-header">
            <div class="session-item-kind">${index + 1}. ${itemKind}</div>
            <button class="session-item-remove" type="button" data-item-id="${escapeHtml(item.id)}">${overlayText('overlaySessionRemove')}</button>
          </div>
          <div class="session-item-text">${escapeHtml(itemText)}</div>
          <div class="session-item-meta">
            <span>${item.previewImageUrl ? overlayText('overlaySessionCachedCropReady') : overlayText('overlaySessionNoCachedCrop')}</span>
            <label class="session-item-toggle">
              <input
                class="session-item-image-toggle"
                type="checkbox"
                data-item-id="${escapeHtml(item.id)}"
                ${item.includeImage ? 'checked' : ''}
                ${toggleDisabled ? 'disabled' : ''}
              />
              ${overlayText('overlaySessionIncludeImage')}
            </label>
          </div>
        </div>
      `;
    })
    .join('');
}

async function addRectangleSelection(
  errorBox: HTMLElement,
  errorSection: HTMLElement,
  payload: OverlayPayload
): Promise<void> {
  if (!canAppendSelectionBatchItem()) {
    errorBox.textContent = overlayText(
      'overlayErrorBatchLimit',
      { count: payload.maxSessionItems ?? MAX_SELECTION_SESSION_ITEMS },
      payload
    );
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
      selection.error !== overlayText('overlayRectangleCancelled', undefined, payload)
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
      response.error ?? overlayText('overlayErrorAddRectangle', undefined, payload);
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
      getOverlayLanguage(currentOverlayPayload),
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
      getOverlayLanguage(currentOverlayPayload),
      errorBox,
      errorSection
    );
  }

  if (
    event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    event.key === 'Backspace'
  ) {
    if (isEditableTarget(event)) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    const message: ClearSelectionBatchMessage = {
      type: 'phase3.clearSelectionBatch',
    };
    void chrome.runtime.sendMessage(message);
  }
}
