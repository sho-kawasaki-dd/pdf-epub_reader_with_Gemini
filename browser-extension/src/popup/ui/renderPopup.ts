import {
  isValidLocalApiBaseUrl,
  normalizeLocalApiBaseUrl,
  type ArticleCacheSettings,
  type MarkdownExportSettings,
  type ExtensionSettings,
  type UiLanguage,
} from '../../shared/config/phase0';
import type {
  CacheListItem,
  ModelCatalogSource,
  ModelOption,
  OpenOverlayResponse,
  PopupStatusPayload,
} from '../../shared/contracts/messages';
import {
  fetchPopupBootstrap,
  listBrowserExtensionCaches,
  deleteContextCache,
} from '../../shared/gateways/localApiGateway';
import { t } from '../../shared/i18n/translator';
import type { MessageKey } from '../../shared/i18n/messages';
import {
  loadExtensionSettings,
  patchExtensionSettings,
  saveExtensionSettings,
} from '../../shared/storage/settingsStorage';

/**
 * Popup は短命な Document 上で動くので、表示状態は永続設定と直近の疎通結果から毎回組み立て直す。
 * overlay のような long-lived UI state は持たず、settings と diagnostics の入口に責務を絞る。
 */
interface PopupViewState {
  settings: ExtensionSettings;
  status: PopupStatusPayload;
  models: ModelOption[];
}

/**
 * DOM query の散在を防ぐための参照束。
 * popup の再描画はしない前提なので、初回 mount 後はこの refs を単一の操作窓口として使う。
 */
interface PopupRefs {
  form: HTMLFormElement;
  apiInput: HTMLInputElement;
  defaultModelInput: HTMLInputElement;
  uiLanguageSelect: HTMLSelectElement;
  sharedSystemPromptInput: HTMLTextAreaElement;
  articleCacheAutoCreateInput: HTMLInputElement;
  includeExplanationInput: HTMLInputElement;
  includeSelectionsInput: HTMLInputElement;
  includeRawResponseInput: HTMLInputElement;
  includeArticleMetadataInput: HTMLInputElement;
  includeUsageMetricsInput: HTMLInputElement;
  includeYamlFrontmatterInput: HTMLInputElement;
  statusBadge: HTMLElement;
  statusLine: HTMLElement;
  detailLine: HTMLElement;
  sourceLine: HTMLElement;
  messageLine: HTMLElement;
  refreshButton: HTMLButtonElement;
  saveButton: HTMLButtonElement;
  openOverlayButton: HTMLButtonElement;
  modelDatalist: HTMLDataListElement;
  debugSection: HTMLDetailsElement;
  debugCacheList: HTMLElement;
  debugLoadButton: HTMLButtonElement;
}

interface PopupFlashMessage {
  key: MessageKey;
  isError: boolean;
  params?: Record<string, string | number>;
}

/**
 * Popup は Local API の接続確認と永続 settings の編集に責務を絞る。
 * 実行系 UI を overlay 側に寄せることで、popup は設定と診断の導線として保守しやすく保つ。
 */
