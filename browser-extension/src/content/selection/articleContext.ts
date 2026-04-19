import { Readability } from '@mozilla/readability';

import type {
  ArticleContext,
  ArticleContextResponse,
} from '../../shared/contracts/messages';

const READABILITY_MIN_TEXT_LENGTH = 160;
const DOM_FALLBACK_MIN_TEXT_LENGTH = 200;
const DOM_CANDIDATE_SELECTORS = [
  'article',
  'main article',
  'main',
  '[role="main"]',
  '#main',
  '#content',
  '.main-content',
  '.article-content',
  '.article-body',
  '.post-content',
  '.entry-content',
];
const BLOCK_TEXT_SELECTOR =
  'p, li, blockquote, pre, figcaption, h1, h2, h3, h4, h5, h6';
const STRIP_SELECTOR =
  'script, style, noscript, template, svg, canvas, iframe, form, button';
const FNV_OFFSET_BASIS = 0xcbf29ce484222325n;
const FNV_PRIME = 0x100000001b3n;
// 記事本文のハッシュ計算に使う先頭文字数。
// 広告挿入など動的 DOM 変化の影響を受けにくくするため、先頭部分のみを対象とする。
const BODY_HASH_PREFIX_LENGTH = 2000;

export function collectArticleContext(
  documentRef: Document = document
): ArticleContextResponse {
  if (!documentRef.body) {
    return {
      ok: false,
      error: 'Document body is unavailable for article extraction.',
    };
  }

  const url = window.location.href;
  const readabilityContext = extractWithReadability(documentRef, url);
  if (readabilityContext) {
    return {
      ok: true,
      payload: readabilityContext,
    };
  }

  const fallbackContext = extractWithDomFallback(documentRef, url);
  if (fallbackContext) {
    return {
      ok: true,
      payload: fallbackContext,
    };
  }

  return {
    ok: false,
    error: 'Readable article context could not be extracted on this page.',
  };
}

function extractWithReadability(
  documentRef: Document,
  url: string
): ArticleContext | null {
  const clonedDocument = cloneExtractionDocument(documentRef);
  const reader = new Readability(clonedDocument, {
    charThreshold: READABILITY_MIN_TEXT_LENGTH,
  });
  const parsed = reader.parse();
  if (!parsed) {
    return null;
  }

  const bodyText = normalizeArticleText(parsed.textContent ?? '');
  if (bodyText.length < READABILITY_MIN_TEXT_LENGTH) {
    return null;
  }

  return finalizeArticleContext({
    title: normalizeInlineText(parsed.title) || normalizeInlineText(documentRef.title),
    url,
    bodyText,
    source: 'readability',
    excerpt: normalizeInlineText(parsed.excerpt ?? ''),
    byline: normalizeInlineText(parsed.byline ?? ''),
    siteName: normalizeInlineText(parsed.siteName ?? ''),
  });
}

function extractWithDomFallback(
  documentRef: Document,
  url: string
): ArticleContext | null {
  const candidates = collectFallbackCandidates(documentRef);
  let bestCandidate: { element: Element; bodyText: string; score: number } | null = null;

  for (const element of candidates) {
    const bodyText = extractStructuredText(element);
    if (bodyText.length < DOM_FALLBACK_MIN_TEXT_LENGTH) {
      continue;
    }

    const score = scoreCandidate(element, bodyText);
    if (!bestCandidate || score > bestCandidate.score) {
      bestCandidate = { element, bodyText, score };
    }
  }

  if (!bestCandidate) {
    return null;
  }

  const title =
    normalizeInlineText(
      bestCandidate.element.querySelector('h1, h2')?.textContent ?? ''
    ) || normalizeInlineText(documentRef.title);

  return finalizeArticleContext({
    title,
    url,
    bodyText: bestCandidate.bodyText,
    source: 'dom-fallback',
  });
}

function cloneExtractionDocument(documentRef: Document): Document {
  const clonedDocument = documentRef.cloneNode(true) as Document;
  for (const node of clonedDocument.querySelectorAll(STRIP_SELECTOR)) {
    node.remove();
  }
  return clonedDocument;
}

function collectFallbackCandidates(documentRef: Document): Element[] {
  const seen = new Set<Element>();
  const candidates: Element[] = [];

  for (const selector of DOM_CANDIDATE_SELECTORS) {
    for (const element of Array.from(documentRef.querySelectorAll(selector))) {
      if (seen.has(element)) {
        continue;
      }

      seen.add(element);
      candidates.push(element);
    }
  }

  return candidates;
}

function extractStructuredText(element: Element): string {
  const blockTexts = Array.from(element.querySelectorAll(BLOCK_TEXT_SELECTOR))
    .map((node) => normalizeInlineText(node.textContent ?? ''))
    .filter(Boolean);

  if (blockTexts.length > 0) {
    return blockTexts.join('\n\n');
  }

  return normalizeArticleText(element.textContent ?? '');
}

function normalizeArticleText(text: string): string {
  const normalized = text.replace(/\u00a0/g, ' ').replace(/\r/g, '');
  const paragraphs = normalized
    .split(/\n+/)
    .map((segment) => normalizeInlineText(segment))
    .filter(Boolean);

  if (paragraphs.length === 0) {
    return '';
  }

  return paragraphs.join('\n\n');
}

function normalizeInlineText(text: string): string {
  return text.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
}

function scoreCandidate(element: Element, bodyText: string): number {
  const blockCount = element.querySelectorAll(BLOCK_TEXT_SELECTOR).length;
  const linkTextLength = Array.from(element.querySelectorAll('a')).reduce(
    (total, link) => total + normalizeInlineText(link.textContent ?? '').length,
    0
  );
  const linkDensity = bodyText.length === 0 ? 1 : linkTextLength / bodyText.length;

  return bodyText.length + blockCount * 80 - Math.round(linkDensity * 400);
}

function finalizeArticleContext(input: {
  title: string;
  url: string;
  bodyText: string;
  source: ArticleContext['source'];
  excerpt?: string;
  byline?: string;
  siteName?: string;
}): ArticleContext {
  const normalizedBodyText = normalizeArticleText(input.bodyText);
  const normalizedTitle = input.title || 'Untitled article';

  return {
    title: normalizedTitle,
    url: input.url,
    bodyText: normalizedBodyText,
    bodyHash: computeBodyHash(normalizedBodyText),
    source: input.source,
    textLength: normalizedBodyText.length,
    excerpt: input.excerpt || undefined,
    byline: input.byline || undefined,
    siteName: input.siteName || undefined,
  };
}

function computeBodyHash(text: string): string {
  // 先頭 BODY_HASH_PREFIX_LENGTH 文字のみをハッシュ対象とする。
  // これにより、広告・推薦コンテンツなど本文末尾への動的挿入による
  // 誤ったキャッシュ無効化を防ぐ。
  const prefix = text.slice(0, BODY_HASH_PREFIX_LENGTH);
  let hash = FNV_OFFSET_BASIS;
  for (const character of prefix.normalize('NFKC')) {
    hash ^= BigInt(character.codePointAt(0) ?? 0);
    hash = BigInt.asUintN(64, hash * FNV_PRIME);
  }

  return hash.toString(16).padStart(16, '0');
}