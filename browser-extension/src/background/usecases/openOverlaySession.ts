import { t } from '../../shared/i18n/translator';
import { loadExtensionSettings } from '../../shared/storage/settingsStorage';
import {
  collectArticleContext,
  renderOverlay,
} from '../gateways/tabMessagingGateway';
import {
  getAnalysisSession,
  setAnalysisSession,
} from '../services/analysisSessionStore';
import {
  mergeCollectedArticleContext,
  syncArticleCacheState,
} from '../services/articleCacheService';
import { syncPayloadTokenEstimate } from '../services/payloadTokenService';
import {
  buildEmptyOverlayPayload,
  buildOverlayPayload,
} from './updateSelectionSession';

/**
 * 既存 session があれば overlay をそのまま再表示し、必要な article/cache/token 情報だけ最新化する。
 * live selection を再取得して full panel を復元するのではなく、background session から reopen できることが目的。
 */
export async function openOverlaySession(tabId: number): Promise<void> {
  const settings = await loadExtensionSettings();
  const session = await getAnalysisSession(tabId);
  if (session) {
    // reopen 時も article context は取り直し、SPA 遷移や本文変化に対して cache 状態だけ stale のまま残さない。
    const articleContextResult = await collectArticleContext(tabId).catch(
      (error) => ({
        ok: false as const,
        error:
          error instanceof Error
            ? error.message
            : t(settings.uiLanguage, 'overlayArticleExtractionUnavailable'),
      })
    );
    const refreshedSession = await syncArticleCacheState(
      mergeCollectedArticleContext(session, articleContextResult),
      {
        apiBaseUrl: settings.apiBaseUrl,
        modelName: session.lastModelName || settings.defaultModel || undefined,
        allowAutoCreate:
          session.items.length > 0 && settings.articleCache.enableAutoCreate,
        autoCreateDisabledBySetting: !settings.articleCache.enableAutoCreate,
      }
    );
    const tokenAwareSession = await syncPayloadTokenEstimate(refreshedSession, {
      apiBaseUrl: settings.apiBaseUrl,
      modelName: session.lastModelName || settings.defaultModel || undefined,
    });
    await setAnalysisSession(tabId, tokenAwareSession);

    if (
      tokenAwareSession.items.length ||
      tokenAwareSession.articleContext ||
      tokenAwareSession.articleCacheState
    ) {
      await renderOverlay(
        tabId,
        buildOverlayPayload(tokenAwareSession, {
          launcherOnly: false,
          preserveDrafts: true,
          uiLanguage: settings.uiLanguage,
        })
      );
      return;
    }
  }

  // 復元可能な session がない場合だけ launcher-only へ落とし、overlay を開く導線自体は失わせない。
  await renderOverlay(
    tabId,
    buildEmptyOverlayPayload(settings, {
      launcherOnly: true,
      preserveDrafts: true,
      uiLanguage: settings.uiLanguage,
    })
  );
}