export async function renderPopup(
  documentRef: Document,
  flashMessage?: PopupFlashMessage
): Promise<void> {
  const appRoot = documentRef.getElementById('app');
  if (!appRoot) {
    return;
  }

  const settings = await loadExtensionSettings();
  const language = settings.uiLanguage;

  appRoot.innerHTML = `
    <style>
      :root {
        color-scheme: light;
      }
      .popup-shell {
        box-sizing: border-box;
        width: 360px;
        min-height: 420px;
        padding: 18px;
        background:
          radial-gradient(circle at top left, rgba(250, 204, 21, 0.2), transparent 34%),
          linear-gradient(180deg, #fffdf8 0%, #f4efe2 100%);
        color: #1f2937;
        font: 13px/1.5 Georgia, 'Yu Mincho', serif;
      }
      .panel {
        padding: 16px;
        border: 1px solid rgba(120, 53, 15, 0.14);
        border-radius: 18px;
        background: rgba(255, 252, 244, 0.88);
        box-shadow: 0 14px 34px rgba(120, 53, 15, 0.12);
      }
      .eyebrow {
        margin: 0;
        color: #92400e;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }
      .title-row {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        margin-top: 8px;
      }
      .title {
        margin: 0;
        color: #111827;
        font-size: 24px;
        line-height: 1.05;
      }
      .subtitle {
        margin: 8px 0 0;
        color: #6b7280;
      }
      .status-badge {
        display: inline-flex;
        align-items: center;
        padding: 6px 10px;
        border-radius: 999px;
        background: #fef3c7;
        color: #92400e;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        white-space: nowrap;
      }
      .section {
        margin-top: 16px;
      }
      .label {
        display: block;
        margin-bottom: 6px;
        color: #7c2d12;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .input,
      .textarea,
      .button {
        box-sizing: border-box;
        width: 100%;
        min-height: 40px;
        border-radius: 12px;
        font: inherit;
      }
      .input,
      .textarea {
        border: 1px solid rgba(146, 64, 14, 0.22);
        padding: 10px 12px;
        background: rgba(255, 255, 255, 0.88);
        color: #111827;
      }
      .textarea {
        min-height: 116px;
        resize: vertical;
      }
      .status-card {
        padding: 12px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.7);
        border: 1px solid rgba(120, 53, 15, 0.1);
      }
      .status-line,
      .detail-line,
      .source-line,
      .message-line {
        margin: 0;
      }
      .detail-line,
      .source-line,
      .message-line {
        margin-top: 6px;
        color: #6b7280;
      }
      .button-row {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
      }
      .button {
        border: 0;
        cursor: pointer;
        padding: 10px 12px;
      }
      .button:disabled {
        cursor: progress;
        opacity: 0.7;
      }
      .button-primary {
        background: linear-gradient(135deg, #b45309 0%, #ea580c 100%);
        color: #fff7ed;
        box-shadow: 0 10px 24px rgba(194, 65, 12, 0.22);
      }
      .button-secondary {
        background: rgba(255, 255, 255, 0.72);
        color: #7c2d12;
        border: 1px solid rgba(146, 64, 14, 0.18);
      }
      .button-wide {
        margin-top: 10px;
      }
      .hint {
        margin: 8px 0 0;
        color: #78716c;
        font-size: 12px;
      }
      .checkbox-group {
        display: grid;
        gap: 10px;
        margin-top: 10px;
      }
      .details-section {
        margin-top: 16px;
        border: 1px solid rgba(120, 53, 15, 0.14);
        border-radius: 14px;
        background: rgba(255, 252, 244, 0.6);
      }
      .details-summary {
        padding: 10px 14px;
        cursor: pointer;
        color: #92400e;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        list-style: none;
        user-select: none;
      }
      .details-summary::-webkit-details-marker { display: none; }
      .details-body {
        padding: 0 14px 12px;
      }
      .details-summary-note {
        display: block;
        margin-top: 4px;
        color: #78716c;
        font-size: 11px;
        font-weight: 400;
        letter-spacing: normal;
        text-transform: none;
      }
      .checkbox-card {
        display: flex;
        gap: 10px;
        align-items: flex-start;
        padding: 10px 12px;
        border: 1px solid rgba(146, 64, 14, 0.12);
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.66);
      }
      .checkbox-input {
        margin: 2px 0 0;
        accent-color: #c2410c;
      }
      .checkbox-copy {
        display: grid;
        gap: 2px;
      }
      .checkbox-title {
        color: #1f2937;
        font-size: 12px;
        font-weight: 700;
      }
      .checkbox-hint {
        color: #6b7280;
        font-size: 11px;
      }
      .message-line.is-error {
        color: #b91c1c;
      }
      .message-line.is-success {
        color: #166534;
      }
      .debug-section {
        margin-top: 16px;
        border: 1px solid rgba(120, 53, 15, 0.14);
        border-radius: 14px;
        background: rgba(255, 252, 244, 0.6);
      }
      .debug-summary {
        padding: 10px 14px;
        cursor: pointer;
        color: #92400e;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        list-style: none;
        user-select: none;
      }
      .debug-summary::-webkit-details-marker { display: none; }
      .debug-body {
        padding: 0 14px 12px;
      }
      .debug-load-button {
        display: inline-block;
        margin-bottom: 8px;
        padding: 6px 10px;
        border: 1px solid rgba(146, 64, 14, 0.22);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.72);
        color: #7c2d12;
        font: inherit;
        font-size: 12px;
        cursor: pointer;
      }
      .debug-load-button:disabled { opacity: 0.6; cursor: progress; }
      .debug-cache-list {
        list-style: none;
        margin: 0;
        padding: 0;
      }
      .debug-cache-item {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 8px;
        padding: 6px 0;
        border-top: 1px solid rgba(120, 53, 15, 0.08);
        font-size: 11px;
        word-break: break-all;
      }
      .debug-cache-name {
        flex: 1;
        color: #374151;
      }
      .debug-cache-delete {
        flex-shrink: 0;
        padding: 2px 6px;
        border: 1px solid rgba(185, 28, 28, 0.3);
        border-radius: 6px;
        background: transparent;
        color: #b91c1c;
        font: inherit;
        font-size: 11px;
        cursor: pointer;
      }
      .debug-cache-delete:disabled { opacity: 0.5; cursor: progress; }
      .debug-empty {
        color: #6b7280;
        font-size: 12px;
      }
    </style>
    <div class="popup-shell">
      <div class="panel">
        <p class="eyebrow">${t(language, 'popupEyebrow')}</p>
        <div class="title-row">
          <div>
            <h1 class="title">${t(language, 'popupTitle')}</h1>
            <p class="subtitle">${t(language, 'popupSubtitle')}</p>
          </div>
          <div class="status-badge" data-role="status-badge">${t(language, 'popupChecking')}</div>
        </div>
        <div class="section status-card">
          <p class="status-line" data-role="status-line">${t(language, 'popupCheckingLine')}</p>
          <p class="detail-line" data-role="detail-line"></p>
          <p class="source-line" data-role="source-line"></p>
          <p class="message-line" data-role="message-line"></p>
        </div>
        <form class="section" data-role="settings-form">
          <label class="label" for="api-base-url">${t(language, 'popupApiBaseUrlLabel')}</label>
          <input class="input" id="api-base-url" name="apiBaseUrl" type="url" autocomplete="off" spellcheck="false" />
          <p class="hint">${t(language, 'popupApiBaseUrlHint')}</p>
          <div class="section">
            <label class="label" for="default-model">${t(language, 'popupDefaultModelLabel')}</label>
            <input class="input" id="default-model" name="defaultModel" type="text" list="model-options" autocomplete="off" spellcheck="false" />
            <datalist id="model-options"></datalist>
            <p class="hint">${t(language, 'popupDefaultModelHint')}</p>
          </div>
          <div class="section">
            <label class="label" for="ui-language">${t(language, 'popupUiLanguageLabel')}</label>
            <select class="input" id="ui-language" name="uiLanguage">
              <option value="ja">${t(language, 'popupUiLanguageJa')}</option>
              <option value="en">${t(language, 'popupUiLanguageEn')}</option>
            </select>
          </div>
          <div class="section">
            <label class="label" for="shared-system-prompt">${t(language, 'popupSharedSystemPromptLabel')}</label>
            <textarea class="textarea" id="shared-system-prompt" name="sharedSystemPrompt" data-role="shared-system-prompt" spellcheck="false"></textarea>
            <p class="hint">${t(language, 'popupSharedSystemPromptHint')}</p>
          </div>
          <details class="details-section" data-role="article-cache-section">
            <summary class="details-summary">${t(language, 'popupArticleCacheSummary')}
              <span class="details-summary-note">${t(language, 'popupArticleCacheSummaryNote')}</span>
            </summary>
            <div class="details-body">
              <div class="checkbox-group">
                <label class="checkbox-card" for="article-cache-auto-create">
                  <input class="checkbox-input" id="article-cache-auto-create" data-role="article-cache-auto-create" type="checkbox" />
                  <span class="checkbox-copy">
                    <span class="checkbox-title">${t(language, 'popupArticleCacheAutoCreateTitle')}</span>
                    <span class="checkbox-hint">${t(language, 'popupArticleCacheAutoCreateHint')}</span>
                  </span>
                </label>
              </div>
              <p class="hint">${t(language, 'popupArticleCacheHint')}</p>
            </div>
          </details>
          <details class="details-section" data-role="markdown-export-section">
            <summary class="details-summary">${t(language, 'popupMarkdownExportSummary')}
              <span class="details-summary-note">${t(language, 'popupMarkdownExportSummaryNote')}</span>
            </summary>
            <div class="details-body">
              <div class="checkbox-group">
                <label class="checkbox-card" for="include-explanation">
                  <input class="checkbox-input" id="include-explanation" data-role="include-explanation" type="checkbox" />
                  <span class="checkbox-copy">
                    <span class="checkbox-title">${t(language, 'popupIncludeExplanationTitle')}</span>
                    <span class="checkbox-hint">${t(language, 'popupIncludeExplanationHint')}</span>
                  </span>
                </label>
                <label class="checkbox-card" for="include-selections">
                  <input class="checkbox-input" id="include-selections" data-role="include-selections" type="checkbox" />
                  <span class="checkbox-copy">
                    <span class="checkbox-title">${t(language, 'popupIncludeSelectionsTitle')}</span>
                    <span class="checkbox-hint">${t(language, 'popupIncludeSelectionsHint')}</span>
                  </span>
                </label>
                <label class="checkbox-card" for="include-raw-response">
                  <input class="checkbox-input" id="include-raw-response" data-role="include-raw-response" type="checkbox" />
                  <span class="checkbox-copy">
                    <span class="checkbox-title">${t(language, 'popupIncludeRawResponseTitle')}</span>
                    <span class="checkbox-hint">${t(language, 'popupIncludeRawResponseHint')}</span>
                  </span>
                </label>
                <label class="checkbox-card" for="include-article-metadata">
                  <input class="checkbox-input" id="include-article-metadata" data-role="include-article-metadata" type="checkbox" />
                  <span class="checkbox-copy">
                    <span class="checkbox-title">${t(language, 'popupIncludeArticleMetadataTitle')}</span>
                    <span class="checkbox-hint">${t(language, 'popupIncludeArticleMetadataHint')}</span>
                  </span>
                </label>
                <label class="checkbox-card" for="include-usage-metrics">
                  <input class="checkbox-input" id="include-usage-metrics" data-role="include-usage-metrics" type="checkbox" />
                  <span class="checkbox-copy">
                    <span class="checkbox-title">${t(language, 'popupIncludeUsageMetricsTitle')}</span>
                    <span class="checkbox-hint">${t(language, 'popupIncludeUsageMetricsHint')}</span>
                  </span>
                </label>
                <label class="checkbox-card" for="include-yaml-frontmatter">
                  <input class="checkbox-input" id="include-yaml-frontmatter" data-role="include-yaml-frontmatter" type="checkbox" />
                  <span class="checkbox-copy">
                    <span class="checkbox-title">${t(language, 'popupIncludeYamlFrontmatterTitle')}</span>
                    <span class="checkbox-hint">${t(language, 'popupIncludeYamlFrontmatterHint')}</span>
                  </span>
                </label>
              </div>
              <p class="hint">${t(language, 'popupMarkdownExportHint')}</p>
            </div>
          </details>
          <div class="section button-row">
            <button class="button button-secondary" type="button" data-role="refresh-button">${t(language, 'popupRefresh')}</button>
            <button class="button button-primary" type="submit" data-role="save-button">${t(language, 'popupSave')}</button>
          </div>
          <button class="button button-secondary button-wide" type="button" data-role="open-overlay-button">${t(language, 'popupOpenOverlay')}</button>
          <p class="hint">${t(language, 'popupOpenOverlayHint')}</p>
        </form>
        <details class="debug-section" data-role="debug-section">
          <summary class="debug-summary">${t(language, 'popupDebugCacheSummary')}</summary>
          <div class="debug-body">
            <button class="debug-load-button" type="button" data-role="debug-load-button">${t(language, 'popupDebugLoadCaches')}</button>
            <ul class="debug-cache-list" data-role="debug-cache-list"></ul>
          </div>
        </details>
      </div>
    </div>
  `;

  const refs = getPopupRefs(appRoot);
  if (!refs) {
    return;
  }
  const state: PopupViewState = {
    settings,
    status: {
      connectionStatus: 'unreachable',
      availability: 'degraded',
      apiBaseUrl: settings.apiBaseUrl,
      detail: t(language, 'popupDetailNotCheckedYet'),
      modelSource: 'storage_fallback',
      degradedReason: 'unknown',
    },
    // Local API がまだ未確認でも、前回取得した model 候補があれば入力補完には使える。
    models: settings.lastKnownModels.map((modelId) => ({
      modelId,
      displayName: modelId,
    })),
  };

  refs.apiInput.value = state.settings.apiBaseUrl;
  refs.defaultModelInput.value = state.settings.defaultModel;
  refs.uiLanguageSelect.value = state.settings.uiLanguage;
  refs.sharedSystemPromptInput.value = state.settings.sharedSystemPrompt;
  syncView(refs, state);
  if (flashMessage) {
    setMessage(
      refs,
      t(state.settings.uiLanguage, flashMessage.key, flashMessage.params),
      flashMessage.isError
    );
  }

  refs.form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const candidateUrl = refs.apiInput.value.trim();
    if (!isValidLocalApiBaseUrl(candidateUrl)) {
      // 拡張が任意ホストへ送信しないよう、UI 側でも localhost 制約を早めに明示する。
      setMessage(
        refs,
        t(getCurrentPopupLanguage(refs, state), 'popupErrorUseLocalhost'),
        true
      );
      return;
    }

    setBusy(refs, true);
    try {
      state.settings = await saveExtensionSettings({
        apiBaseUrl: normalizeLocalApiBaseUrl(candidateUrl),
        defaultModel: refs.defaultModelInput.value.trim(),
        uiLanguage: refs.uiLanguageSelect.value as UiLanguage,
        sharedSystemPrompt: refs.sharedSystemPromptInput.value,
        lastKnownModels: state.models.map((model) => model.modelId),
        articleCache: readArticleCacheSettings(refs),
        markdownExport: readMarkdownExportSettings(refs),
      });
      await renderPopup(documentRef, {
        key: 'popupMessageSaved',
        isError: false,
      });
      return;
    } catch (error) {
      setMessage(
        refs,
        toErrorMessage(
          error,
          t(getCurrentPopupLanguage(refs, state), 'popupErrorSaveSettings')
        ),
        true
      );
    } finally {
      setBusy(refs, false);
    }
  });

  refs.refreshButton.addEventListener('click', async () => {
    const candidateUrl = refs.apiInput.value.trim();
    if (!isValidLocalApiBaseUrl(candidateUrl)) {
      setMessage(
        refs,
        t(getCurrentPopupLanguage(refs, state), 'popupErrorRefreshNeedsLocalhost'),
        true
      );
      return;
    }

    setBusy(refs, true);
    try {
      await refreshPopupState(
        state,
        refs,
        normalizeLocalApiBaseUrl(candidateUrl),
        false
      );
      setMessage(
        refs,
        t(getCurrentPopupLanguage(refs, state), 'popupMessageStatusRefreshed'),
        false
      );
    } catch (error) {
      setMessage(
        refs,
        toErrorMessage(
          error,
          t(getCurrentPopupLanguage(refs, state), 'popupErrorRefreshStatus')
        ),
        true
      );
    } finally {
      setBusy(refs, false);
    }
  });

  refs.openOverlayButton.addEventListener('click', async () => {
    setBusy(refs, true);
    try {
      await openOverlayShortcut(state, refs);
      setMessage(
        refs,
        t(getCurrentPopupLanguage(refs, state), 'popupMessageOverlayOpened'),
        false
      );
    } catch (error) {
      setMessage(
        refs,
        toErrorMessage(
          error,
          t(getCurrentPopupLanguage(refs, state), 'popupErrorOpenOverlay')
        ),
        true
      );
    } finally {
      setBusy(refs, false);
    }
  });

  refs.debugLoadButton.addEventListener('click', async () => {
    refs.debugLoadButton.disabled = true;
    try {
      const result = await listBrowserExtensionCaches(
        state.settings.apiBaseUrl
      );
      renderDebugCacheList(refs, result.items, state, refs);
    } catch (error) {
      setMessage(
        refs,
        toErrorMessage(
          error,
          t(getCurrentPopupLanguage(refs, state), 'popupErrorLoadCacheList')
        ),
        true
      );
    } finally {
      refs.debugLoadButton.disabled = false;
    }
  });

  await refreshPopupState(state, refs, state.settings.apiBaseUrl, true);
}

