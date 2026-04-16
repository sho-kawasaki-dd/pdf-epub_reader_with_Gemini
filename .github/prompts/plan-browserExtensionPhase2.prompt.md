## Plan: Browser Extension Phase 2

Phase 2 is implemented on top of the existing single-endpoint flow, not by introducing a second analyze API. The recommended approach is to keep `/analyze/translate` as the only analyze route, extend the extension session model from one selection to an ordered batch of up to 10 items, support per-item image inclusion with image capture cached at add-time for correctness, add free-rectangle capture through overlay/context-menu/shortcut entry points, and replace plain-text overlay rendering with safe Markdown + KaTeX rendering. Context Cache and token-count APIs stay out of Phase 2 and remain Phase 3 scope.

**Phases**

### Phase 2A: Scope Freeze and Contract Foundation

Goal: lock the rules and shared message/session shapes before any UI or API work diverges.

1. Freeze the Phase 2 decisions already made: no cache/token work in Phase 2; one combined API result per request; add selections from the overlay; default image inclusion is off; free-rectangle supports translation, translation-with-explanation, and custom prompt; raw response is hidden behind a details UI; max 10 items per batch; popup remains settings-only.
2. Extend shared runtime contracts in `browser-extension/src/shared/contracts/messages.ts`. Replace the single cached selection assumption with a batch/session model that can represent ordered items, per-item `includeImage`, free-rectangle vs text-selection origin, optional preview image, and close/clear actions. Keep `AnalysisAction` unchanged.
3. Refactor the background analysis session in `browser-extension/src/background/services/analysisSessionStore.ts` from single selection to batch selection. Each batch item should store the selection source, normalized text, viewport rect, cached preview image URL, crop timing, and `includeImage` flag. Change lifecycle semantics from “kept indefinitely per tab” to “kept until overlay is closed in that tab”.
4. Extend background bootstrap and commands. Update `browser-extension/manifest.json` to add the command shortcut and any additional context-menu exposure needed for free-rectangle initiation. Extend `browser-extension/src/background/menus/phase0ContextMenu.ts` into a multi-action menu registration flow, and update `browser-extension/src/background/entry.ts` to handle both existing translation clicks and new free-rectangle start requests plus command events.

Exit criteria: message contracts, tab session shape, and trigger entry points are stable enough that content/background/API can be implemented against one shared model.

### Phase 2B: Selection Accumulation and Capture Flows

Goal: let the user build and maintain a reusable batch of text and image-first items.

1. Rework content-side selection state. Keep the existing snapshot logic in `browser-extension/src/content/selection/snapshotStore.ts` for live text selections, but add a Phase 2 selection-batch controller under `browser-extension/src/content/selection/` that manages the current ordered item list, enforces the 10-item limit, and supports add/remove semantics only.
2. Add free-rectangle capture mode in content. Introduce a dedicated rectangle-selection controller under `browser-extension/src/content/selection/` that can be started from three entry points: overlay button, background-triggered context-menu action, and background-triggered keyboard shortcut. The controller should draw inside the content runtime, return viewport-space rects compatible with the existing crop pipeline, allow confirm/cancel, and produce an item with empty text for image-only requests.
3. Rework the add-selection flow. When the user presses the overlay Add button, content should collect the latest text selection snapshot and hand it to background; background should immediately capture/crop the preview image and cache it even though `includeImage` defaults to false. Free-rectangle items should always capture/crop immediately because they are image-first by definition.
4. Add explicit close/clear behavior from content so background clears the tab-scoped session when the overlay is dismissed.

Exit criteria: a tab can accumulate up to 10 ordered items, remove items, add image-first items, and preserve reusable crop data even after selection loss or scroll changes.

### Phase 2C: Analysis Pipeline and Browser API Compatibility

Goal: send one batch through the existing analyze route without introducing a second API surface.

1. Update the background orchestration in `browser-extension/src/background/usecases/runSelectionAnalysis.ts` and `browser-extension/src/background/gateways/tabMessagingGateway.ts`. Split responsibilities into: create/update session items, start free-rectangle mode, run analysis from the current batch, and rerun analysis with different actions/models/custom prompts without recollecting items.
2. Compose a single analyze request by numbering non-empty text items as `1.`, `2.`, `3.` with blank lines between blocks, while preserving full item order in metadata even for image-only items.
3. Keep the browser API route surface minimal. Reuse `src/browser_api/api/routers/analyze.py` and extend the existing request/command/result flow instead of adding a second route. The extension should continue posting to `/analyze/translate` via `browser-extension/src/shared/gateways/localApiGateway.ts`, but the request body must now support batch-aware `selection_metadata` and sparse image inclusion.
4. Relax the browser API request validation for image-only use cases in `src/browser_api/api/schemas/analyze.py`, `src/browser_api/application/dto.py`, and `src/browser_api/application/services/analyze_service.py`. `text` must no longer require `min_length=1` unconditionally; validation should become “at least one of non-empty text or one-or-more images is required”. Keep custom-prompt validation, but allow `custom_prompt` with empty text when images are present.
5. Extend request metadata instead of changing the response shape. Add optional batch item metadata to the analyze request schema so logs/debugging can still recover source order, item type, per-item `includeImage`, rect info, and image index mapping. Preserve backward compatibility by keeping current top-level metadata fields usable for a single item while adding an optional `items` array for Phase 2.

