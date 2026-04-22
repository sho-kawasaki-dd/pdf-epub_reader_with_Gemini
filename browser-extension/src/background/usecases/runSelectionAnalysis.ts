import {
  MAX_SELECTION_SESSION_ITEMS,
  type ExtensionSettings,
  type UiLanguage,
} from '../../shared/config/phase0';
import type {
  AnalysisAction,
  AnalyzeRequestOptions,
  ModelOption,
  SelectionCapturePayload,
  SelectionSessionItem,
} from '../../shared/contracts/messages';
import { loadExtensionSettings } from '../../shared/storage/settingsStorage';
import { t } from '../../shared/i18n/translator';
import { sendAnalyzeTranslateRequest } from '../gateways/localApiGateway';
import {
  collectArticleContext,
  collectSelection,
  renderOverlay,
} from '../gateways/tabMessagingGateway';
import {
  getAnalysisSession,
  getLatestSelectionItem,
  setAnalysisSession,
  type SelectionAnalysisSession,
} from '../services/analysisSessionStore';
import {
  invalidateArticleCache,
  mergeCollectedArticleContext,
  syncArticleCacheState,
} from '../services/articleCacheService';
import { cropSelectionImage } from '../services/cropSelectionImage';
import { syncPayloadTokenEstimate } from '../services/payloadTokenService';

export interface RunSelectionAnalysisOptions {
  action?: AnalysisAction;
  apiBaseUrl?: string;
  modelName?: string;
  customPrompt?: string;
  reuseCachedSession?: boolean;
}

/**
 * Phase 1 の解析フローを background 側で束ねる use case。
 * 初回実行では selection/crop/session 作成まで進め、overlay からの再実行では cached session を再利用する。
 * Content からは action と補助入力だけを受け取り、正準 session の解決と Local API 送信はここで完結させる。
 */
export async function runSelectionAnalysis(
  tab: chrome.tabs.Tab,
  fallbackSelectionText: string,
  options: RunSelectionAnalysisOptions = {}
): Promise<void> {
  const tabId = tab.id;
  if (tabId === undefined) {
    return;
  }

  const settings = await loadExtensionSettings();
  const resolvedRequestOptions = resolveAnalyzeRequestOptions(
    settings,
    options
  );
  const modelOptions = buildModelOptions(settings);
  const cachedSession = await getCachedSession(tabId);
  const reusableSession = options.reuseCachedSession
    ? cachedSession
    : undefined;

  try {
    // loading を先に描画して、selection 取得や crop の待ち時間でも UI 上の文脈を保つ。
    await renderOverlay(tabId, {
      status: 'loading',
      uiLanguage: settings.uiLanguage,
      action: resolvedRequestOptions.action,
      modelName: resolvedRequestOptions.modelName,
      modelOptions,
      sessionItems: reusableSession?.items,
      maxSessionItems: MAX_SELECTION_SESSION_ITEMS,
      customPrompt: resolvedRequestOptions.customPrompt,
      sessionReady: Boolean(reusableSession ?? cachedSession),
      selectedText: fallbackSelectionText,
      articleContext: (reusableSession ?? cachedSession)?.articleContext,
      articleContextError: (reusableSession ?? cachedSession)
        ?.articleContextError,
      articleCacheState: (reusableSession ?? cachedSession)?.articleCacheState,
      payloadTokenEstimate: (reusableSession ?? cachedSession)
        ?.payloadTokenEstimate,
      payloadTokenModelName: (reusableSession ?? cachedSession)
        ?.payloadTokenModelName,
      payloadTokenError: (reusableSession ?? cachedSession)?.payloadTokenError,
    });

    const session = await resolveAnalysisSession(
      tab,
      tabId,
      fallbackSelectionText,
      modelOptions,
      options.reuseCachedSession === true,
      resolvedRequestOptions.apiBaseUrl,
      resolvedRequestOptions.modelName,
      settings.articleCache.enableAutoCreate,
      cachedSession,
      settings.uiLanguage
    );
    const sessionItem = getRequiredSessionItem(session);

    const apiResponse = await sendAnalyzeTranslateRequest(session.items, {
      ...resolvedRequestOptions,
      cacheName: resolveExplicitCacheName(
        session.articleCacheState,
        resolvedRequestOptions.modelName
      ),
    });

    const nextSession =
      apiResponse.cacheRequestAttempted && apiResponse.cacheRequestFailed
        ? await invalidateArticleCache(session, {
            apiBaseUrl: resolvedRequestOptions.apiBaseUrl,
            reason: 'remote-missing',
            notice: t(settings.uiLanguage, 'bgNoticeRemoteMissing'),
          })
        : session;

    await setAnalysisSession(tabId, {
      ...nextSession,
      lastAction: apiResponse.mode,
      lastModelName: resolvedRequestOptions.modelName,
      lastCustomPrompt: resolvedRequestOptions.customPrompt,
      modelOptions,
    });

    await renderOverlay(tabId, {
      status: 'success',
      uiLanguage: settings.uiLanguage,
      action: apiResponse.mode,
      modelName: resolvedRequestOptions.modelName,
      modelOptions,
      sessionItems: session.items,
      maxSessionItems: MAX_SELECTION_SESSION_ITEMS,
      customPrompt: resolvedRequestOptions.customPrompt,
      sessionReady: true,
      selectedText: buildSelectedText(sessionItem),
      articleContext: nextSession.articleContext,
      articleContextError: nextSession.articleContextError,
      articleCacheState: nextSession.articleCacheState,
      payloadTokenEstimate: nextSession.payloadTokenEstimate,
      payloadTokenModelName: nextSession.payloadTokenModelName,
      payloadTokenError: nextSession.payloadTokenError,
      translatedText: apiResponse.translated_text,
      explanation: apiResponse.explanation,
      previewImageUrl: sessionItem.previewImageUrl,
      usedMock: apiResponse.used_mock,
      availability: apiResponse.availability,
      degradedReason: apiResponse.degraded_reason ?? undefined,
      imageCount: apiResponse.image_count,
      timingMs: sessionItem.cropDurationMs,
      rawResponse: apiResponse.raw_response,
      usage: apiResponse.usage ?? undefined,
    });
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : t(settings.uiLanguage, 'bgErrorOverlayAction');
    const availableSession = reusableSession ?? (await getCachedSession(tabId));
    await renderOverlay(tabId, {
      status: 'error',
      uiLanguage: settings.uiLanguage,
      action: resolvedRequestOptions.action,
      modelName: resolvedRequestOptions.modelName,
      modelOptions,
      sessionItems: availableSession?.items,
      maxSessionItems: MAX_SELECTION_SESSION_ITEMS,
      customPrompt: resolvedRequestOptions.customPrompt,
      sessionReady: Boolean(availableSession),
      selectedText: fallbackSelectionText,
      articleContext: availableSession?.articleContext,
      articleContextError: availableSession?.articleContextError,
      articleCacheState: availableSession?.articleCacheState,
      payloadTokenEstimate: availableSession?.payloadTokenEstimate,
      payloadTokenModelName: availableSession?.payloadTokenModelName,
      payloadTokenError: availableSession?.payloadTokenError,
      error: message,
    });
  }
}

