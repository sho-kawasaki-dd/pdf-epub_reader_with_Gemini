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

- Browser command `Ctrl+Shift+O`: reopen the overlay for the current tab
- Browser command `Ctrl+Shift+B`: append the current live text selection to the batch
- Browser command `Ctrl+Shift+Y`: start free-rectangle capture
- Popup button `Open Overlay On Active Tab`: helper entry point that uses the same reopen flow as `Ctrl+Shift+O`

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
- Keyboard-first overlay reopen and rerun flow

Current limitations:

- Article-wide extraction
- Context Cache integration from the extension UI
- Reload or browser-restart session restore
- Restricted pages such as browser internal pages, extension pages, and other URLs where content scripts cannot be injected

For `Ctrl+Shift+B`, Gem Read uses only the current live text selection. It does not reuse the last rectangle capture or the previous batch item when no live selection is active.
