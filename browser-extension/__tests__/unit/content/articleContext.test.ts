import { beforeEach, describe, expect, it, vi } from 'vitest';

const parseMock = vi.hoisted(() => vi.fn());

vi.mock('@mozilla/readability', () => ({
  Readability: class {
    parse() {
      return parseMock();
    }
  },
}));

describe('articleContext', () => {
  beforeEach(() => {
    vi.resetModules();
    parseMock.mockReset();
    document.body.innerHTML = '';
    document.title = 'Original title';
    window.history.replaceState({}, '', 'http://localhost:3000/articles/readability');
  });

  it('prefers readability output and computes a stable body hash', async () => {
    document.body.innerHTML = `
      <article>
        <h1>Ignored DOM title</h1>
        <p>Ignored paragraph</p>
      </article>
    `;
    parseMock.mockReturnValue({
      title: 'Readable article',
      textContent:
        '  First paragraph with useful context and enough detail to look like a real article body that can seed later cache logic.\n\nSecond paragraph keeps enough length for extraction and confirms that normalization still preserves stable hashing across repeated calls.  ',
      excerpt: 'Short summary',
      byline: 'Author Name',
      siteName: 'Gem Read Tests',
    });

    const { collectArticleContext } = await import(
      '../../../src/content/selection/articleContext'
    );
    const result = collectArticleContext();

    expect(result.ok).toBe(true);
    expect(result.payload).toEqual(
      expect.objectContaining({
        title: 'Readable article',
        url: 'http://localhost:3000/articles/readability',
        source: 'readability',
        excerpt: 'Short summary',
        byline: 'Author Name',
        siteName: 'Gem Read Tests',
        bodyText:
          'First paragraph with useful context and enough detail to look like a real article body that can seed later cache logic.\n\nSecond paragraph keeps enough length for extraction and confirms that normalization still preserves stable hashing across repeated calls.',
        bodyHash: expect.any(String),
      })
    );
    expect(result.payload?.textLength).toBeGreaterThanOrEqual(160);

    const secondResult = collectArticleContext();
    expect(secondResult.ok).toBe(true);
    expect(secondResult.payload?.bodyHash).toBe(result.payload?.bodyHash);
  });

  it('falls back to lightweight DOM extraction when readability cannot parse', async () => {
    document.body.innerHTML = `
      <main>
        <h1>Fallback title</h1>
        <p>First fallback paragraph carries enough detail for article extraction to continue safely and give the overlay a reusable article context foundation.</p>
        <p>Second fallback paragraph adds more body text so the content clears the minimum threshold without relying on any site specific selector tuning.</p>
        <nav><a href="#">Ignore me</a></nav>
      </main>
    `;
    parseMock.mockReturnValue(null);

    const { collectArticleContext } = await import(
      '../../../src/content/selection/articleContext'
    );
    const result = collectArticleContext();

    expect(result.ok).toBe(true);
    expect(result.payload).toEqual(
      expect.objectContaining({
        title: 'Fallback title',
        source: 'dom-fallback',
        bodyText: expect.stringContaining(
          'First fallback paragraph carries enough detail for article extraction to continue safely'
        ),
      })
    );
    expect(result.payload?.textLength).toBeGreaterThanOrEqual(200);
  });

  it('returns a non-fatal failure when no article-like content can be extracted', async () => {
    document.body.innerHTML = `
      <div class="toolbar">
        <button>Open</button>
        <button>Close</button>
      </div>
    `;
    parseMock.mockReturnValue(null);

    const { collectArticleContext } = await import(
      '../../../src/content/selection/articleContext'
    );

    expect(collectArticleContext()).toEqual({
      ok: false,
      error: 'Readable article context could not be extracted on this page.',
    });
  });
});