from __future__ import annotations

from io import BytesIO

from PIL import Image

from desktop_capture.capture.screenshot import MssCaptureGateway
from desktop_capture.contracts import CaptureRect


class FakeShot:
    def __init__(self) -> None:
        self.width = 2
        self.height = 1
        self.bgra = bytes([
            0,
            0,
            255,
            0,
            0,
            255,
            0,
            0,
        ])


class FakeMssBackend:
    def __init__(self) -> None:
        self.grab_calls = []

    def __enter__(self) -> FakeMssBackend:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def grab(self, monitor):
        self.grab_calls.append(monitor)
        return FakeShot()


def test_mss_capture_gateway_passes_monitor_rect_and_encodes_jpeg() -> None:
    backend = FakeMssBackend()
    gateway = MssCaptureGateway(backend_factory=lambda: backend, jpeg_quality=80)

    result = gateway._capture_sync(CaptureRect(left=10, top=20, width=2, height=1))

    assert backend.grab_calls == [{"left": 10, "top": 20, "width": 2, "height": 1}]
    assert result.width == 2
    assert result.height == 1
    decoded = Image.open(BytesIO(result.image_bytes))
    assert decoded.size == (2, 1)