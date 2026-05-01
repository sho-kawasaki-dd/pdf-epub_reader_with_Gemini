"""Plotly sandbox 用の共有ポリシーと例外定義。

Phase 2 では、LLM が返した Python コードを専用 venv + subprocess で
実行する。その際に必要になる allow-list / deny-list と、呼び出し側が
失敗理由を UI にマッピングしやすい例外型をここへ集約している。
"""

from __future__ import annotations

from pathlib import Path

# 専用 venv にインストールする外部パッケージ群。
ALLOWED_THIRDPARTY_PACKAGES: tuple[str, ...] = (
    "plotly",
    "kaleido",
    "numpy",
    "pandas",
    "scipy",
    "sympy",
)

# LLM コードからの import を許可する標準ライブラリ。
ALLOWED_STDLIB_MODULES: frozenset[str] = frozenset(
    {"math", "statistics", "datetime", "json"}
)

# AST 静的解析で拒否する危険な組み込み呼び出し。
DISALLOWED_BUILTIN_CALLS: frozenset[str] = frozenset(
    {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
)

# オブジェクト内部へ深く潜る足掛かりになりやすい dunder 属性。
DISALLOWED_DUNDER_ATTRS: frozenset[str] = frozenset(
    {
        "__class__",
        "__bases__",
        "__subclasses__",
        "__mro__",
        "__globals__",
        "__builtins__",
        "__import__",
        "__loader__",
        "__code__",
    }
)

# venv の互換性確認に使うマニフェスト名と schema バージョン。
SANDBOX_MANIFEST_NAME = "gem-read-sandbox.json"
SANDBOX_MANIFEST_SCHEMA_VERSION = 1


class SandboxProvisioningError(Exception):
    """専用 sandbox venv の作成・更新に失敗したことを表す。"""


class SandboxTimeoutError(Exception):
    """sandbox subprocess が制限時間を超過したことを表す。"""


class SandboxCancelledError(Exception):
    """呼び出し側からの cancel 要求で sandbox 実行を停止したことを表す。"""


class SandboxStaticCheckError(Exception):
    """runner の AST 静的解析でコードが拒否されたことを表す。"""

    def __init__(self, disallowed: list[str], stderr_log_path: Path) -> None:
        # UI が禁止名一覧をそのまま表示できるよう、加工前の情報を保持する。
        self.disallowed = disallowed
        self.stderr_log_path = stderr_log_path
        details = ", ".join(disallowed) if disallowed else "unknown policy violation"
        super().__init__(f"Sandbox static check failed: {details}")


class SandboxRuntimeError(Exception):
    """AST 違反以外の実行時エラーで runner が失敗したことを表す。"""

    def __init__(self, stderr_summary: str, stderr_log_path: Path) -> None:
        # status bar には要約だけを出し、全文はログ参照に回す設計。
        self.stderr_summary = stderr_summary
        self.stderr_log_path = stderr_log_path
        super().__init__(stderr_summary)


class SandboxOutputError(Exception):
    """runner の stdout から有効な Plotly JSON を抽出できなかったことを表す。"""


__all__ = [
    "ALLOWED_THIRDPARTY_PACKAGES",
    "ALLOWED_STDLIB_MODULES",
    "DISALLOWED_BUILTIN_CALLS",
    "DISALLOWED_DUNDER_ATTRS",
    "SANDBOX_MANIFEST_NAME",
    "SANDBOX_MANIFEST_SCHEMA_VERSION",
    "SandboxProvisioningError",
    "SandboxTimeoutError",
    "SandboxCancelledError",
    "SandboxStaticCheckError",
    "SandboxRuntimeError",
    "SandboxOutputError",
]