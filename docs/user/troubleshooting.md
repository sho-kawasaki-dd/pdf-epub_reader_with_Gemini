# Troubleshooting

## PowerShell Launcher Does Not Start

Check the following:

- Run `.\gem-read_launch.ps1` from the repository root
- `uv` is installed and available on `PATH`
- Dependencies have been installed with `uv sync --dev`
- PowerShell execution policy is not blocking local scripts in the current session

## AI Features Do Not Work

Check the following:

- `GEMINI_API_KEY` is present in `.env`
- The selected model is valid and enabled
- The machine has network access to Gemini API
- The side panel model selector is not disabled

## Document Opens but AI Fails

This usually means local viewing is working but AI configuration is incomplete.

Check:

- API key configuration
- Selected models in settings
- Error text shown in the side panel result area

## Cache Operations Fail

Possible causes:

- The selected model does not support context caching
- The API request failed remotely
- Cached content expired

If needed, invalidate the cache and create it again.

## Math or Markdown Rendering Looks Wrong

Check whether the response includes Markdown or LaTeX syntax that should be rendered in the side panel. If output is still incorrect, verify the local KaTeX bundle and the rendered response content.

## UI Language Looks Wrong After Change

Main window and side panel update immediately. Some dialogs apply new language text when they are opened again.