/**
 * Popup markup を組み立てた直後に必要な DOM 参照を集める。
 * ここで欠ける場合は部分的に動かさず fail-closed にして、保存や接続確認だけ半端に動く状態を避ける。
 */
function getPopupRefs(appRoot: HTMLElement): PopupRefs | null {
  const form = appRoot.querySelector<HTMLFormElement>(
    '[data-role="settings-form"]'
  );
  const apiInput = appRoot.querySelector<HTMLInputElement>('#api-base-url');
  const defaultModelInput =
    appRoot.querySelector<HTMLInputElement>('#default-model');
  const uiLanguageSelect =
    appRoot.querySelector<HTMLSelectElement>('#ui-language');
  const sharedSystemPromptInput = appRoot.querySelector<HTMLTextAreaElement>(
    '[data-role="shared-system-prompt"]'
  );
  const articleCacheAutoCreateInput = appRoot.querySelector<HTMLInputElement>(
    '[data-role="article-cache-auto-create"]'
  );
  const includeExplanationInput = appRoot.querySelector<HTMLInputElement>(
    '[data-role="include-explanation"]'
  );
  const includeSelectionsInput = appRoot.querySelector<HTMLInputElement>(
    '[data-role="include-selections"]'
  );
  const includeRawResponseInput = appRoot.querySelector<HTMLInputElement>(
    '[data-role="include-raw-response"]'
  );
  const includeArticleMetadataInput = appRoot.querySelector<HTMLInputElement>(
    '[data-role="include-article-metadata"]'
  );
  const includeUsageMetricsInput = appRoot.querySelector<HTMLInputElement>(
    '[data-role="include-usage-metrics"]'
  );
  const includeYamlFrontmatterInput = appRoot.querySelector<HTMLInputElement>(
    '[data-role="include-yaml-frontmatter"]'
  );
  const statusBadge = appRoot.querySelector<HTMLElement>(
    '[data-role="status-badge"]'
  );
  const statusLine = appRoot.querySelector<HTMLElement>(
    '[data-role="status-line"]'
  );
  const detailLine = appRoot.querySelector<HTMLElement>(
    '[data-role="detail-line"]'
  );
  const sourceLine = appRoot.querySelector<HTMLElement>(
    '[data-role="source-line"]'
  );
  const messageLine = appRoot.querySelector<HTMLElement>(
    '[data-role="message-line"]'
  );
  const refreshButton = appRoot.querySelector<HTMLButtonElement>(
    '[data-role="refresh-button"]'
  );
  const saveButton = appRoot.querySelector<HTMLButtonElement>(
    '[data-role="save-button"]'
  );
  const openOverlayButton = appRoot.querySelector<HTMLButtonElement>(
    '[data-role="open-overlay-button"]'
  );
  const modelDatalist =
    appRoot.querySelector<HTMLDataListElement>('#model-options');
  const debugSection = appRoot.querySelector<HTMLDetailsElement>(
    '[data-role="debug-section"]'
  );
  const debugCacheList = appRoot.querySelector<HTMLElement>(
    '[data-role="debug-cache-list"]'
  );
  const debugLoadButton = appRoot.querySelector<HTMLButtonElement>(
    '[data-role="debug-load-button"]'
  );

  if (
    !form ||
    !apiInput ||
    !defaultModelInput ||
    !uiLanguageSelect ||
    !sharedSystemPromptInput ||
    !articleCacheAutoCreateInput ||
    !includeExplanationInput ||
    !includeSelectionsInput ||
    !includeRawResponseInput ||
    !includeArticleMetadataInput ||
    !includeUsageMetricsInput ||
    !includeYamlFrontmatterInput ||
    !statusBadge ||
    !statusLine ||
    !detailLine ||
    !sourceLine ||
    !messageLine ||
    !refreshButton ||
    !saveButton ||
    !openOverlayButton ||
    !modelDatalist ||
    !debugSection ||
    !debugCacheList ||
    !debugLoadButton
  ) {
    return null;
  }

  return {
    form,
    apiInput,
    defaultModelInput,
    uiLanguageSelect,
    sharedSystemPromptInput,
    articleCacheAutoCreateInput,
    includeExplanationInput,
    includeSelectionsInput,
    includeRawResponseInput,
    includeArticleMetadataInput,
    includeUsageMetricsInput,
    includeYamlFrontmatterInput,
    statusBadge,
    statusLine,
    detailLine,
    sourceLine,
    messageLine,
    refreshButton,
    saveButton,
    openOverlayButton,
    modelDatalist,
    debugSection,
    debugCacheList,
    debugLoadButton,
  };
}

