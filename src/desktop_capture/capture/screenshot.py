"""mss-backed screenshot capture gateway for desktop_capture Phase 1."""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any, Callable

from PIL import Image
import mss

from pdf_epub_reader.utils.config import DEFAULT_JPEG_QUALITY

from desktop_capture.contracts import CapturedImage, CaptureRect, ScreenCaptureGateway


class MssCaptureGateway(ScreenCaptureGateway):
    """Capture physical-pixel rectangles and encode them as JPEG bytes."""

    def __init__(
        self,
        *,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        backend_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._jpeg_quality = jpeg_quality
        self._backend_factory = backend_factory or mss.mss

    async def capture(self, rect: CaptureRect) -> CapturedImage:
        return await asyncio.to_thread(self._capture_sync, rect)

    def _capture_sync(self, rect: CaptureRect) -> CapturedImage:
        monitor = {
            "left": rect.left,
            "top": rect.top,
            "width": rect.width,
            "height": rect.height,
        }
        with self._backend_factory() as backend:
            shot = backend.grab(monitor)

        image = _image_from_grab(shot)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=self._jpeg_quality)
        return CapturedImage(
            image_bytes=buffer.getvalue(),
            width=image.width,
            height=image.height,
        )


def _image_from_grab(shot: Any) -> Image.Image:
    width = int(shot.width)
    height = int(shot.height)
    if width <= 0 or height <= 0:
        raise ValueError("Captured image has invalid dimensions.")

    if hasattr(shot, "rgb"):
        return Image.frombytes("RGB", (width, height), shot.rgb)

    if hasattr(shot, "bgra"):
        return Image.frombytes("RGB", (width, height), shot.bgra, "raw", "BGRX")

    raise TypeError("Unsupported mss grab result: missing rgb/bgra buffer")