async function resolveAnalysisSession(
  tab: chrome.tabs.Tab,
  tabId: number,
  fallbackSelectionText: string,
  modelOptions: ModelOption[],
  reuseCachedSession: boolean,
  apiBaseUrl: string,
  modelName: string | undefined,
  autoCreateEnabled: boolean,
  cachedSession: SelectionAnalysisSession | undefined,
  uiLanguage: UiLanguage
): Promise<SelectionAnalysisSession> {
  if (reuseCachedSession) {
    const session = await getCachedSession(tabId);
    if (session?.items.length) {
      // rerun 時は selection batch 自体は再利用しつつ、article context と cache 状態だけは最新ページ文脈へ寄せ直す。
      const articleContextResult = await collectArticleContext(tabId).catch(
        (error) => ({
          ok: false as const,
          error:
            error instanceof Error
              ? error.message
              : t(uiLanguage, 'overlayArticleExtractionUnavailable'),
        })
      );
      const refreshedSession = await syncArticleCacheState(
        mergeCollectedArticleContext(session, articleContextResult),
        {
          apiBaseUrl,
          modelName,
          allowAutoCreate: autoCreateEnabled,
          autoCreateDisabledBySetting: !autoCreateEnabled,
        }
      );
      const tokenAwareSession = await syncPayloadTokenEstimate(
        refreshedSession,
        {
          apiBaseUrl,
          modelName,
        }
      );
      await setAnalysisSession(tabId, tokenAwareSession);
      return tokenAwareSession;
    }

    throw new Error(t(uiLanguage, 'bgErrorSelectionSessionMissing'));
  }

  return createFreshSession(
    tab,
    tabId,
    fallbackSelectionText,
    modelOptions,
    apiBaseUrl,
    modelName,
    autoCreateEnabled,
    cachedSession,
    uiLanguage
  );
}

