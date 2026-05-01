"""専用 subprocess 上で Plotly Python スクリプトを実行する service。

runner 自身は stdout をそのまま流すだけなので、この層が
`print(fig.to_json())` の出力を回収し、終了コードに応じて
構造化例外へ変換する責務を持つ。
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import platformdirs

from pdf_epub_reader.services.plotly_sandbox import (
    SandboxCancelledError,
    SandboxOutputError,
    SandboxRuntimeError,
    SandboxStaticCheckError,
    SandboxTimeoutError,
)
from pdf_epub_reader.services.plotly_sandbox.cancel import CancelToken
from pdf_epub_reader.services.plotly_sandbox.venv_provisioner import (
    SandboxVenvProvisioner,
)

logger = logging.getLogger(__name__)


class SandboxExecutor:
    """隔離 subprocess で Python Plotly コードを実行し JSON を返す。

    実行前の venv 準備、タイムアウト、キャンセル監視、stderr ログ保存、
    stdout 末尾からの JSON 抽出までを一箇所にまとめている。
    """

    def __init__(
        self,
        provisioner: SandboxVenvProvisioner | None = None,
        *,
        log_dir: Path | None = None,
        runner_path: Path | None = None,
    ) -> None:
        # 実行時ログの保存先と runner スクリプトの位置は差し替え可能にして、
        # テストと本番の両方で扱いやすくしている。
        self._provisioner = provisioner or SandboxVenvProvisioner()
        self._runner_path = runner_path or Path(__file__).with_name("runner.py")
        self._log_dir = log_dir or Path(
            platformdirs.user_log_dir("gem-read", "gem-read")
        )

    def run(
        self,
        code: str,
        *,
        timeout_s: float,
        cancel_token: CancelToken,
    ) -> str:
        """sandbox でコードを実行し、stdout から Plotly JSON を返す。

        Args:
            code: LLM が返した Python スクリプト全文。
            timeout_s: subprocess 全体に適用する秒単位の上限時間。
            cancel_token: UI からの Cancel を監視するためのトークン。

        Returns:
            Plotly `Figure.to_json()` 相当の JSON 文字列。

        Raises:
            SandboxTimeoutError: 実行が制限時間を超えた場合。
            SandboxCancelledError: 呼び出し側がキャンセルした場合。
            SandboxStaticCheckError: runner の AST 検査で拒否された場合。
            SandboxRuntimeError: runner 内で例外が発生した場合。
            SandboxOutputError: stdout に有効な JSON が無かった場合。
        """
        python_path = self._provisioner.ensure()

        with TemporaryDirectory(prefix="gem_read_plotly_sandbox_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            code_path = temp_dir / "sandbox_code.py"
            code_path.write_text(code, encoding="utf-8")

            # `-I -S` と空 env により、ホスト環境からの影響を最小化して起動する。
            process = subprocess.Popen(
                [
                    str(python_path),
                    "-I",
                    "-S",
                    str(self._runner_path),
                    "--code-path",
                    str(code_path),
                ],
                cwd=temp_dir,
                env={},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            stop_monitor = threading.Event()
            cancelled_by_user = threading.Event()
            # `communicate()` は blocking なので、Cancel は別スレッドで監視する。
            monitor = threading.Thread(
                target=self._monitor_cancellation,
                args=(process, cancel_token, cancelled_by_user, stop_monitor),
                daemon=True,
            )
            monitor.start()

            try:
                stdout, stderr = process.communicate(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                # timeout 時は穏当な terminate を試し、必要なら kill へ段階的に移る。
                stdout, stderr = self._terminate_process(process)
                raise SandboxTimeoutError(
                    f"Sandbox execution timed out after {timeout_s:.2f} seconds."
                )
            finally:
                stop_monitor.set()
                monitor.join(timeout=1)

        if cancelled_by_user.is_set():
            raise SandboxCancelledError("Sandbox execution cancelled.")

        if process.returncode == 0:
            # runner は stdout を素通しするので、最後の有効 JSON 行を採用する。
            return self._extract_json_output(stdout)

        stderr_log_path = self._write_stderr_log(stderr)
        if process.returncode == 3:
            # exit code 3 は AST 静的解析専用。禁止名一覧を UI に返す。
            raise SandboxStaticCheckError(
                self._parse_disallowed_names(stderr),
                stderr_log_path,
            )

        # それ以外は runtime error として要約だけを表に出す。
        raise SandboxRuntimeError(
            self._summarize_stderr(stderr),
            stderr_log_path,
        )

    @staticmethod
    def _monitor_cancellation(
        process: subprocess.Popen[str],
        cancel_token: CancelToken,
        cancelled_by_user: threading.Event,
        stop_monitor: threading.Event,
    ) -> None:
        """CancelToken を監視し、要求が来たら subprocess を停止する。"""
        while not stop_monitor.is_set():
            if not cancel_token.wait(0.05):
                continue
            cancelled_by_user.set()
            if process.poll() is None:
                process.terminate()
            return

    @staticmethod
    def _terminate_process(
        process: subprocess.Popen[str],
    ) -> tuple[str, str]:
        """subprocess を停止し、回収できた stdout / stderr を返す。"""
        if process.poll() is None:
            process.terminate()
            try:
                return process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                # terminate で止まらないケースに備えて最後は kill する。
                process.kill()
        return process.communicate()

    @staticmethod
    def _extract_json_output(stdout: str) -> str:
        """stdout 全文または末尾行から有効な JSON を抽出する。"""
        stripped = stdout.strip()
        if stripped:
            try:
                json.loads(stripped)
                return stripped
            except json.JSONDecodeError:
                pass

        for line in reversed(stdout.splitlines()):
            candidate = line.strip()
            if not candidate:
                continue
            try:
                # 中間 print が混ざっていても、最後の JSON 行だけ拾えればよい。
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

        raise SandboxOutputError(
            "Sandbox stdout did not contain a valid Plotly JSON payload."
        )

    @staticmethod
    def _parse_disallowed_names(stderr: str) -> list[str]:
        """runner が stderr に出した JSON Lines から禁止名一覧を復元する。"""
        names: list[str] = []
        for line in stderr.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = payload.get("name")
            if isinstance(name, str) and name not in names:
                names.append(name)
        return names

    @staticmethod
    def _summarize_stderr(stderr: str) -> str:
        """stderr の末尾から、人に見せる短い要約を組み立てる。"""
        for line in reversed(stderr.splitlines()):
            summary = line.strip()
            if summary:
                return summary
        return "Sandbox execution failed without stderr output."

    def _write_stderr_log(self, stderr: str) -> Path:
        """stderr 全文をログファイルへ退避し、そのパスを返す。"""
        self._log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        log_path = self._log_dir / f"plotly-sandbox-{timestamp}.log"
        log_path.write_text(stderr, encoding="utf-8")
        logger.warning("Sandbox stderr written to %s", log_path)
        return log_path