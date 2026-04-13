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