async function createFreshSession(
  tab: chrome.tabs.Tab,
  tabId: number,
  fallbackSelectionText: string,
  modelOptions: ModelOption[],
  apiBaseUrl: string,
  modelName: string | undefined,
  autoCreateEnabled: boolean,
  cachedSession: SelectionAnalysisSession | undefined,
  uiLanguage: UiLanguage
): Promise<SelectionAnalysisSession> {
  const [selection, articleContextResult] = await Promise.all([
    collectSelection(tabId, fallbackSelectionText),
    collectArticleContext(tabId).catch((error) => ({
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : t(uiLanguage, 'overlayArticleExtractionUnavailable'),
    })),
  ]);
  if (!selection.ok || !selection.payload) {
    throw new Error(selection.error ?? t(uiLanguage, 'bgErrorSelectionUnavailable'));
  }

  // browser 提供の selectionText は整形差があるため、座標は content script、文字列は fallback と live snapshot の両方を見る。
  const resolvedSelection = {
    ...selection.payload,
    text: fallbackSelectionText.trim() || selection.payload.text,
  } satisfies SelectionCapturePayload;

  const screenshotDataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: 'png',
  });
  // crop は browser 側で済ませ、Python には必要最小限の画像だけを送る。
  const cropResult = await cropSelectionImage(
    screenshotDataUrl,
    resolvedSelection,
    uiLanguage
  );

  const session: SelectionAnalysisSession = {
    items: [
      {
        id: createSessionItemId(),
        source: 'text-selection',
        selection: resolvedSelection,
        includeImage: false,
        previewImageUrl: cropResult.imageDataUrl,
        cropDurationMs: cropResult.durationMs,
      },
    ],
    modelOptions,
    lastAction: 'translation',
    lastModelName: cachedSession?.lastModelName,
    lastCustomPrompt: cachedSession?.lastCustomPrompt,
    articleContext:
      articleContextResult.ok && 'payload' in articleContextResult
        ? articleContextResult.payload
        : undefined,
    articleContextError: articleContextResult.ok
      ? undefined
      : articleContextResult.error,
    articleCacheState: cachedSession?.articleCacheState,
    payloadTokenEstimate: cachedSession?.payloadTokenEstimate,
    payloadTokenModelName: cachedSession?.payloadTokenModelName,
    payloadTokenError: cachedSession?.payloadTokenError,
  };
  // fresh selection へ差し替えても article cache と token estimate の文脈は引き継ぎ、次の sync で再評価する。
  const cacheAwareSession = await syncArticleCacheState(session, {
    apiBaseUrl,
    modelName,
    allowAutoCreate: autoCreateEnabled,
    autoCreateDisabledBySetting: !autoCreateEnabled,
  });
  const tokenAwareSession = await syncPayloadTokenEstimate(cacheAwareSession, {
    apiBaseUrl,
    modelName,
  });
  await setAnalysisSession(tabId, tokenAwareSession);
  return tokenAwareSession;
}

async function getCachedSession(
  tabId: number
): Promise<SelectionAnalysisSession | undefined> {
  const session = await getAnalysisSession(tabId);
  if (!session) {
    return undefined;
  }

  return {
    ...session,
    items: session.items.map((item) => ({
      ...item,
      selection: {
        ...item.selection,
        rect: { ...item.selection.rect },
      },
    })),
    // 呼び出し側が候補配列を書き換えても store 本体を汚染しないよう参照を切る。
    modelOptions: [...session.modelOptions],
    articleContext: session.articleContext
      ? {
          ...session.articleContext,
        }
      : undefined,
    articleCacheState: session.articleCacheState
      ? {
          ...session.articleCacheState,
        }
      : undefined,
  };
}

/**
 * store から取り出した session を defensive copy にして返す。
 * overlay payload 組み立て側で配列や nested object を触っても、background store 本体を汚染しないため。
 */

function getRequiredSessionItem(session: SelectionAnalysisSession) {
  const item = getLatestSelectionItem(session);
  if (!item) {
    throw new Error(
      'Analysis session could not be found.'
    );
  }
  return item;
}

function createSessionItemId(): string {
  return `selection-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function buildSelectedText(item: SelectionSessionItem): string {
  return item.selection.text || '[Image region only]';
}

function buildModelOptions(settings: ExtensionSettings): ModelOption[] {
  return settings.lastKnownModels.map((modelId) => ({
    modelId,
    displayName: modelId,
  }));
}

function resolveExplicitCacheName(
  articleCacheState: SelectionAnalysisSession['articleCacheState'],
  modelName: string | undefined
): string | undefined {
  // remote cache は model 固有なので、選択中 model が一致するときだけ明示的に再利用する。
  if (
    articleCacheState?.status !== 'active' ||
    !articleCacheState.cacheName ||
    !articleCacheState.modelName ||
    !modelName
  ) {
    return undefined;
  }

  return normalizeModelKey(articleCacheState.modelName) ===
    normalizeModelKey(modelName)
    ? articleCacheState.cacheName
    : undefined;
}

function normalizeModelKey(modelName: string | undefined): string | undefined {
  const normalized = modelName?.trim();
  if (!normalized) {
    return undefined;
  }

  return normalized.replace(/^models\//i, '');
}

function resolveAnalyzeRequestOptions(
  settings: ExtensionSettings,
  options: RunSelectionAnalysisOptions
): AnalyzeRequestOptions & { apiBaseUrl: string } {
  const resolvedModelName = options.modelName ?? settings.defaultModel;
  const resolvedSystemPrompt =
    settings.sharedSystemPrompt.trim().length > 0
      ? settings.sharedSystemPrompt
      : undefined;

  return {
    action: options.action ?? 'translation',
    apiBaseUrl: options.apiBaseUrl ?? settings.apiBaseUrl,
    modelName: resolvedModelName || undefined,
    customPrompt: options.customPrompt?.trim() || undefined,
    systemPrompt: resolvedSystemPrompt,
  };
}
