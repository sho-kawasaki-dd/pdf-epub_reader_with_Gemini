"""Transparent full-screen overlay and geometry helpers for screen selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from desktop_capture.contracts import CaptureRect


@dataclass(frozen=True)
class ScreenScaleContext:
    """Mapping data from Qt logical coordinates to physical capture coordinates."""

    logical_left: int
    logical_top: int
    physical_left: int
    physical_top: int
    device_pixel_ratio: float


def normalize_drag_rect(start: QPoint, end: QPoint) -> QRect:
    """Return a top-left anchored logical rectangle regardless of drag direction."""
    left = min(start.x(), end.x())
    top = min(start.y(), end.y())
    right = max(start.x(), end.x())
    bottom = max(start.y(), end.y())
    return QRect(left, top, right - left, bottom - top)


def logical_rect_to_physical(
    logical_rect: QRect,
    scale_context: ScreenScaleContext,
) -> CaptureRect:
    """Convert a logical Qt rect into a physical-pixel capture rect."""
    local_left = logical_rect.left() - scale_context.logical_left
    local_top = logical_rect.top() - scale_context.logical_top

    return CaptureRect(
        left=scale_context.physical_left + round(local_left * scale_context.device_pixel_ratio),
        top=scale_context.physical_top + round(local_top * scale_context.device_pixel_ratio),
        width=round(logical_rect.width() * scale_context.device_pixel_ratio),
        height=round(logical_rect.height() * scale_context.device_pixel_ratio),
    )


class SelectionOverlay(QWidget):
    """A temporary transparent overlay used to collect a drag-selection rectangle."""

    selection_submitted = Signal(object)
    selection_cancelled = Signal()

    def __init__(
        self,
        scale_context_resolver: Callable[[object], ScreenScaleContext],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scale_context_resolver = scale_context_resolver
        self._drag_start: QPoint | None = None
        self._drag_current: QPoint | None = None
        self._active_screen = None
        self._active_screen_geometry: QRect | None = None
        self._selection_rect = QRect()

        self.setWindowTitle("Desktop Capture Selection")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        self._set_virtual_geometry()

    def show_and_focus(self) -> None:
        """Show the overlay and take focus for keyboard cancellation."""
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        self.setFocus(Qt.ActiveWindowFocusReason)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        global_pos = event.globalPosition().toPoint()
        self._active_screen = QGuiApplication.screenAt(global_pos)
        if self._active_screen is None:
            self.selection_cancelled.emit()
            self.close()
            return

        self._active_screen_geometry = self._active_screen.geometry()
        self._drag_start = global_pos
        self._drag_current = global_pos
        self._selection_rect = QRect(global_pos, global_pos)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is None or self._active_screen_geometry is None:
            event.ignore()
            return

        next_point = self._clamp_to_screen(
            event.globalPosition().toPoint(),
            self._active_screen_geometry,
        )
        self._drag_current = next_point
        self._selection_rect = normalize_drag_rect(self._drag_start, next_point)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton or self._drag_start is None:
            event.ignore()
            return

        event.accept()
        if self._active_screen is None or self._active_screen_geometry is None:
            self.selection_cancelled.emit()
            self.close()
            return

        end_point = self._clamp_to_screen(
            event.globalPosition().toPoint(),
            self._active_screen_geometry,
        )
        logical_rect = normalize_drag_rect(self._drag_start, end_point)
        if logical_rect.width() < 4 or logical_rect.height() < 4:
            self.selection_cancelled.emit()
            self.close()
            return

        scale_context = self._scale_context_resolver(self._active_screen)
        self.selection_submitted.emit(logical_rect_to_physical(logical_rect, scale_context))
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.selection_cancelled.emit()
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(15, 23, 42, 48))

        if self._selection_rect.isNull():
            return

        translated_rect = QRect(
            self._selection_rect.left() - self.geometry().left(),
            self._selection_rect.top() - self.geometry().top(),
            self._selection_rect.width(),
            self._selection_rect.height(),
        )
        painter.fillRect(translated_rect, QColor(234, 88, 12, 48))
        painter.setPen(QPen(QColor(234, 88, 12), 2))
        painter.drawRect(translated_rect)

    def _set_virtual_geometry(self) -> None:
        virtual_geometry = QRect()
        for screen in QApplication.screens():
            virtual_geometry = virtual_geometry.united(screen.geometry())
        self.setGeometry(virtual_geometry)

    @staticmethod
    def _clamp_to_screen(point: QPoint, screen_geometry: QRect) -> QPoint:
        return QPoint(
            max(screen_geometry.left(), min(point.x(), screen_geometry.right())),
            max(screen_geometry.top(), min(point.y(), screen_geometry.bottom())),
        )