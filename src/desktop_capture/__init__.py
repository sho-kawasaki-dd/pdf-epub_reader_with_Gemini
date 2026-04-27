"""Desktop capture companion app bootstrap package."""

from __future__ import annotations


def main() -> None:
	from desktop_capture.app import main as run_desktop_capture_app

	run_desktop_capture_app()


__all__ = ["main"]