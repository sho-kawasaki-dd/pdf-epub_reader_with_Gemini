export interface DownloadMarkdownFileOptions {
  markdown: string;
  pageTitle: string;
  exportedAt?: Date;
}

export interface DownloadMarkdownFileResult {
  downloadId: number;
  filename: string;
}

export async function downloadMarkdownFile(
  options: DownloadMarkdownFileOptions
): Promise<DownloadMarkdownFileResult> {
  const exportedAt = options.exportedAt ?? new Date();
  const filename = buildMarkdownFilename(options.pageTitle, exportedAt);
  const url = buildMarkdownDataUrl(options.markdown);
  const downloadId = await new Promise<number>((resolve, reject) => {
    chrome.downloads.download(
      {
        url,
        filename,
        saveAs: false,
        conflictAction: 'uniquify',
      },
      (result) => {
        const lastError = chrome.runtime.lastError;
        if (lastError) {
          reject(new Error(`Markdown download failed: ${lastError.message}`));
          return;
        }

        if (typeof result !== 'number') {
          reject(new Error('Markdown download did not return a download id.'));
          return;
        }

        resolve(result);
      }
    );
  });

  return {
    downloadId,
    filename,
  };
}

export function buildMarkdownFilename(
  pageTitle: string,
  exportedAt: Date
): string {
  const sanitizedTitle = sanitizePageTitle(pageTitle);
  return `${sanitizedTitle}-${formatTimestamp(exportedAt)}.md`;
}

export function sanitizePageTitle(pageTitle: string): string {
  const sanitized = pageTitle
    .trim()
    .replace(/[\/\\?%*:|"<>]/g, '-')
    .replace(/\s+/g, ' ')
    .slice(0, 80)
    .replace(/[\s-]+$/g, '')
    .trim();

  return sanitized || 'gem-read-export';
}

function buildMarkdownDataUrl(markdown: string): string {
  return `data:text/markdown;charset=utf-8,${encodeURIComponent(markdown)}`;
}

function formatTimestamp(date: Date): string {
  const year = date.getFullYear().toString().padStart(4, '0');
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  const hour = `${date.getHours()}`.padStart(2, '0');
  const minute = `${date.getMinutes()}`.padStart(2, '0');
  const second = `${date.getSeconds()}`.padStart(2, '0');
  return `${year}${month}${day}-${hour}${minute}${second}`;
}