async function refreshPopupState(
  state: PopupViewState,
  refs: PopupRefs,
  apiBaseUrl: string,
  persistFetchedModels: boolean
): Promise<void> {
  try {
    const bootstrap = await fetchPopupBootstrap(apiBaseUrl);
    const fetchedModels = bootstrap.models;
    const fallbackModels = state.settings.lastKnownModels.map((modelId) => ({
      modelId,
      displayName: modelId,
    }));

    state.status = {
      ...bootstrap.status,
      apiBaseUrl,
    };
    state.models = fetchedModels.length > 0 ? fetchedModels : fallbackModels;

    // 到達できた model catalog は次回 offline 時の候補にも使うため、成功時だけ storage へ戻す。
    if (fetchedModels.length > 0 && persistFetchedModels) {
      state.settings = await patchExtensionSettings({
        lastKnownModels: fetchedModels.map((model) => model.modelId),
      });
    }

    if (fetchedModels.length === 0 && fallbackModels.length > 0) {
      // popup は degraded でも手入力や cached model による設定編集を止めない。
      state.status.modelSource = 'storage_fallback';
      state.status.detail =
        state.status.detail ??
        t(state.settings.uiLanguage, 'popupDetailUsingCachedModels');
    }

    syncView(refs, state);
  } catch (error) {
    state.status = {
      connectionStatus: 'unreachable',
      availability: 'degraded',
      apiBaseUrl,
      checkedAt: new Date().toISOString(),
      detail: toErrorMessage(
        error,
        t(state.settings.uiLanguage, 'popupErrorUnreachable')
      ),
      modelSource:
        state.settings.lastKnownModels.length > 0
          ? 'storage_fallback'
          : undefined,
      degradedReason: 'offline',
    };
    state.models = state.settings.lastKnownModels.map((modelId) => ({
      modelId,
      displayName: modelId,
    }));
    syncView(refs, state);
  }
}

