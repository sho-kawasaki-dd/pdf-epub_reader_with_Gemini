# Getting Started

## What This App Does

Gem Read is a local desktop reader for PDF and EPUB documents.
It lets you open documents, select one or more rectangular regions, and send the extracted content to Gemini for translation or custom analysis.

## Requirements

- Python 3.13 or newer
- A desktop environment that can run a PySide6 application
- `GEMINI_API_KEY` if you want to use AI features

## Install

```bash
uv sync --dev
```

## Configure Environment

Create a `.env` file in the repository root:

```env
GEMINI_API_KEY=your-api-key-here
```

The application can start without this key, but AI features will fail until the key is set.

## Launch

```bash
uv run python -m pdf_epub_reader
```

## Launch from Windows PowerShell

From the repository root, you can also use the bundled launcher:

```powershell
.\gem-read_launch.ps1
```

## First Run Checklist

1. Open a PDF or EPUB file.
2. Confirm that pages render in the main document pane.
3. Open the settings dialog and review rendering and AI options.
4. If you plan to use AI, choose available models in settings and confirm the side panel model selector is enabled.
5. Try a simple selection and run a translation request.
