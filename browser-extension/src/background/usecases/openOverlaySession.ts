import { loadExtensionSettings } from '../../shared/storage/settingsStorage';
import { renderOverlay } from '../gateways/tabMessagingGateway';
import { getAnalysisSession } from '../services/analysisSessionStore';
import {
  buildEmptyOverlayPayload,
  buildOverlayPayload,
} from './updateSelectionSession';

export async function openOverlaySession(tabId: number): Promise<void> {
	const session = getAnalysisSession(tabId);
	if (session?.items.length) {
		await renderOverlay(
			tabId,
			buildOverlayPayload(session, {
				launcherOnly: false,
				preserveDrafts: true,
			})
		);
		return;
	}

	const settings = await loadExtensionSettings();
	await renderOverlay(
		tabId,
		buildEmptyOverlayPayload(settings, {
			launcherOnly: true,
			preserveDrafts: true,
		})
	);
}