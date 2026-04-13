# Settings and Cache

These settings apply regardless of whether you launch Gem Read with `.\gem-read_launch.ps1` or `uv run python -m pdf_epub_reader`.

## Settings Dialog

The settings dialog is split into three tabs.

### Rendering

- Render format: PNG or JPEG
- JPEG quality
- Default DPI
- Page cache size
- High-quality downscale toggle

### Detection

- Automatic embedded image detection
- Automatic math font detection

### AI Models

- Default model
- Available model list
- Selected models
- Output language
- Translation system prompt
- Context cache TTL

## UI Language vs AI Output Language

These are separate settings.

- UI language changes menus, buttons, and visible application text.
- AI output language changes the language requested from Gemini.

## Context Cache

Context cache stores the full extracted document text on the Gemini side for repeated analysis requests.

You can:

- Create a cache
- Invalidate a cache
- Inspect cache status
- Update cache TTL
- View available caches in the cache management dialog

## Cache Tips

- Cache is model-specific.
- Opening a different document invalidates the previous cache.
- Changing to a different model may require cache invalidation.
- The application also invalidates cache during shutdown cleanup.
