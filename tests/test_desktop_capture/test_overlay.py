from __future__ import annotations

from PySide6.QtCore import QPoint, QRect

from desktop_capture.capture.overlay import (
    ScreenScaleContext,
    logical_rect_to_physical,
    normalize_drag_rect,
)
from desktop_capture.contracts import CaptureRect


def test_normalize_drag_rect_handles_reverse_drag() -> None:
    result = normalize_drag_rect(QPoint(180, 90), QPoint(40, 10))

    assert result == QRect(40, 10, 140, 80)


def test_logical_rect_to_physical_uses_explicit_screen_origins() -> None:
    logical_rect = QRect(120, 80, 200, 40)
    scale_context = ScreenScaleContext(
        logical_left=100,
        logical_top=50,
        physical_left=160,
        physical_top=75,
        device_pixel_ratio=1.5,
    )

    result = logical_rect_to_physical(logical_rect, scale_context)

    assert result == CaptureRect(left=190, top=120, width=300, height=60)


def test_logical_rect_to_physical_supports_mixed_dpi_offset_monitors() -> None:
    logical_rect = QRect(-700, 120, 300, 100)
    scale_context = ScreenScaleContext(
        logical_left=-1280,
        logical_top=0,
        physical_left=-1920,
        physical_top=0,
        device_pixel_ratio=1.5,
    )

    result = logical_rect_to_physical(logical_rect, scale_context)

    assert result == CaptureRect(left=-1050, top=180, width=450, height=150)