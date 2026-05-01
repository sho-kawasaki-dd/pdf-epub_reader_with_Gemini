"""Plotly sandbox 専用 venv を作成・検証するプロビジョナ。

この層は「隔離そのもの」ではなく、allow-list で許可した依存を安全に
供給するための専用環境を維持する責務を持つ。manifest を併用して、
schema や Python バージョンの不一致時には丸ごと再構築する。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import venv
from collections.abc import Callable
from pathlib import Path

import platformdirs

from pdf_epub_reader.services.plotly_sandbox import (
    ALLOWED_THIRDPARTY_PACKAGES,
    SANDBOX_MANIFEST_NAME,
    SANDBOX_MANIFEST_SCHEMA_VERSION,
    SandboxProvisioningError,
)

logger = logging.getLogger(__name__)


class SandboxVenvProvisioner:
    """sandboxed Plotly 実行に使う専用 venv を作成・保守する。"""

    def __init__(self, venv_dir: Path | None = None) -> None:
        if venv_dir is None:
            base_dir = Path(platformdirs.user_data_dir("gem-read", "gem-read"))
            venv_dir = base_dir / "sandbox-venv"
        self._venv_dir = venv_dir

    def ensure(
        self,
        progress_cb: Callable[[str], None] | None = None,
    ) -> Path:
        """sandbox Python 実行ファイルを返し、必要なら venv を再構築する。

        既存環境が使える場合はそのまま再利用し、manifest 不一致や import
        probe 失敗時だけ最小限の修復または再作成を行う。
        """
        python_path = self._python_path(self._venv_dir)

        if self._needs_rebuild(python_path):
            self._rebuild_environment(progress_cb)
        elif not self._probe_required_imports(python_path):
            # venv 自体は残っていても、依存だけ壊れているケースをここで補修する。
            self._notify(progress_cb, "Installing sandbox packages...")
            self._install_packages(python_path)
            self._write_manifest()

        if not self._probe_required_imports(python_path):
            raise SandboxProvisioningError(
                "Sandbox environment is missing required Plotly packages."
            )
        return python_path

    def _needs_rebuild(self, python_path: Path) -> bool:
        """manifest や実行ファイルの有無から再構築の必要性を判定する。"""
        if not self._venv_dir.exists():
            return True
        if not python_path.exists():
            return True
        return not self._has_compatible_manifest()

    def _rebuild_environment(
        self,
        progress_cb: Callable[[str], None] | None = None,
    ) -> None:
        """既存 venv を破棄して、クリーンな sandbox 環境を再作成する。"""
        self._notify(progress_cb, "Creating sandbox virtual environment...")
        try:
            if self._venv_dir.exists():
                shutil.rmtree(self._venv_dir)
            self._venv_dir.parent.mkdir(parents=True, exist_ok=True)
            venv.EnvBuilder(with_pip=True, clear=True).create(str(self._venv_dir))
        except Exception as exc:
            raise SandboxProvisioningError(
                f"Failed to create sandbox venv: {exc}"
            ) from exc

        python_path = self._python_path(self._venv_dir)
        self._notify(progress_cb, "Upgrading sandbox pip...")
        self._upgrade_pip(python_path)
        self._notify(progress_cb, "Installing sandbox packages...")
        self._install_packages(python_path)
        self._write_manifest()

    def _upgrade_pip(self, python_path: Path) -> None:
        """sandbox venv 内の pip を更新する。"""
        self._run_checked(
            [str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
            "Failed to upgrade sandbox pip.",
        )

    def _install_packages(self, python_path: Path) -> None:
        """allow-list に含まれる外部依存を一括インストールする。"""
        self._run_checked(
            [
                str(python_path),
                "-m",
                "pip",
                "install",
                *ALLOWED_THIRDPARTY_PACKAGES,
            ],
            "Failed to install sandbox dependencies.",
        )

    def _probe_required_imports(self, python_path: Path) -> bool:
        """必要依存が import 可能かを軽量な subprocess で確認する。"""
        command = [
            str(python_path),
            "-c",
            (
                "import importlib\n"
                f"mods = {list(ALLOWED_THIRDPARTY_PACKAGES)!r}\n"
                "for name in mods:\n"
                "    importlib.import_module(name)\n"
            ),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _run_checked(self, command: list[str], message: str) -> None:
        """失敗時に `SandboxProvisioningError` を送出する subprocess 実行ヘルパ。"""
        try:
            subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            if stderr:
                # 詳細はログへ残し、上位には抽象化した provisioning error を返す。
                logger.warning("%s stderr=%s", message, stderr)
            raise SandboxProvisioningError(message) from exc

    def _has_compatible_manifest(self) -> bool:
        """既存 manifest が現在の schema / Python / allow-list と一致するかを見る。"""
        manifest_path = self._venv_dir / SANDBOX_MANIFEST_NAME
        if not manifest_path.exists():
            return False

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError):
            return False

        return payload == self._build_manifest_payload()

    def _write_manifest(self) -> None:
        """現在の venv 構成を manifest として保存する。"""
        manifest_path = self._venv_dir / SANDBOX_MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(self._build_manifest_payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_manifest_payload(self) -> dict[str, object]:
        """互換性判定に使う manifest ペイロードを構築する。"""
        return {
            "schema_version": SANDBOX_MANIFEST_SCHEMA_VERSION,
            "python_version": ".".join(str(part) for part in sys.version_info[:3]),
            "allowed_packages": list(ALLOWED_THIRDPARTY_PACKAGES),
        }

    def _notify(
        self,
        progress_cb: Callable[[str], None] | None,
        message: str,
    ) -> None:
        """進捗通知コールバックがある場合だけメッセージを転送する。"""
        if progress_cb is not None:
            progress_cb(message)

    @staticmethod
    def _python_path(venv_dir: Path) -> Path:
        """OS ごとの差分を吸収して venv 内 Python のパスを返す。"""
        if sys.platform.startswith("win"):
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"