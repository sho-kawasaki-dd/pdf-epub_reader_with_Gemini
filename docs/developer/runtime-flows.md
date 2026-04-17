# Runtime Flows

## Startup Flow

1. On Windows PowerShell, `.\gem-read_launch.ps1` changes to the repository root and runs `uv run python -m pdf_epub_reader`.
2. `python -m pdf_epub_reader` calls `main()`.
3. `main()` loads `.env` and delegates to `run_app()`.
4. `run_app()` creates or reuses `QApplication`, installs a qasync event loop, and schedules `_app_main()`.
5. `_app_main()` creates config, models, views, and presenters.
6. The main window is shown.
7. On shutdown, cache invalidation cleanup is attempted before event loop teardown.

## Open File Flow

1. The view emits an open request, recent-file request, or file-drop event.
2. `MainPresenter.open_file()` clears selection state and displays opening status.
3. Existing cache is invalidated if active.
4. `DocumentModel.open_document()` returns `DocumentInfo`.
5. Placeholder pages are derived from page sizes and base DPI.
6. The view receives page placeholders and table-of-contents entries.
7. Page images are rendered later through viewport-driven requests.

## Selection Flow

1. The user creates one or more rectangular selections.
2. `MainPresenter` allocates stable selection slots and marks them pending.
3. `DocumentModel.extract_content()` resolves text and optional image data.
4. The selection snapshot is updated to ready or error.
5. `PanelPresenter` rebuilds the combined preview string from ordered slots.
6. AI requests use the current side panel model and current selection snapshot.

## Cache Flow

1. Full document text is extracted.
2. `AIModel.create_cache()` creates remote cached content for a selected model.
3. `PanelPresenter` updates cache UI state and countdown.
4. `AIModel.analyze()` includes cached content when the model matches.
5. If cache-backed analysis fails for non-rate-limit reasons, AIModel clears the cache linkage and retries without cache.
6. Cache can expire, be invalidated manually, be replaced, or be cleared on shutdown.

## Browser Extension Phase 2 Flow

1. The user selects text on a web page or starts free-rectangle mode.
2. The content script keeps the latest text snapshot alive and, when rectangle mode is used, produces an image-first viewport rect payload.
3. The overlay Add Selection button or rectangle flow sends a session-mutation request to background instead of calling the Local API immediately.
4. Background captures a visible-tab screenshot for each appended item, crops the item immediately, and stores the cached preview in a tab-scoped analysis session.
5. Text-selection items default to `includeImage=false`, while free-rectangle items default to `includeImage=true`.
6. The overlay mirrors the ordered batch, allows remove and image-toggle actions, and keeps model/custom-prompt draft state locally.
7. When the user runs translation, translation-with-explanation, or custom prompt, background composes one `/analyze/translate` request from the full ordered batch.
8. Non-empty text items are concatenated as numbered blocks, enabled preview images are sent sparsely, and ordered per-item metadata is attached for diagnostics.
9. The overlay first renders a loading state, then renders translated Markdown, explanations, raw-response details, or an error state.

## Overlay Rerun Flow

1. After at least one item has been appended, background stores a tab-scoped analysis session.
2. The overlay exposes translation, translation-with-explanation, and custom-prompt actions without forcing the user to recapture selection state.
3. When the user presses one of those buttons, the content script forwards only the requested action and optional draft inputs.
4. Background reuses the cached ordered session, including previously captured crop previews, instead of reacquiring live selection state.
5. The new API result is rendered into the same overlay, and the batch remains available until the overlay is explicitly closed.

This rerun flow exists because live browser selections are unreliable once the user starts interacting with overlay controls, while Phase 2 also needs crop correctness to survive scroll changes and selection loss.

## Free Rectangle Flow

1. Free-rectangle mode can start from the overlay button, the background context-menu route, or the keyboard command route.
2. The content runtime owns the on-page drag UI and returns viewport-space coordinates only after the user confirms a sufficiently large rectangle.
3. Background receives the rectangle payload, captures and crops immediately, and appends it as an image-first session item.
4. The appended item enters the same ordered batch as text selections, so image-only translation and custom-prompt requests use the same analyze route.

## Overlay Close and Clear Flow

1. Closing the overlay removes the content-side UI immediately.
2. The content runtime then sends a clear-session request to background.
3. Background deletes the tab-scoped batch session.
4. Any later rerun request fails closed until a new selection or rectangle item is added.

## Rich Result Rendering Flow

1. Background returns plain text fields from the Local API.
2. The content overlay passes result text through a renderer pipeline: Markdown parse, sanitize, and KaTeX auto-render.
3. Code blocks and inline code are excluded from math conversion.
4. Raw response text stays behind a details disclosure so debugging data is available without dominating the overlay.
5. If Markdown or math rendering fails, the overlay falls back to safe plain text instead of breaking the panel.

## Popup Bootstrap Flow

1. The popup loads saved extension settings from `chrome.storage.local`.
2. The popup checks `/health` on the Local API.
3. If health succeeds, the popup requests `/models`.
4. If model loading succeeds, the popup renders a reachable state with live model choices.
5. If model loading fails but health succeeded, the popup stays usable and renders a degraded state instead of failing closed.

This distinction lets users tell the difference between an offline Local API and a reachable API that is running in mock or config-fallback mode.