/**
 * 永続 settings と直近 bootstrap 結果を DOM へ反映する唯一の入口。
 * popup 内で個別更新を増やしすぎないことで、reachable/degraded/offline の切替を追いやすくする。
 */
function syncView(refs: PopupRefs, state: PopupViewState): void {
  refs.statusBadge.textContent = formatStatusBadge(
    state.settings.uiLanguage,
    state.status.connectionStatus
  );
  refs.statusLine.textContent = formatStatusLine(
    state.settings.uiLanguage,
    state.status
  );
  refs.detailLine.textContent = state.status.detail ?? '';
  refs.sourceLine.textContent = formatSourceLine(
    state.settings.uiLanguage,
    state.status.modelSource,
    state.models
  );
  refs.apiInput.value = state.settings.apiBaseUrl;
  if (!refs.defaultModelInput.value) {
    refs.defaultModelInput.value = state.settings.defaultModel;
  }
  refs.uiLanguageSelect.value = state.settings.uiLanguage;
  if (!refs.sharedSystemPromptInput.value) {
    refs.sharedSystemPromptInput.value = state.settings.sharedSystemPrompt;
  }
  refs.articleCacheAutoCreateInput.checked =
    state.settings.articleCache.enableAutoCreate;
  refs.includeExplanationInput.checked =
    state.settings.markdownExport.includeExplanation;
  refs.includeSelectionsInput.checked =
    state.settings.markdownExport.includeSelections;
  refs.includeRawResponseInput.checked =
    state.settings.markdownExport.includeRawResponse;
  refs.includeArticleMetadataInput.checked =
    state.settings.markdownExport.includeArticleMetadata;
  refs.includeUsageMetricsInput.checked =
    state.settings.markdownExport.includeUsageMetrics;
  refs.includeYamlFrontmatterInput.checked =
    state.settings.markdownExport.includeYamlFrontmatter;
  refs.modelDatalist.innerHTML = state.models
    .map(
      (model) =>
        `<option value="${escapeHtml(model.modelId)}">${escapeHtml(model.displayName)}</option>`
    )
    .join('');
}

