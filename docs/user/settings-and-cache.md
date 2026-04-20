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

## Browser Extension Popup Settings

The browser extension popup also stores Markdown export preferences.

Available toggles:

- Explanation
- Selected source text
- Raw response
- Article metadata
- Usage metrics
- YAML frontmatter

Default export behavior keeps `Explanation` and `Selected source text` enabled, while raw response, article metadata, usage metrics, and YAML frontmatter stay off until you opt in.

These popup settings control the `Download Markdown` action in the overlay Gemini tab. Exporting again after changing a toggle uses the updated popup state.

## Context Cache

Context cache stores the full extracted document text on the Gemini side for repeated analysis requests.

In the browser extension, this is managed as one active article cache per tab.

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
- Switching action mode (translation, explanation, or custom prompt) does **not** require a new cache. One cache serves all three actions.
- Changing output language does **not** require a new cache. The language is sent with each request, not stored in the cache.

## Browser Extension Cache Behavior

For article pages in the browser extension:

- Gem Read first tries Readability-based extraction, then falls back to a lighter DOM-based extraction.
- Automatic cache creation is conditional. It only happens when article extraction succeeds, the article is large enough, and the selected model is expected to support caching.
- The overlay shows whether the cache is active, invalidated, unsupported, or degraded.
- `Delete Cache` removes the active cache for the current tab only.
- One article cache serves all three overlay actions (Translate, Translate + Explain, and Run Custom Prompt). Switching between them does not recreate the cache.
- Changing output language in the popup settings does not recreate the article cache. The new language takes effect on the next analysis request.

The cache can disappear without direct user action when:

- You navigate to a new URL in the same tab
- You switch to a different model
- Gemini expires the cache TTL
- Gem Read detects that the extracted article body hash changed

## Token Display in the Browser Extension

The overlay can show three token-related views:

- Current request estimate: the current selection batch before sending
- Article baseline: the extracted article size used for cache decisions
- Last response usage: prompt, cached-content, output, and total tokens from Gemini when available

If the local API cannot return token counts, the overlay keeps working and shows a degraded token message instead of failing closed.
