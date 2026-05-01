from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from pdf_epub_reader.services.plotly_sandbox import (
    SandboxCancelledError,
    SandboxOutputError,
    SandboxProvisioningError,
    SandboxRuntimeError,
    SandboxStaticCheckError,
    SandboxTimeoutError,
)
from pdf_epub_reader.services.plotly_sandbox.cancel import CancelToken
from pdf_epub_reader.services.plotly_sandbox.executor import SandboxExecutor


class _StubProvisioner:
    def __init__(
        self,
        python_path: Path | None = None,
        error: Exception | None = None,
    ) -> None:
        self.python_path = python_path or Path(sys.executable)
        self.error = error
        self.calls = 0

    def ensure(self, progress_cb=None) -> Path:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.python_path


@pytest.mark.slow
class TestSandboxExecutor:
    def test_run_returns_json_from_stdout(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(),
            log_dir=tmp_path / "logs",
        )

        result = executor.run(
            "import plotly.graph_objects as go\n"
            "fig = go.Figure()\n"
            "fig.add_scatter(x=[1, 2, 3], y=[1, 4, 9])\n"
            "print(fig.to_json())\n",
            timeout_s=5.0,
            cancel_token=CancelToken(),
        )

        assert '"data"' in result
        assert '"scatter"' in result

    def test_run_preserves_unicode_in_json_stdout(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(),
            log_dir=tmp_path / "logs",
        )

        result = executor.run(
            "import plotly.graph_objects as go\n"
            "fig = go.Figure()\n"
            "fig.add_scatter(x=[1, 2], y=[3, 4], name='指数関数的減衰 λ1')\n"
            "fig.update_layout(title='関数の時間発展')\n"
            "print(fig.to_json())\n",
            timeout_s=5.0,
            cancel_token=CancelToken(),
        )

        payload = json.loads(result)

        assert payload["data"][0]["name"] == "指数関数的減衰 λ1"
        assert payload["layout"]["title"]["text"] == "関数の時間発展"

    def test_run_uses_last_valid_json_line_when_stdout_contains_noise(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(),
            log_dir=tmp_path / "logs",
        )

        result = executor.run(
            "print('hello')\n"
            "import plotly.graph_objects as go\n"
            "fig = go.Figure()\n"
            "print(fig.to_json())\n",
            timeout_s=5.0,
            cancel_token=CancelToken(),
        )

        assert result.startswith("{")
        assert '"layout"' in result

    def test_run_raises_static_check_error_for_disallowed_import(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(),
            log_dir=tmp_path / "logs",
        )

        with pytest.raises(SandboxStaticCheckError) as exc_info:
            executor.run(
                "import os\n",
                timeout_s=5.0,
                cancel_token=CancelToken(),
            )

        assert exc_info.value.disallowed == ["os"]
        assert exc_info.value.stderr_log_path.exists() is True

    def test_run_raises_runtime_error_for_execution_failure(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(),
            log_dir=tmp_path / "logs",
        )

        with pytest.raises(SandboxRuntimeError) as exc_info:
            executor.run(
                "raise RuntimeError('boom')\n",
                timeout_s=5.0,
                cancel_token=CancelToken(),
            )

        assert "boom" in exc_info.value.stderr_summary
        assert exc_info.value.stderr_log_path.exists() is True

    def test_run_raises_output_error_when_stdout_has_no_json(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(),
            log_dir=tmp_path / "logs",
        )

        with pytest.raises(SandboxOutputError):
            executor.run(
                "print('hello')\n",
                timeout_s=5.0,
                cancel_token=CancelToken(),
            )

    def test_run_raises_timeout_error(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(),
            log_dir=tmp_path / "logs",
        )

        with pytest.raises(SandboxTimeoutError):
            executor.run(
                "while True:\n    pass\n",
                timeout_s=0.2,
                cancel_token=CancelToken(),
            )

    def test_run_raises_cancelled_error_when_cancel_token_is_set(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(),
            log_dir=tmp_path / "logs",
        )
        cancel_token = CancelToken()

        def trigger_cancel() -> None:
            time.sleep(0.1)
            cancel_token.set()

        thread = threading.Thread(target=trigger_cancel, daemon=True)
        thread.start()

        with pytest.raises(SandboxCancelledError):
            executor.run(
                "while True:\n    pass\n",
                timeout_s=5.0,
                cancel_token=cancel_token,
            )

        thread.join(timeout=1)

    def test_run_propagates_provisioning_error(self, tmp_path) -> None:
        executor = SandboxExecutor(
            provisioner=_StubProvisioner(
                error=SandboxProvisioningError("failed to provision")
            ),
            log_dir=tmp_path / "logs",
        )

        with pytest.raises(SandboxProvisioningError):
            executor.run(
                "print('noop')\n",
                timeout_s=5.0,
                cancel_token=CancelToken(),
            )