function readArticleCacheSettings(refs: PopupRefs): ArticleCacheSettings {
  return {
    enableAutoCreate: refs.articleCacheAutoCreateInput.checked,
  };
}

function readMarkdownExportSettings(refs: PopupRefs): MarkdownExportSettings {
  return {
    includeExplanation: refs.includeExplanationInput.checked,
    includeSelections: refs.includeSelectionsInput.checked,
    includeRawResponse: refs.includeRawResponseInput.checked,
    includeArticleMetadata: refs.includeArticleMetadataInput.checked,
    includeUsageMetrics: refs.includeUsageMetricsInput.checked,
    includeYamlFrontmatter: refs.includeYamlFrontmatterInput.checked,
  };
}

function setBusy(refs: PopupRefs, busy: boolean): void {
  refs.refreshButton.disabled = busy;
  refs.saveButton.disabled = busy;
  refs.openOverlayButton.disabled = busy;
  refs.debugLoadButton.disabled = busy;
}

function setMessage(refs: PopupRefs, message: string, isError: boolean): void {
  refs.messageLine.textContent = message;
  refs.messageLine.classList.toggle('is-error', isError);
  refs.messageLine.classList.toggle(
    'is-success',
    !isError && message.length > 0
  );
}

async function openOverlayShortcut(
  _state: PopupViewState,
  _refs: PopupRefs
): Promise<void> {
  const response = (await chrome.runtime.sendMessage({
    type: 'phase3.openOverlay',
  })) as OpenOverlayResponse | undefined;

  if (response?.ok === false) {
    throw new Error(
      response.error ?? t(_state.settings.uiLanguage, 'popupErrorOpenOverlayResponse')
    );
  }
}

