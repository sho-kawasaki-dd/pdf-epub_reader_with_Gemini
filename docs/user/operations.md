# Core Operations

## Launch the Application

- On Windows PowerShell, run `.\gem-read_launch.ps1` from the repository root.
- The launcher script delegates to `uv run python -m pdf_epub_reader`.

## Open a Document

- Use the open command from the menu.
- Drag and drop a supported file onto the document pane.
- Reopen a recent file from the recent files menu.

If the document is password protected, the application prompts for a password before retrying the open operation.

## Navigate the Document

- Scroll through pages in the central document pane.
- Use the bookmark panel to jump to entries from the table of contents.
- Use zoom controls to change the viewport scale.

## Select Content

- Drag on the document to create a selection.
- Use `Ctrl+drag` to append more selections.
- Press `Esc` to clear the current selection set.

Each accepted selection becomes a numbered slot in the side panel. Slots can be pending, ready, or error.

## Run AI Actions

From the side panel you can:

- Run translation
- Run translation with explanation
- Submit a custom prompt
- Choose whether to force sending the selected region as an image
- Switch the active Gemini model for the current request

When the selection includes cropped image content, the request can be sent as multimodal input.

## Useful Shortcuts

- `Ctrl+B`: toggle bookmark panel
- `Ctrl+,`: open settings
- `Ctrl+Shift+G`: open cache management
- `Esc`: clear selections

## Use the Browser Extension Phase 3 Workflow

1. Start the local API with `uv run python -m browser_api`.
2. Open the extension popup and save the Local API Base URL.
3. Check the popup status badge.

Badge meanings:

- `Reachable`: extension can reach the local API and fetch a live model list
- `Mock Mode`: extension can reach the local API, but the API is returning fallback or mock-mode information
- `Unreachable`: extension cannot reach the configured local API URL

1. Select text on a page.
1. Run the first analysis from the page selection flow.

Available entry points:

- Browser command `Ctrl+Shift+8`: reopen the cached Gem Read session for the current tab. If no cached session exists yet, Gem Read shows a launcher-only overlay instead of a full panel.
- Browser command `Ctrl+Shift+9`: append the current live text selection to the batch. If no live text selection exists, Gem Read opens the full overlay with an explicit error instead of failing silently.
- Browser command `Ctrl+Shift+Y`: start free-rectangle capture
- Popup button `Open Overlay On Active Tab`: helper entry point that uses the same cached-session reopen flow as `Ctrl+Shift+8`

1. In the overlay, inspect the crop preview, batch list, and latest result.
1. If you want a different action without reselection, use one of the overlay actions:

- `Translate`
- `Translate + Explain`
- `Run Custom Prompt`

1. Optionally enter a different model ID in the overlay before rerunning.
1. Use the keyboard bindings when the overlay is visible:

- `Esc`: minimize the overlay
- `Shift+Esc`: close the overlay and clear the tab session
- `Ctrl+Enter`: submit the custom prompt while the custom prompt textarea is focused
- `Alt+R`: rerun the last action with the last model and last custom prompt when focus is not in an editable control

1. Use the minimize button or `Esc` if you want to keep the current session available while reducing the overlay footprint.

Current Phase 3 scope:

- Batch sessions across multiple text selections
- Free-rectangle capture mode
- Popup-managed local API URL and default model
- Overlay reruns for translation, explanation, and custom prompt
- Keyboard-first cached-session reopen and rerun flow

## Use Article Context and Cache in the Browser Extension

When Gem Read can extract a long article from the current page, the overlay shows an `Article Context` section and a `Tokens` section.

What you can expect:

- `Article Context` shows the extracted article title, extraction source, and cache status for the current tab.
- `Tokens` shows the current selection request estimate, the extracted article token baseline, and the last response usage when Gemini reports it.
- If the article is large enough and the current model supports caching, Gem Read may create one article cache automatically for the active tab.
- If token counting is unavailable, Gem Read keeps the overlay usable and shows a degraded token message instead of hiding the rest of the workflow.

The active article cache is scoped to the current tab and current model. Gem Read invalidates or recreates it when needed.

Common invalidation reasons:

- The page URL changed
- The selected model changed
- The extracted article body changed
- The remote cache expired
- You used `Delete Cache` in the overlay

Switching action mode (Translate, Translate + Explain, or Run Custom Prompt) or changing output language does **not** invalidate the article cache. Gem Read encodes the action and output language in each request directly, so one article cache serves all three actions and all language settings without recreating it.

Current limitations:

- Reload or browser-restart session restore
- Restricted pages such as browser internal pages, extension pages, and other URLs where content scripts cannot be injected

Unsupported or extraction-failure pages fall back to the existing selection-based flow. In that case you can still build a batch, rerun actions, and use rectangle capture, but article-wide cache and article token display may be unavailable.

For `Ctrl+Shift+9`, Gem Read uses only the current live text selection. It does not reuse the last rectangle capture or the previous batch item when no live selection is active.

For `Ctrl+Shift+8`, Gem Read does not synthesize a new batch or reopen a purely minimized UI state on its own. It only restores the full overlay when the current tab already has a cached Gem Read session in the background store.
