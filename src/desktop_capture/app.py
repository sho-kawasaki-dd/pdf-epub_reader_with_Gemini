"""Desktop capture application runtime wiring for Phase 1."""

from __future__ import annotations

import asyncio
import ctypes
import logging

import dotenv
from PySide6.QtWidgets import QStyle, QWidget

from pdf_epub_reader.infrastructure.event_loop import run_app

from desktop_capture.adapters.ai_gateway import DesktopCaptureGeminiGateway
from desktop_capture.capture.hotkey import GlobalHotkeyManager
from desktop_capture.capture.overlay import ScreenScaleContext, SelectionOverlay
from desktop_capture.capture.screenshot import MssCaptureGateway
from desktop_capture.capture.trigger_panel import CaptureTriggerPanel
from desktop_capture.config import DesktopCaptureConfig, load_config
from desktop_capture.contracts import CaptureRect
from desktop_capture.presenter import DesktopCapturePresenter
from desktop_capture.result_window import DesktopCaptureResultWindow

logger = logging.getLogger(__name__)

_runtime: _DesktopCaptureRuntime | None = None


class _DesktopCaptureRuntime:
    def __init__(self, config: DesktopCaptureConfig) -> None:
        self._config = config
        self._result_window = DesktopCaptureResultWindow()
        self._trigger_panel = CaptureTriggerPanel()
        self._capture_gateway = MssCaptureGateway()
        self._ai_gateway = DesktopCaptureGeminiGateway.from_config(config)
        self._presenter = DesktopCapturePresenter(
            view=self._result_window,
            capture_gateway=self._capture_gateway,
            ai_gateway=self._ai_gateway,
            config=config,
        )
        self._hotkey_manager = GlobalHotkeyManager(self.start_capture_flow)
        self._active_overlay: SelectionOverlay | None = None
        self._selection_active = False

    def start(self) -> None:
        self._trigger_panel.set_on_capture_requested(self.start_capture_flow)
        self._trigger_panel.setWindowIcon(self._trigger_panel.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))

        registration = self._hotkey_manager.register(self._config.hotkey)
        self._trigger_panel.set_hotkey_status(registration.message)
        self._trigger_panel.show()
        self._result_window.show_status(self._presenter.state, "Ready to capture.")

    async def shutdown(self) -> None:
        self._hotkey_manager.unregister()
        if self._active_overlay is not None:
            self._active_overlay.close()
            self._active_overlay = None

    def start_capture_flow(self) -> None:
        if self._selection_active:
            self._trigger_panel.set_status_text("Selection is already active.")
            return

        self._selection_active = True
        self._trigger_panel.cancel_countdown()
        self._trigger_panel.set_status_text("Selection overlay opened.")
        self._presenter.request_capture()

        overlay = SelectionOverlay(self._resolve_scale_context)
        overlay.selection_cancelled.connect(self._handle_selection_cancelled)
        overlay.selection_submitted.connect(self._handle_selection_submitted)
        overlay.destroyed.connect(self._handle_overlay_destroyed)
        self._active_overlay = overlay
        overlay.show_and_focus()

    def _handle_selection_cancelled(self) -> None:
        self._selection_active = False
        self._active_overlay = None
        self._presenter.cancel_capture()
        self._trigger_panel.set_status_text("Capture cancelled.")

    def _handle_selection_submitted(self, rect: object) -> None:
        if not isinstance(rect, CaptureRect):
            self._handle_selection_cancelled()
            return
        self._selection_active = False
        self._active_overlay = None
        asyncio.create_task(self._run_capture(rect))

    def _handle_overlay_destroyed(self) -> None:
        self._active_overlay = None

    async def _run_capture(self, rect: CaptureRect) -> None:
        self._trigger_panel.set_busy(True)
        try:
            result = await self._presenter.submit_selection(rect)
            if result is None:
                self._trigger_panel.set_status_text(
                    self._presenter.last_error or "Capture failed."
                )
            else:
                self._trigger_panel.set_status_text("Capture complete.")
        finally:
            self._trigger_panel.set_busy(False)

    @staticmethod
    def _resolve_scale_context(screen) -> ScreenScaleContext:
        geometry = screen.geometry()
        device_pixel_ratio = float(screen.devicePixelRatio() or 1.0)
        return ScreenScaleContext(
            logical_left=geometry.left(),
            logical_top=geometry.top(),
            physical_left=round(geometry.left() * device_pixel_ratio),
            physical_top=round(geometry.top() * device_pixel_ratio),
            device_pixel_ratio=device_pixel_ratio,
        )


def main() -> None:
    """Start the desktop capture application."""
    dotenv.load_dotenv()
    _enable_dpi_awareness()
    run_app(_app_main, on_shutdown=_shutdown)


def _enable_dpi_awareness() -> None:
    """Opt into per-monitor DPI awareness before QApplication is created."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except AttributeError:
        logger.debug("SetProcessDpiAwareness is not available on this platform")
    except OSError as exc:
        logger.debug("Failed to enable per-monitor DPI awareness: %s", exc)


async def _app_main() -> None:
    """Load config and start the desktop capture runtime."""
    global _runtime  # noqa: PLW0603

    config = load_config()
    _runtime = _DesktopCaptureRuntime(config)
    _runtime.start()


async def _shutdown() -> None:
    if _runtime is not None:
        await _runtime.shutdown()