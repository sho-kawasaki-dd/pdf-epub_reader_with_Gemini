import type {
  SelectionCapturePayload,
  SelectionCaptureResponse,
  SelectionRect,
} from '../../shared/contracts/messages';

// Context menu 起動時には live Selection が消えていることがあるため、直近 snapshot を保持しておく。
let lastSelectionSnapshot: SelectionCapturePayload | null = null;

export interface CollectSelectionOptions {
  liveOnly?: boolean;
}

/**
 * ユーザー操作に追従して selection snapshot を更新し、遅延した background 処理でも同じ選択を再利用できるようにする。
 */
export function startSelectionTracking(): void {
  document.addEventListener('selectionchange', handleSelectionActivity);
  document.addEventListener('contextmenu', handleSelectionActivity);
  document.addEventListener('mouseup', handleSelectionActivity);
  document.addEventListener('keyup', handleSelectionActivity);
}

export function collectSelection(
  fallbackText?: string,
  options: CollectSelectionOptions = {}
): SelectionCaptureResponse {
  if (options.liveOnly) {
    const liveSnapshot = buildSelectionSnapshot();
    if (liveSnapshot) {
      lastSelectionSnapshot = liveSnapshot;
      return {
        ok: true,
        payload: liveSnapshot,
      };
    }

    return {
      ok: false,
      error: 'A live text selection is required. Select text on the page and try again.',
    };
  }

  const liveSnapshot = buildSelectionSnapshot(fallbackText);
  if (liveSnapshot) {
    lastSelectionSnapshot = liveSnapshot;
    return {
      ok: true,
      payload: liveSnapshot,
    };
  }

  if (lastSelectionSnapshot) {
    return {
      ok: true,
      payload: {
        ...lastSelectionSnapshot,
        // 文字列だけ最新の fallbackText が届くケースでは、座標を保ったまま text だけ差し替える。
        text:
          normalizeSelectionText(fallbackText) || lastSelectionSnapshot.text,
      },
    };
  }

  const normalizedFallback = normalizeSelectionText(fallbackText);
  if (normalizedFallback) {
    return {
      ok: false,
      error:
        '選択テキストの座標を保持できていません。選択し直してから再度実行してください。',
    };
  }

  return {
    ok: false,
    error: 'ページ上でテキストを選択してから実行してください。',
  };
}

function handleSelectionActivity(): void {
  const snapshot = buildSelectionSnapshot();
  if (snapshot) {
    lastSelectionSnapshot = snapshot;
  }
}

function buildSelectionSnapshot(
  fallbackText?: string
): SelectionCapturePayload | null {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    return null;
  }

  const text =
    normalizeSelectionText(selection.toString()) ||
    normalizeSelectionText(fallbackText);
  if (!text) {
    return null;
  }

  const range = selection.getRangeAt(0);
  const rect = getUnionRect(range);
  if (!rect) {
    return null;
  }

  return {
    text,
    rect,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio || 1,
    url: window.location.href,
    pageTitle: document.title,
  };
}

function normalizeSelectionText(text: string | undefined): string {
  return (text ?? '').replace(/\s+/g, ' ').trim();
}

function getUnionRect(range: Range): SelectionRect | null {
  const clientRects = Array.from(range.getClientRects()).filter(
    (rect) => rect.width > 0 && rect.height > 0
  );
  const baseRect = range.getBoundingClientRect();
  // 複数行 selection は複数 rect に分割されるため、crop 用には外接矩形へ畳み込む。
  const rects = clientRects.length > 0 ? clientRects : [baseRect];
  const validRects = rects.filter((rect) => rect.width > 0 && rect.height > 0);
  if (validRects.length === 0) {
    return null;
  }

  let left = validRects[0].left;
  let top = validRects[0].top;
  let right = validRects[0].right;
  let bottom = validRects[0].bottom;

  for (const rect of validRects.slice(1)) {
    left = Math.min(left, rect.left);
    top = Math.min(top, rect.top);
    right = Math.max(right, rect.right);
    bottom = Math.max(bottom, rect.bottom);
  }

  return {
    left,
    top,
    width: right - left,
    height: bottom - top,
  };
}