Exit criteria: text-only, mixed text+image, and image-only custom prompt flows all work through `/analyze/translate` with one stable response contract.

### Phase 2D: Overlay Rendering and Interaction Polish

Goal: make the Phase 2 overlay usable for daily work rather than just technically functional.

1. Replace plain-text rendering in `browser-extension/src/content/overlay/renderOverlay.ts` with a dedicated rich-text renderer module under `browser-extension/src/content/overlay/`. Recommended library stack: `marked` for Markdown parsing, `DOMPurify` for sanitization, and `KaTeX` auto-render for math.
2. Use the rendering pipeline `Markdown parse -> sanitize -> KaTeX render`, apply math only to non-code nodes, and fall back to safe plain text on any parse/render failure.
3. Update overlay UX in `browser-extension/src/content/overlay/renderOverlay.ts`. Add the batch list UI with remove buttons, per-item image toggles, Add Selection action, Free Rectangle action, and a collapsed details area for raw response.
4. Keep module-level draft state for model/custom prompt, extend it for temporary free-rectangle mode state if needed, and preserve the existing “rerun without recapture” behavior for translation, translation-with-explanation, and custom prompt.
5. Keep popup responsibilities unchanged. `browser-extension/src/popup/ui/renderPopup.ts` and `browser-extension/src/shared/storage/settingsStorage.ts` only need compatibility checks if new settings are introduced later, but no new Phase 2 popup features should be planned.

Exit criteria: the overlay can manage the full batch, safely render Markdown and math, expose image toggles, and rerun actions without forcing reselection.

### Phase 2E: Test Hardening and Documentation

Goal: make the Phase 2 work shippable and maintainable.

1. Add and update tests once the contract changes settle. Extend browser-extension unit tests for overlay batch rendering, add/remove actions, per-item image toggles, free-rectangle state transitions, renderer sanitization, code-block exclusion from math rendering, and background batch orchestration.
2. Extend browser API tests for image-only validation, mixed text+image validation, and batch metadata serialization.
3. Add a new Playwright smoke path for free-rectangle initiation and a new end-to-end flow for multi-selection + explanation/custom prompt.
4. Update developer documentation after tests pass. Revise `docs/developer/runtime-flows.md` for the new session lifecycle and free-rectangle flow, and update `docs/developer/architecture.md` so the runtime-first split explicitly covers multi-selection session ownership, close/clear semantics, and rich-result rendering responsibilities.

Exit criteria: unit, API, and E2E coverage reflect the new batch and rendering flows, and the developer docs describe the new runtime boundaries accurately.

**Relevant files**

