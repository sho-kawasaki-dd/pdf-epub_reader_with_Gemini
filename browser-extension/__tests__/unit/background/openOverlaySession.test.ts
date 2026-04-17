import { beforeEach, describe, expect, it, vi } from 'vitest';

const loadExtensionSettingsMock = vi.hoisted(() => vi.fn());
const renderOverlayMock = vi.hoisted(() => vi.fn());

vi.mock('../../../src/shared/storage/settingsStorage', () => ({
	loadExtensionSettings: loadExtensionSettingsMock,
}));

vi.mock('../../../src/background/gateways/tabMessagingGateway', () => ({
	renderOverlay: renderOverlayMock,
}));

import {
	clearAnalysisSession,
	setAnalysisSession,
} from '../../../src/background/services/analysisSessionStore';
import { openOverlaySession } from '../../../src/background/usecases/openOverlaySession';

describe('openOverlaySession', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		clearAnalysisSession(7);
		loadExtensionSettingsMock.mockResolvedValue({
			apiBaseUrl: 'http://127.0.0.1:9000',
			defaultModel: 'gemini-2.5-flash',
			lastKnownModels: ['gemini-2.5-flash'],
		});
	});

	it('renders the cached batch session when one exists', async () => {
		setAnalysisSession(7, {
			items: [
				{
					id: 'selection-1',
					source: 'text-selection',
					selection: {
						text: 'Selected text',
						rect: { left: 1, top: 2, width: 3, height: 4 },
						viewportWidth: 100,
						viewportHeight: 100,
						devicePixelRatio: 1,
						url: 'https://example.com',
						pageTitle: 'Example',
					},
					includeImage: false,
					previewImageUrl: 'data:image/webp;base64,preview',
					cropDurationMs: 2.5,
				},
			],
			modelOptions: [
				{
					modelId: 'gemini-2.5-flash',
					displayName: 'Gemini 2.5 Flash',
				},
			],
			lastAction: 'translation_with_explanation',
			lastModelName: 'gemini-2.5-pro',
			lastCustomPrompt: 'Summarize this',
		});

		await openOverlaySession(7);

		expect(loadExtensionSettingsMock).not.toHaveBeenCalled();
		expect(renderOverlayMock).toHaveBeenCalledWith(
			7,
			expect.objectContaining({
				sessionReady: true,
				launcherOnly: false,
				preserveDrafts: true,
				action: 'translation_with_explanation',
				selectedText: 'Selected text',
			})
		);
	});

	it('renders a launcher-only overlay when no cached session exists', async () => {
		await openOverlaySession(7);

		expect(loadExtensionSettingsMock).toHaveBeenCalledTimes(1);
		expect(renderOverlayMock).toHaveBeenCalledWith(
			7,
			expect.objectContaining({
				sessionReady: false,
				launcherOnly: true,
				preserveDrafts: true,
				modelName: 'gemini-2.5-flash',
			})
		);
	});
});