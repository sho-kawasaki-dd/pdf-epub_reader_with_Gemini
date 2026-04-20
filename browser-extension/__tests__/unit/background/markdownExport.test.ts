import { describe, expect, it, vi, beforeEach } from 'vitest';

import {
  buildMarkdownFilename,
  downloadMarkdownFile,
  sanitizePageTitle,
} from '../../../src/background/gateways/downloadGateway';
import { buildMarkdownExportDocument } from '../../../src/background/services/markdownExportService';
import { getChromeMock } from '../../mocks/chrome';

describe('markdownExport', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('builds markdown with default export sections and omits disabled metadata', () => {
    const markdown = buildMarkdownExportDocument(
      {
        action: 'translation_with_explanation',
        modelName: 'gemini-2.5-pro',
        pageTitle: 'Example article',
        pageUrl: 'https://example.com/article',
        translatedText: 'Translated body',
        explanation: 'Supporting explanation',
        rawResponse: 'raw payload',
        sessionItems: [
          {
            id: 'selection-1',
            source: 'text-selection',
            includeImage: true,
            selection: {
              text: 'First selected paragraph',
              rect: { left: 1, top: 2, width: 3, height: 4 },
              viewportWidth: 100,
              viewportHeight: 100,
              devicePixelRatio: 1,
              url: 'https://example.com/article',
              pageTitle: 'Example article',
            },
          },
        ],
        articleContext: {
          title: 'Example article',
          url: 'https://example.com/article',
          bodyText: 'body',
          bodyHash: 'hash-1',
          source: 'readability',
          textLength: 1234,
          byline: 'Author',
          siteName: 'Example',
        },
        usage: {
          totalTokenCount: 42,
        },
      },
      {
        includeExplanation: true,
        includeSelections: true,
        includeRawResponse: false,
        includeArticleMetadata: false,
        includeUsageMetrics: false,
        includeYamlFrontmatter: false,
      },
      {
        exportedAt: new Date('2026-04-20T10:30:00.000Z'),
      }
    );

    expect(markdown).toContain('# Example article');
    expect(markdown).toContain('- Exported At: 2026-04-20T10:30:00.000Z');
    expect(markdown).toContain('## Selections');
    expect(markdown).toContain('1. First selected paragraph');
    expect(markdown).toContain('## Gemini Response');
    expect(markdown).toContain('Translated body');
    expect(markdown).toContain('## Explanation');
    expect(markdown).toContain('Supporting explanation');
    expect(markdown).not.toContain('## Raw Response');
    expect(markdown).not.toContain('## Article Metadata');
    expect(markdown).not.toContain('## Usage Metrics');
    expect(markdown.startsWith('---')).toBe(false);
  });

  it('includes optional sections when enabled', () => {
    const markdown = buildMarkdownExportDocument(
      {
        action: 'custom_prompt',
        modelName: 'gemini-2.5-flash',
        pageTitle: 'Title / with reserved chars?',
        pageUrl: 'https://example.com/article',
        translatedText: 'Translated body',
        explanation: 'Supporting explanation',
        rawResponse: 'raw payload',
        selectedText: 'Selected source',
        articleContext: {
          title: 'Example article',
          url: 'https://example.com/article',
          bodyText: 'body',
          bodyHash: 'hash-1',
          source: 'dom-fallback',
          textLength: 987,
          excerpt: 'Short excerpt',
        },
        usage: {
          promptTokenCount: 10,
          cachedContentTokenCount: 5,
          candidatesTokenCount: 3,
          totalTokenCount: 18,
        },
      },
      {
        includeExplanation: true,
        includeSelections: true,
        includeRawResponse: true,
        includeArticleMetadata: true,
        includeUsageMetrics: true,
        includeYamlFrontmatter: true,
      },
      {
        exportedAt: new Date('2026-04-20T10:30:00.000Z'),
      }
    );

    expect(markdown.startsWith('---\n')).toBe(true);
    expect(markdown).toContain('selectionCount: 1');
    expect(markdown).toContain('## Raw Response');
    expect(markdown).toContain('```text');
    expect(markdown).toContain('## Article Metadata');
    expect(markdown).toContain('- Source: dom-fallback');
    expect(markdown).toContain('## Usage Metrics');
    expect(markdown).toContain('- Total Tokens: 18');
  });

  it('omits explanation and selection sections when those toggles are disabled', () => {
    const markdown = buildMarkdownExportDocument(
      {
        action: 'translation_with_explanation',
        modelName: 'gemini-2.5-pro',
        pageTitle: 'Example article',
        pageUrl: 'https://example.com/article',
        translatedText: 'Translated body',
        explanation: 'Supporting explanation',
        rawResponse: 'raw payload',
        selectedText: 'Selected source',
      },
      {
        includeExplanation: false,
        includeSelections: false,
        includeRawResponse: true,
        includeArticleMetadata: false,
        includeUsageMetrics: false,
        includeYamlFrontmatter: false,
      },
      {
        exportedAt: new Date('2026-04-20T10:30:00.000Z'),
      }
    );

    expect(markdown).toContain('## Gemini Response');
    expect(markdown).toContain('Translated body');
    expect(markdown).toContain('## Raw Response');
    expect(markdown).not.toContain('## Explanation');
    expect(markdown).not.toContain('Supporting explanation');
    expect(markdown).not.toContain('## Selections');
    expect(markdown).not.toContain('Selected source');
    expect(markdown.startsWith('---')).toBe(false);
  });

  it('sanitizes the page title and formats the markdown filename timestamp', () => {
    expect(sanitizePageTitle('  Example:/\\?%*:|"<> title -  ')).toBe(
      'Example----------- title'
    );
    expect(
      buildMarkdownFilename(
        'Example:/\\?%*:|"<> title',
        new Date(2026, 3, 20, 10, 30, 45)
      )
    ).toBe('Example----------- title-20260420-103045.md');
  });

  it('downloads markdown with a generated filename', async () => {
    const chromeMock = getChromeMock();
    (
      chromeMock.downloads.download as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation((_options, callback) => {
      callback?.(88);
    });

    const result = await downloadMarkdownFile({
      markdown: '# Export',
      pageTitle: 'Example article',
      exportedAt: new Date(2026, 3, 20, 10, 30, 45),
    });

    expect(chromeMock.downloads.download).toHaveBeenCalledWith(
      expect.objectContaining({
        url: 'data:text/markdown;charset=utf-8,%23%20Export',
        filename: 'Example article-20260420-103045.md',
        saveAs: false,
        conflictAction: 'uniquify',
      }),
      expect.any(Function)
    );
    expect(result).toEqual({
      downloadId: 88,
      filename: 'Example article-20260420-103045.md',
    });
  });

  it('maps chrome.downloads failures to a typed error message', async () => {
    const chromeMock = getChromeMock();
    (
      chromeMock.downloads.download as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation((_options, callback) => {
      chrome.runtime.lastError = {
        message: 'The download was blocked.',
      } as chrome.runtime.LastError;
      callback?.(undefined);
      chrome.runtime.lastError = undefined;
    });

    await expect(
      downloadMarkdownFile({
        markdown: '# Export',
        pageTitle: 'Example article',
        exportedAt: new Date(2026, 3, 20, 10, 30, 45),
      })
    ).rejects.toThrow('Markdown download failed: The download was blocked.');
  });
});