- `d:/programming/py_apps/gem-read/browser-extension/manifest.json` — add shortcut command and any new context-menu reachable permissions/config needed for free-rectangle entry points
- `d:/programming/py_apps/gem-read/browser-extension/src/shared/contracts/messages.ts` — extend message contracts and overlay/session payloads from single selection to ordered batch items
- `d:/programming/py_apps/gem-read/browser-extension/src/content/entry.ts` — route Phase 2 content messages for add-selection, free-rectangle mode, and overlay close/clear
- `d:/programming/py_apps/gem-read/browser-extension/src/content/selection/snapshotStore.ts` — preserve and reuse the existing live text selection snapshot behavior as the base for add-selection
- `d:/programming/py_apps/gem-read/browser-extension/src/content/overlay/renderOverlay.ts` — batch UI, raw-response details toggle, renderer integration, free-rectangle start button, per-item image toggles
- `d:/programming/py_apps/gem-read/browser-extension/src/background/entry.ts` — handle multiple context-menu actions, shortcut command, and new session-control messages
- `d:/programming/py_apps/gem-read/browser-extension/src/background/menus/phase0ContextMenu.ts` — evolve from one selection-only entry to multi-action menu registration
- `d:/programming/py_apps/gem-read/browser-extension/src/background/services/analysisSessionStore.ts` — change the session model from one cached selection to a tab-scoped batch with explicit clear-on-close semantics
- `d:/programming/py_apps/gem-read/browser-extension/src/background/usecases/runSelectionAnalysis.ts` — separate “session mutation” from “run analysis”, compose numbered batch text, and support image-only batch items
- `d:/programming/py_apps/gem-read/browser-extension/src/background/gateways/tabMessagingGateway.ts` — extend tab message helpers for batch/session/free-rectangle messages
- `d:/programming/py_apps/gem-read/browser-extension/src/shared/gateways/localApiGateway.ts` — keep one analyze endpoint, but send batch-aware metadata and only the enabled images
- `d:/programming/py_apps/gem-read/browser-extension/src/popup/ui/renderPopup.ts` — verify no Phase 2 scope creep beyond compatibility
- `d:/programming/py_apps/gem-read/browser-extension/src/shared/storage/settingsStorage.ts` — verify existing settings persistence remains sufficient
- `d:/programming/py_apps/gem-read/src/browser_api/api/schemas/analyze.py` — relax validation for image-only requests and add batch metadata support
- `d:/programming/py_apps/gem-read/src/browser_api/application/dto.py` — carry expanded analyze command metadata without changing the endpoint surface
- `d:/programming/py_apps/gem-read/src/browser_api/application/services/analyze_service.py` — preserve current analyze flow while accepting empty text plus images
- `d:/programming/py_apps/gem-read/src/browser_api/api/routers/analyze.py` — keep the thin router boundary and reuse the existing route
- `d:/programming/py_apps/gem-read/browser-extension/__tests__/unit/content/renderOverlay.test.ts` — extend for batch UI and rich rendering
- `d:/programming/py_apps/gem-read/browser-extension/__tests__/unit/content/snapshotStore.test.ts` — preserve existing selection snapshot guarantees during Phase 2 refactors
- `d:/programming/py_apps/gem-read/browser-extension/__tests__/unit/background/runSelectionAnalysis.test.ts` — extend for batch composition, image toggle behavior, and session reuse
- `d:/programming/py_apps/gem-read/browser-extension/__tests__/e2e/phase0-overlay.spec.ts` — use as the base to add Phase 2 smoke scenarios
- `d:/programming/py_apps/gem-read/tests/test_browser_api/test_api/test_analyze_router.py` — extend schema/validation coverage for image-only requests and new metadata
- `d:/programming/py_apps/gem-read/tests/test_browser_api/test_application/test_analyze_service.py` — extend service coverage for empty-text image requests and unchanged mock behavior
- `d:/programming/py_apps/gem-read/docs/developer/runtime-flows.md` — update flow docs after implementation stabilizes
- `d:/programming/py_apps/gem-read/docs/developer/architecture.md` — update runtime ownership and Phase 2 boundaries after implementation stabilizes

**Verification**

1. Run `npm run test` in `browser-extension/` and confirm new unit coverage for batch session handling, free-rectangle mode, renderer sanitization, KaTeX fallback, and image-toggle behavior.
2. Run `npm run test:e2e` in `browser-extension/` and cover at minimum: existing text-selection flow, multi-selection batch flow, image-only free-rectangle flow, translation-with-explanation rerun, and custom-prompt image-only flow.
3. Run `uv run pytest tests/test_browser_api/ -q` and confirm `/analyze/translate` accepts text-only, text+images, and image-only requests while still rejecting empty text with no images.
4. Run `npm run build` in `browser-extension/` and verify the Markdown/KaTeX dependencies bundle cleanly under MV3 without CSP/runtime errors.
5. Run manual smoke checks in Chrome and Edge for all three free-rectangle entry points: overlay button, context menu, and keyboard shortcut.
6. Manually verify that turning image inclusion on after adding a text selection still uses the originally captured crop even after scroll/selection loss.
7. Manually verify that closing the overlay clears the batch session for that tab and disables rerun actions until a new item is captured.

**Decisions**

- Phase 2 excludes Context Cache and token counting even as API groundwork.
- Multi-selection returns one combined result from one analyze request.
- New text items are added from the overlay, not by repeated context-menu runs.
- Batch text is concatenated in order with numbered blocks.
- Text-selection items default to `includeImage=false`, but the crop is still cached at add-time for later correctness.
- Free-rectangle is available from overlay button, context menu, and keyboard shortcut from the start.
- Free-rectangle supports translation, translation-with-explanation, and custom prompt.
- Image-only custom prompt requests are allowed with empty `text`.
- Raw response is hidden behind a details-style affordance rather than always visible.
- Batch size is capped at 10 items.
- Session lifetime is tab-scoped and ends when the overlay is closed.
- Popup remains a settings/connectivity surface only.

**Further Considerations**

1. The highest technical risk is image-only compatibility through the reused `AnalysisRequest` path. The plan assumes empty `text` plus images can be accepted after browser_api validation is relaxed; if the underlying Gemini adapter proves to require non-empty text, add the smallest possible compatibility shim in `AnalyzeService` rather than creating a second endpoint.
2. The second highest technical risk is MV3 packaging of `DOMPurify` + `KaTeX` inside the overlay Shadow DOM. Validate build/CSP behavior before polishing UI details so renderer packaging does not block the rest of Phase 2.
3. Because image capture is cached even when `includeImage` defaults to off, performance on large/high-DPI pages should be measured early. If add-time capture becomes too expensive, only then consider a second-pass optimization instead of changing the functional plan first.
