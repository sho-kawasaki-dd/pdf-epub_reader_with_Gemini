# Testing Guide

## Testing Strategy

The project is designed so that most logic can be tested without launching a real Qt UI.

- Presenters are tested against mock views and mock models.
- Models are tested as async Python components.
- Protocols define the stable contracts used by both production code and tests.

## Main Test Areas

### Document Model

Document tests cover:

- PDF and EPUB open flows
- rendering behavior
- extraction logic
- page cache behavior
- table-of-contents extraction

### AI Model

AI tests cover:

- request construction
- multimodal request handling
- retry behavior
- model enumeration
- context cache behavior

### Presenters

Presenter tests cover:

- open-file orchestration
- selection state updates
- side panel actions
- cache orchestration
- UI language application

## Practical Rule

If a new feature adds branching logic, prefer putting that logic in a presenter or model and covering it with tests before expanding the Qt view layer.

## Smoke Launch Checks

- Validate the canonical startup path with `uv run python -m pdf_epub_reader`.
- On Windows, also validate `.\gem-read_launch.ps1` to ensure the PowerShell wrapper still resolves the repository root correctly.
