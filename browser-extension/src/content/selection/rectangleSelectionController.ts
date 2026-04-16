import type {
  RectangleSelectionTriggerSource,
  SelectionCaptureResponse,
  SelectionRect,
} from '../../shared/contracts/messages';

const RECTANGLE_OVERLAY_ID = 'gem-read-phase2-rectangle-overlay';

let rectangleSelectionActive = false;

export function isRectangleSelectionActive(): boolean {
  return rectangleSelectionActive;
}

export async function startRectangleSelection(
  triggerSource: RectangleSelectionTriggerSource
): Promise<SelectionCaptureResponse> {
  if (rectangleSelectionActive) {
    return {
      ok: false,
      error: 'Rectangle selection is already active.',
    };
  }

  rectangleSelectionActive = true;
  const previousUserSelect = document.body.style.userSelect;

  return new Promise((resolve) => {
    const host = document.createElement('div');
    host.id = RECTANGLE_OVERLAY_ID;
    host.style.position = 'fixed';
    host.style.inset = '0';
    host.style.zIndex = '2147483646';
    host.style.cursor = 'crosshair';
    host.style.background = 'rgba(15, 23, 42, 0.12)';
    host.style.userSelect = 'none';

    const instruction = document.createElement('div');
    instruction.textContent =
      triggerSource === 'overlay'
        ? 'Drag to capture an image region. Press Esc to cancel.'
        : 'Gem Read rectangle mode: drag to capture a region. Press Esc to cancel.';
    instruction.style.position = 'fixed';
    instruction.style.top = '16px';
    instruction.style.left = '16px';
    instruction.style.padding = '10px 12px';
    instruction.style.borderRadius = '999px';
    instruction.style.background = 'rgba(15, 23, 42, 0.92)';
    instruction.style.color = '#f8fafc';
    instruction.style.font = "13px/1.4 'Segoe UI', 'Yu Gothic UI', sans-serif";
    instruction.style.boxShadow = '0 12px 32px rgba(15, 23, 42, 0.28)';

    const rectangle = document.createElement('div');
    rectangle.style.position = 'fixed';
    rectangle.style.border = '2px solid rgba(234, 88, 12, 0.95)';
    rectangle.style.background = 'rgba(234, 88, 12, 0.18)';
    rectangle.style.display = 'none';

    host.append(instruction, rectangle);
    document.documentElement.appendChild(host);
    document.body.style.userSelect = 'none';

    let startPoint: { x: number; y: number } | null = null;

    const cleanup = (): void => {
      host.remove();
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener('mousemove', handleMouseMove, true);
      window.removeEventListener('mouseup', handleMouseUp, true);
      window.removeEventListener('keydown', handleKeyDown, true);
      rectangleSelectionActive = false;
    };

    const finish = (response: SelectionCaptureResponse): void => {
      cleanup();
      resolve(response);
    };

    const handleMouseMove = (event: MouseEvent): void => {
      if (!startPoint) {
        return;
      }

      const nextRect = normalizeRectangle(
        startPoint.x,
        startPoint.y,
        event.clientX,
        event.clientY
      );
      rectangle.style.display = 'block';
      rectangle.style.left = `${nextRect.left}px`;
      rectangle.style.top = `${nextRect.top}px`;
      rectangle.style.width = `${nextRect.width}px`;
      rectangle.style.height = `${nextRect.height}px`;
      event.preventDefault();
      event.stopPropagation();
    };

    const handleMouseUp = (event: MouseEvent): void => {
      if (!startPoint) {
        return;
      }

      const nextRect = normalizeRectangle(
        startPoint.x,
        startPoint.y,
        event.clientX,
        event.clientY
      );
      startPoint = null;

      if (nextRect.width < 4 || nextRect.height < 4) {
        finish({
          ok: false,
          error: 'Rectangle selection was too small. Drag a larger region.',
        });
        return;
      }

      finish({
        ok: true,
        payload: {
          text: '',
          rect: nextRect,
          viewportWidth: window.innerWidth,
          viewportHeight: window.innerHeight,
          devicePixelRatio: window.devicePixelRatio || 1,
          url: window.location.href,
          pageTitle: document.title,
        },
      });
    };

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') {
        return;
      }

      event.preventDefault();
      finish({
        ok: false,
        error: 'Rectangle selection was cancelled.',
      });
    };

    host.addEventListener(
      'mousedown',
      (event) => {
        if (event.button !== 0) {
          return;
        }

        startPoint = {
          x: event.clientX,
          y: event.clientY,
        };
        rectangle.style.display = 'block';
        rectangle.style.left = `${event.clientX}px`;
        rectangle.style.top = `${event.clientY}px`;
        rectangle.style.width = '0px';
        rectangle.style.height = '0px';
        event.preventDefault();
        event.stopPropagation();
      },
      true
    );

    window.addEventListener('mousemove', handleMouseMove, true);
    window.addEventListener('mouseup', handleMouseUp, true);
    window.addEventListener('keydown', handleKeyDown, true);
  });
}

function normalizeRectangle(
  startX: number,
  startY: number,
  endX: number,
  endY: number
): SelectionRect {
  const left = Math.min(startX, endX);
  const top = Math.min(startY, endY);
  const right = Math.max(startX, endX);
  const bottom = Math.max(startY, endY);

  return {
    left,
    top,
    width: right - left,
    height: bottom - top,
  };
}