function formatStatusBadge(
  language: UiLanguage,
  connectionStatus: PopupStatusPayload['connectionStatus']
): string {
  if (connectionStatus === 'reachable') {
    return t(language, 'popupStatusReachable');
  }
  if (connectionStatus === 'mock-mode') {
    return t(language, 'popupStatusMockMode');
  }
  return t(language, 'popupStatusUnreachable');
}

function formatStatusLine(
  language: UiLanguage,
  status: PopupStatusPayload
): string {
  if (status.connectionStatus === 'reachable') {
    return t(language, 'popupStatusLineReachable');
  }
  if (status.connectionStatus === 'mock-mode') {
    return t(language, 'popupStatusLineMockMode');
  }
  return t(language, 'popupStatusLineUnreachable');
}

function formatSourceLine(
  language: UiLanguage,
  source: ModelCatalogSource | undefined,
  models: ModelOption[]
): string {
  const modelCount = models.length;
  if (!source) {
    return modelCount > 0
      ? t(language, 'popupSourceCachedModels', { count: modelCount })
      : t(language, 'popupSourceNoModels');
  }

  return t(language, 'popupSourceModels', {
    source,
    count: modelCount,
  });
}

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderDebugCacheList(
  refs: PopupRefs,
  items: CacheListItem[],
  state: PopupViewState,
  outerRefs: PopupRefs
): void {
  if (items.length === 0) {
    refs.debugCacheList.innerHTML =
      `<li class="debug-empty">${escapeHtml(
        t(state.settings.uiLanguage, 'popupMessageNoCaches')
      )}</li>`;
    return;
  }

  refs.debugCacheList.innerHTML = items
    .map(
      (item) => `
      <li class="debug-cache-item" data-cache-name="${escapeHtml(item.cacheName)}">
        <span class="debug-cache-name">${escapeHtml(item.displayName || item.cacheName)}</span>
        <button class="debug-cache-delete" type="button" data-cache-name="${escapeHtml(item.cacheName)}">Delete</button>
      </li>`
    )
    .join('');

  for (const btn of refs.debugCacheList.querySelectorAll<HTMLButtonElement>(
    '.debug-cache-delete'
  )) {
    btn.addEventListener('click', async () => {
      const cacheName = btn.dataset.cacheName;
      if (!cacheName) {
        return;
      }

      btn.disabled = true;
      try {
        await deleteContextCache(cacheName, state.settings.apiBaseUrl);
        const result = await listBrowserExtensionCaches(
          state.settings.apiBaseUrl
        );
        // 削除後は server-side 状態を再取得し、popup 内の list を再構築して stale 表示を残さない。
        renderDebugCacheList(outerRefs, result.items, state, outerRefs);
        setMessage(
          outerRefs,
          t(state.settings.uiLanguage, 'popupMessageDeletedCache', {
            cacheName,
          }),
          false
        );
      } catch (error) {
        btn.disabled = false;
        setMessage(
          outerRefs,
          toErrorMessage(
            error,
            t(state.settings.uiLanguage, 'popupErrorDeleteCache')
          ),
          true
        );
      }
    });
  }
}

function getCurrentPopupLanguage(
  refs: PopupRefs,
  state: PopupViewState
): UiLanguage {
  return refs.uiLanguageSelect.value === 'ja' ? 'ja' : 'en';
}
