import {
  OUTPUT_IMAGE_QUALITY,
  OUTPUT_IMAGE_TYPE,
  OUTPUT_MAX_LONG_EDGE,
  type UiLanguage,
} from '../../shared/config/phase0';
import type { SelectionCapturePayload } from '../../shared/contracts/messages';
import { t } from '../../shared/i18n/translator';

/**
 * viewport 座標の selection を screenshot bitmap に合わせて crop/resize し、
 * Local API へ送る補助画像を browser 側で前処理する。
 * こうしておくと Python 側はブラウザ依存の座標補正を知らずに済み、送信 payload も小さく保てる。
 */
export async function cropSelectionImage(
  screenshotDataUrl: string,
  selection: SelectionCapturePayload,
  uiLanguage: UiLanguage = 'en'
): Promise<{ imageDataUrl: string; durationMs: number }> {
  const startedAt = performance.now();
  const imageBlob = await fetch(screenshotDataUrl).then((response) =>
    response.blob()
  );
  const bitmap = await createImageBitmap(imageBlob);

  // captureVisibleTab の bitmap サイズは CSS px と一致しないため、bitmap 比率へ補正して crop する。
  const scaleX = bitmap.width / selection.viewportWidth;
  const scaleY = bitmap.height / selection.viewportHeight;
  const sourceX = clamp(selection.rect.left * scaleX, 0, bitmap.width - 1);
  const sourceY = clamp(selection.rect.top * scaleY, 0, bitmap.height - 1);
  const sourceWidth = clamp(
    selection.rect.width * scaleX,
    1,
    bitmap.width - sourceX
  );
  const sourceHeight = clamp(
    selection.rect.height * scaleY,
    1,
    bitmap.height - sourceY
  );

  if (sourceWidth <= 0 || sourceHeight <= 0) {
    throw new Error(t(uiLanguage, 'bgErrorInvalidCrop'));
  }

  // 長辺だけを抑えて、可読性を大きく落とさずに転送量と Gemini 入力コストを下げる。
  const { outputWidth, outputHeight } = getOutputSize(
    sourceWidth,
    sourceHeight
  );
  const canvas = new OffscreenCanvas(outputWidth, outputHeight);
  const context = canvas.getContext('2d');
  if (!context) {
    throw new Error(t(uiLanguage, 'bgErrorOffscreenContext'));
  }

  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = 'high';
  context.drawImage(
    bitmap,
    sourceX,
    sourceY,
    sourceWidth,
    sourceHeight,
    0,
    0,
    outputWidth,
    outputHeight
  );

  const outputBlob = await canvas.convertToBlob({
    type: OUTPUT_IMAGE_TYPE,
    quality: OUTPUT_IMAGE_QUALITY,
  });
  const outputBytes = new Uint8Array(await outputBlob.arrayBuffer());
  // 後続の HTTP payload にそのまま載せられるよう data URL 形式へ戻す。
  const imageDataUrl = `${OUTPUT_IMAGE_TYPE};base64,${bytesToBase64(outputBytes)}`;
  const durationMs = performance.now() - startedAt;
  console.log(`Gem Read crop completed in ${durationMs.toFixed(1)}ms`);
  return {
    imageDataUrl: `data:${imageDataUrl}`,
    durationMs,
  };
}

function getOutputSize(
  sourceWidth: number,
  sourceHeight: number
): {
  outputWidth: number;
  outputHeight: number;
} {
  const longEdge = Math.max(sourceWidth, sourceHeight);
  // 短辺は比率維持で追従させ、selection の見た目を崩さない。
  const resizeRatio =
    longEdge > OUTPUT_MAX_LONG_EDGE ? OUTPUT_MAX_LONG_EDGE / longEdge : 1;
  return {
    outputWidth: Math.max(1, Math.round(sourceWidth * resizeRatio)),
    outputHeight: Math.max(1, Math.round(sourceHeight * resizeRatio)),
  };
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function clamp(value: number, minimum: number, maximum: number): number {
  // selection が viewport 外へ少しはみ出しても、crop 自体は安全に成立する範囲へ丸める。
  return Math.min(Math.max(value, minimum), maximum);
}
