import type {
  ArticleCacheInvalidationReason,
  ArticleCacheState,
  ArticleContext,
  ArticleContextResponse,
} from '../../shared/contracts/messages';
import {
  countTokens,
  createContextCache,
  deleteContextCache,
  fetchContextCacheStatus,
} from '../../shared/gateways/localApiGateway';
import type { SelectionAnalysisSession } from './analysisSessionStore';

const AUTO_CACHE_MIN_TEXT_LENGTH = 4000;
const AUTO_CACHE_MIN_TOKEN_ESTIMATE = 1200;
const CACHE_DISPLAY_NAME_PREFIX = 'browser-extension:';

export interface SyncArticleCacheOptions {
  apiBaseUrl: string;
  modelName?: string;
  allowAutoCreate?: boolean;
}

export interface InvalidateArticleCacheOptions {
  apiBaseUrl: string;
  reason: ArticleCacheInvalidationReason;
  notice: string;
}

export async function syncArticleCacheState(
  session: SelectionAnalysisSession,
  options: SyncArticleCacheOptions
): Promise<SelectionAnalysisSession> {
  const resolvedModelName = normalizeModelName(
    options.modelName ?? session.lastModelName
  );
  const articleContext = session.articleContext;
  const now = new Date().toISOString();
  const existingState = session.articleCacheState;
  const shouldInvalidateCachedModel = Boolean(
    existingState?.cacheName &&
    existingState.modelName &&
    resolvedModelName &&
    existingState.modelName !== resolvedModelName
  );

  if (!articleContext) {
    if (!existingState) {
      return session.articleContextError
        ? {
            ...session,
            articleCacheState: {
              status: 'idle',
              autoCreateEligible: false,
              notice: session.articleContextError,
              lastValidatedAt: now,
            },
          }
        : session;
    }

    return {
      ...session,
      articleCacheState: {
        ...existingState,
        status: existingState.status === 'active' ? 'invalidated' : 'idle',
        autoCreateEligible: false,
        notice: session.articleContextError ?? existingState.notice,
        lastValidatedAt: now,
      },
    };
  }

  let nextState = buildSeedCacheState(
    existingState,
    articleContext,
    resolvedModelName,
    now
  );

  if (shouldInvalidateCachedModel) {
    console.warn(
      '[GemRead] articleCache: model changed → invalidating',
      { cachedModel: existingState?.modelName, resolvedModel: resolvedModelName }
    );
    nextState = await invalidateTrackedState(nextState, {
      apiBaseUrl: options.apiBaseUrl,
      reason: 'model-changed',
      notice: 'Article cache was cleared because the selected model changed.',
    });
    if (nextState.status === 'degraded') {
      return {
        ...session,
        articleCacheState: nextState,
      };
    }
  }

  if (shouldInvalidateForArticleChange(nextState, articleContext)) {
    const urlChanged = nextState.articleUrl !== articleContext.url;
    console.warn(
      '[GemRead] articleCache: article changed → invalidating',
      urlChanged
        ? { reason: 'url-changed', cachedUrl: nextState.articleUrl, currentUrl: articleContext.url }
        : { reason: 'body-changed', cachedHash: nextState.articleHash, currentHash: articleContext.bodyHash }
    );
    nextState = await invalidateTrackedState(nextState, {
      apiBaseUrl: options.apiBaseUrl,
      reason: urlChanged ? 'url-changed' : 'body-changed',
      notice: urlChanged
        ? 'Article cache was cleared because the page URL changed.'
        : 'Article cache was cleared because the extracted article body changed.',
    });
    if (nextState.status === 'degraded') {
      return {
        ...session,
        articleCacheState: nextState,
      };
    }
  } else {
    console.debug(
      '[GemRead] articleCache: no article change detected',
      {
        cacheName: nextState.cacheName,
        cachedUrl: nextState.articleUrl,
        currentUrl: articleContext.url,
        cachedHash: nextState.articleHash,
        currentHash: articleContext.bodyHash,
      }
    );
  }

  if (nextState.cacheName) {
    try {
      const remoteStatus = await fetchContextCacheStatus(options.apiBaseUrl);
      if (!remoteStatus.isActive) {
        nextState = {
          ...nextState,
          status: 'invalidated',
          cacheName: undefined,
          tokenCount: undefined,
          ttlSeconds: undefined,
          expireTime: undefined,
          invalidationReason: 'ttl-expired',
          notice: 'Article cache expired and will be recreated when needed.',
          lastValidatedAt: now,
        };
      } else if (remoteStatus.cacheName !== nextState.cacheName) {
        nextState = {
          ...nextState,
          status: 'invalidated',
          cacheName: undefined,
          tokenCount: undefined,
          ttlSeconds: undefined,
          expireTime: undefined,
          invalidationReason: 'remote-missing',
          notice:
            'The active article cache was replaced and will be recreated when needed.',
          lastValidatedAt: now,
        };
      } else {
        nextState = {
          ...nextState,
          status: 'active',
          cacheName: remoteStatus.cacheName,
          displayName: remoteStatus.displayName ?? nextState.displayName,
          modelName: remoteStatus.modelName ?? resolvedModelName,
          tokenCount: remoteStatus.tokenCount,
          ttlSeconds: remoteStatus.ttlSeconds,
          expireTime: remoteStatus.expireTime,
          invalidationReason: undefined,
          notice: nextState.notice,
          lastValidatedAt: now,
        };
      }
    } catch (error) {
      return {
        ...session,
        articleCacheState: {
          ...nextState,
          status: 'degraded',
          notice: `Article cache status could not be refreshed: ${toErrorMessage(error)}`,
          lastValidatedAt: now,
        },
      };
    }
  }

  if (!resolvedModelName) {
    return {
      ...session,
      articleCacheState: {
        ...nextState,
        status: 'idle',
        autoCreateEligible: false,
        notice: 'Choose a Gemini model before article cache can be managed.',
        lastValidatedAt: now,
      },
    };
  }

  if (!isCacheSupportedModel(resolvedModelName)) {
    return {
      ...session,
      articleCacheState: {
        ...nextState,
        status: 'unsupported',
        autoCreateEligible: false,
        notice:
          'The current model is not expected to support context cache creation.',
        lastValidatedAt: now,
      },
    };
  }

  const tokenEstimateResult = await resolveTokenEstimate(
    nextState,
    articleContext,
    resolvedModelName,
    options.apiBaseUrl,
    now
  );
  nextState = tokenEstimateResult.state;

  if (nextState.status === 'active') {
    return {
      ...session,
      articleCacheState: {
        ...nextState,
        autoCreateEligible: true,
      },
    };
  }

  if (!nextState.autoCreateEligible) {
    return {
      ...session,
      articleCacheState: {
        ...nextState,
        status: nextState.status === 'degraded' ? 'degraded' : 'candidate',
        notice:
          nextState.notice ??
          'Article context is below the automatic cache creation threshold.',
        lastValidatedAt: now,
      },
    };
  }

  if (!options.allowAutoCreate) {
    return {
      ...session,
      articleCacheState: {
        ...nextState,
        status: 'candidate',
        notice: 'Article context is eligible for automatic cache creation.',
        lastValidatedAt: now,
      },
    };
  }

  console.info('[GemRead] articleCache: auto-creating cache', {
    url: articleContext.url,
    textLength: articleContext.textLength,
    tokenEstimate: nextState.tokenEstimate,
    model: resolvedModelName,
  });

  try {
    const createdStatus = await createContextCache(articleContext.bodyText, {
      apiBaseUrl: options.apiBaseUrl,
      modelName: resolvedModelName,
      displayName: buildCacheDisplayName(articleContext),
    });
    return {
      ...session,
      articleCacheState: {
        ...nextState,
        status: 'active',
        cacheName: createdStatus.cacheName,
        displayName:
          createdStatus.displayName ?? buildCacheDisplayName(articleContext),
        modelName: createdStatus.modelName ?? resolvedModelName,
        tokenCount: createdStatus.tokenCount,
        ttlSeconds: createdStatus.ttlSeconds,
        expireTime: createdStatus.expireTime,
        invalidationReason: undefined,
        notice: 'Article cache created automatically for the current tab.',
        lastValidatedAt: now,
      },
    };
  } catch (error) {
    const message = toErrorMessage(error);
    return {
      ...session,
      articleCacheState: {
        ...nextState,
        status: isUnsupportedCacheError(message) ? 'unsupported' : 'degraded',
        autoCreateEligible: false,
        notice: `Article cache could not be created: ${message}`,
        lastValidatedAt: now,
      },
    };
  }
}

