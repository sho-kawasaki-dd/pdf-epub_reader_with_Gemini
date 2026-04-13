# Architecture Guide

## Architectural Style

The application uses MVP with a passive view approach.

- View classes are responsible for rendering widgets and forwarding user actions through callbacks.
- Presenters coordinate user actions, model calls, and view updates.
- Models implement document processing and Gemini API logic without depending on Qt.
- Infrastructure isolates Qt and asyncio integration.

## Main Boundaries

### View Layer

The view layer is implemented with PySide6 widgets and dialogs. It knows nothing about business logic beyond callback registration and display commands.

### Presenter Layer

The presenter layer depends on Protocol contracts rather than concrete view or model implementations. This keeps tests lightweight and makes the dependency direction stable.

### Model Layer

The model layer exposes async methods for document rendering, selection extraction, Gemini requests, and context cache operations.

### Infrastructure Layer

The infrastructure layer integrates Qt and asyncio using qasync, allowing presenters to await model operations without blocking the GUI thread.

## Key Entry Points

- Windows launcher: `gem-read_launch.ps1`
- Application composition: `src/pdf_epub_reader/app.py`
- Event loop integration: `src/pdf_epub_reader/infrastructure/event_loop.py`
- Main UI orchestration: `src/pdf_epub_reader/presenters/main_presenter.py`
- Side panel AI orchestration: `src/pdf_epub_reader/presenters/panel_presenter.py`
- Document processing: `src/pdf_epub_reader/models/document_model.py`
- Gemini integration: `src/pdf_epub_reader/models/ai_model.py`

## Why These Diagrams Matter

This project has several flows that are easy to misunderstand from code alone:

- Qt and asyncio are integrated but isolated
- selection state is managed across async completion boundaries
- cache lifecycle depends on model identity and document lifecycle
- side panel actions are separated from document interaction logic

The diagrams in `docs/developer/diagrams/` are intended to explain exactly those points.
