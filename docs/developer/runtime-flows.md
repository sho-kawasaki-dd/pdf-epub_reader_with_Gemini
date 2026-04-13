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