export async function invalidateArticleCache(
  session: SelectionAnalysisSession,
  options: InvalidateArticleCacheOptions
): Promise<SelectionAnalysisSession> {
  const existingState = session.articleCacheState;
  if (!existingState) {
    return {
      ...session,
      articleCacheState: {
        status: 'invalidated',
        autoCreateEligible: false,
        invalidationReason: options.reason,
        notice: options.notice,
        lastValidatedAt: new Date().toISOString(),
      },
    };
  }

  return {
    ...session,
    articleCacheState: await invalidateTrackedState(existingState, options),
  };
}

export function mergeCollectedArticleContext(
  session: SelectionAnalysisSession,
  result: ArticleContextResponse | { ok: false; error?: string }
): SelectionAnalysisSession {
  if (result.ok && result.payload) {
    return {
      ...session,
      articleContext: result.payload,
      articleContextError: undefined,
    };
  }

  if (session.articleContext) {
    return {
      ...session,
      articleContextError: result.error,
    };
  }

  return {
    ...session,
    articleContext: undefined,
    articleContextError: result.error,
  };
}

export function buildNavigatedSessionState(
  session: SelectionAnalysisSession,
  nextUrl: string
): SelectionAnalysisSession {
  // 選択内容とページコンテキストはクリアするが、キャッシュ状態はそのまま保持する。
  // SPA ではセクション切り替えで URL が変わるため、ここでキャッシュを削除すると
  // セクション移動のたびに再作成が走る。本文ハッシュによる有効性確認は
  // 次回の syncArticleCacheState に委ねる。
  return {
    ...session,
    items: [],
    articleContext: undefined,
    articleContextError: `Page changed to ${nextUrl}. Article context will be refreshed on the next run.`,
  };
}

function buildSeedCacheState(
  existingState: ArticleCacheState | undefined,
  articleContext: ArticleContext,
  resolvedModelName: string | undefined,
  now: string
): ArticleCacheState {
  return {
    status: existingState?.status ?? 'idle',
    autoCreateEligible: existingState?.autoCreateEligible,
    cacheName: existingState?.cacheName,
    displayName: existingState?.displayName,
    modelName: resolvedModelName ?? existingState?.modelName,
    articleUrl: existingState?.articleUrl ?? articleContext.url,
    articleHash: existingState?.articleHash ?? articleContext.bodyHash,
    tokenEstimate: existingState?.tokenEstimate,
    tokenCount: existingState?.tokenCount,
    ttlSeconds: existingState?.ttlSeconds,
    expireTime: existingState?.expireTime,
    invalidationReason: existingState?.invalidationReason,
    notice: existingState?.notice,
    lastValidatedAt: now,
  };
}

async function resolveTokenEstimate(
  state: ArticleCacheState,
  articleContext: ArticleContext,
  modelName: string,
  apiBaseUrl: string,
  now: string
): Promise<{ state: ArticleCacheState }> {
  const eligibleByTextLength =
    articleContext.textLength >= AUTO_CACHE_MIN_TEXT_LENGTH;

  try {
    const tokenResult = await countTokens(articleContext.bodyText, {
      apiBaseUrl,
      modelName,
    });
    const autoCreateEligible =
      eligibleByTextLength ||
      tokenResult.tokenCount >= AUTO_CACHE_MIN_TOKEN_ESTIMATE;

    return {
      state: {
        ...state,
        tokenEstimate: tokenResult.tokenCount,
        autoCreateEligible,
        notice: autoCreateEligible
          ? state.notice
          : 'Article context is below the automatic cache creation threshold.',
        lastValidatedAt: now,
      },
    };
  } catch (error) {
    return {
      state: {
        ...state,
        autoCreateEligible: eligibleByTextLength,
        notice: eligibleByTextLength
          ? state.notice
          : `Token estimate is unavailable: ${toErrorMessage(error)}`,
        lastValidatedAt: now,
      },
    };
  }
}

async function invalidateTrackedState(
  state: ArticleCacheState,
  options: InvalidateArticleCacheOptions
): Promise<ArticleCacheState> {
  if (!state.cacheName) {
    return {
      ...state,
      status: 'invalidated',
      autoCreateEligible: false,
      invalidationReason: options.reason,
      notice: options.notice,
      lastValidatedAt: new Date().toISOString(),
    };
  }

  try {
    await deleteContextCache(state.cacheName, options.apiBaseUrl);
    return {
      ...state,
      status: 'invalidated',
      autoCreateEligible: false,
      cacheName: undefined,
      tokenCount: undefined,
      ttlSeconds: undefined,
      expireTime: undefined,
      invalidationReason: options.reason,
      notice: options.notice,
      lastValidatedAt: new Date().toISOString(),
    };
  } catch (error) {
    return {
      ...state,
      status: 'degraded',
      autoCreateEligible: false,
      invalidationReason: options.reason,
      notice: `${options.notice} Remote cache deletion failed: ${toErrorMessage(error)}`,
      lastValidatedAt: new Date().toISOString(),
    };
  }
}

function shouldInvalidateForArticleChange(
  state: ArticleCacheState,
  articleContext: ArticleContext
): boolean {
  // URL の変化だけでは無効化しない。SPA ではセクション切り替えのたびに URL が変わるが
  // 本文ハッシュが一致していれば同じコンテンツとみなしてキャッシュを再利用する。
  // ハッシュが変わった場合（=実際に別コンテンツ）だけ無効化する。
  return Boolean(
    state.cacheName &&
    state.articleHash &&
    state.articleHash !== articleContext.bodyHash
  );
}

function buildCacheDisplayName(articleContext: ArticleContext): string {
  const normalizedTitle = articleContext.title
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 72);
  return `${CACHE_DISPLAY_NAME_PREFIX}${normalizedTitle || 'untitled-article'}`;
}

function isCacheSupportedModel(modelName: string): boolean {
  return !/lite/i.test(modelName);
}

function isUnsupportedCacheError(message: string): boolean {
  const normalized = message.toLowerCase();
  return (
    message.includes('サポートしていません') ||
    normalized.includes('does not support context cache') ||
    normalized.includes('not support') ||
    normalized.includes('not supported for createcachedcontent')
  );
}

function normalizeModelName(modelName: string | undefined): string | undefined {
  const normalized = modelName?.trim();
  return normalized ? normalized : undefined;
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'Unexpected article cache error.';
}
