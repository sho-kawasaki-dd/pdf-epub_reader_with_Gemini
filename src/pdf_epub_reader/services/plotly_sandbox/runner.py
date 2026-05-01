"""sandbox subprocess 内で LLM 生成コードを実行する軽量 runner。

このファイルは `python -I -S runner.py --code-path ...` で起動される前提で、
標準ライブラリだけで完結するように作られている。役割は次の 3 点。

1. AST 静的解析で allow-list 違反を早期に拒否する。
2. `__import__` フックで実行時 import を追加で制限する。
3. LLM コードの stdout をそのまま流し、終了コードで成否を伝える。
"""

from __future__ import annotations

import argparse
import ast
import builtins
import importlib.util
import json
import site
import sys
import traceback
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import CodeType
from typing import Any


@dataclass(frozen=True)
class StaticViolation:
    """AST 走査で見つかった単一のポリシー違反。"""

    node_type: str
    name: str
    lineno: int


@lru_cache(maxsize=1)
def _load_policy() -> dict[str, Any]:
    """同ディレクトリの `__init__.py` からポリシー定数を動的に読み込む。"""
    init_path = Path(__file__).with_name("__init__.py")
    spec = importlib.util.spec_from_file_location("plotly_sandbox_policy", init_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load sandbox policy constants.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        "allowed_thirdparty": tuple(module.ALLOWED_THIRDPARTY_PACKAGES),
        "allowed_stdlib": frozenset(module.ALLOWED_STDLIB_MODULES),
        "disallowed_builtin_calls": frozenset(module.DISALLOWED_BUILTIN_CALLS),
        "disallowed_dunder_attrs": frozenset(module.DISALLOWED_DUNDER_ATTRS),
    }


def _top_level_name(name: str | None) -> str:
    """`plotly.graph_objects` のような名前からトップレベル名だけを返す。"""
    if not name:
        return ""
    return name.split(".", 1)[0]


def collect_static_violations(tree: ast.AST) -> list[StaticViolation]:
    """LLM コードの AST 全体から allow-list / deny-list 違反を収集する。

    ここでは違反を見つけた時点で中断せず、UI が一覧表示できるように
    可能な限り全件を集める。
    """
    policy = _load_policy()
    allowed_roots = set(policy["allowed_thirdparty"]) | set(policy["allowed_stdlib"])
    violations: list[StaticViolation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _top_level_name(alias.name)
                if root not in allowed_roots:
                    # `import os` のような禁止 import を拾う。
                    violations.append(
                        StaticViolation("Import", root or alias.name, node.lineno)
                    )
        elif isinstance(node, ast.ImportFrom):
            root = _top_level_name(node.module)
            if node.level != 0 or root not in allowed_roots:
                # 相対 import と allow-list 外 from-import を禁止する。
                violations.append(
                    StaticViolation("ImportFrom", root or ".", node.lineno)
                )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in policy["disallowed_builtin_calls"]:
                # eval / exec などの危険な builtins 呼び出しを拒否する。
                violations.append(
                    StaticViolation("Call", node.func.id, node.lineno)
                )
        elif isinstance(node, ast.Attribute):
            if node.attr in policy["disallowed_dunder_attrs"]:
                # 内部オブジェクト探索に繋がる dunder 属性アクセスを拒否する。
                violations.append(
                    StaticViolation("Attribute", node.attr, node.lineno)
                )

    return violations


def emit_static_violations(violations: list[StaticViolation]) -> None:
    """静的解析違反を JSON Lines 形式で stderr へ書き出す。"""
    for violation in violations:
        sys.stderr.write(
            json.dumps(
                {
                    "node_type": violation.node_type,
                    "name": violation.name,
                    "lineno": violation.lineno,
                },
                ensure_ascii=False,
            )
        )
        sys.stderr.write("\n")


def _requester_filename() -> str | None:
    """現在の import 呼び出し元が LLM コードかどうかを推定する。"""
    runner_path = str(Path(__file__).resolve()).replace("\\", "/")
    frame = sys._getframe(2)
    while frame is not None:
        filename = frame.f_code.co_filename
        normalized = filename.replace("\\", "/")
        if normalized == runner_path:
            # runner 自身のフレームは判定材料に含めない。
            frame = frame.f_back
            continue
        if filename == "<llm>":
            return filename
        if filename.startswith("<frozen importlib"):
            frame = frame.f_back
            continue
        if "importlib" in normalized:
            frame = frame.f_back
            continue
        return filename
    return None


def _build_sandbox_builtins() -> dict[str, Any]:
    """allow-list を強制する `__import__` フック付き builtins を構築する。"""
    policy = _load_policy()
    allowed_roots = set(policy["allowed_thirdparty"]) | set(policy["allowed_stdlib"])
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] | list[str] = (),
        level: int = 0,
    ) -> Any:
        requester = _requester_filename()
        root = _top_level_name(name)
        if requester == "<llm>" and (level != 0 or root not in allowed_roots):
            # AST をすり抜けた動的 import もここで止める。
            raise ImportError(f"import '{root or name}' is not allowed in sandbox")
        return original_import(name, globals, locals, fromlist, level)

    sandbox_builtins = builtins.__dict__.copy()
    # `exec` に渡す builtins を差し替え、LLM コードからの import を拘束する。
    sandbox_builtins["__import__"] = guarded_import
    return sandbox_builtins


def _enable_site_packages() -> None:
    """`-I -S` 起動で無効化された venv の site-packages を再有効化する。"""
    site.main()


def _configure_stdio() -> None:
    """stdout / stderr を UTF-8 に固定して親側の decode 前提と揃える。"""
    stdout = getattr(sys, "stdout", None)
    stderr = getattr(sys, "stderr", None)

    if stdout is not None and hasattr(stdout, "reconfigure"):
        stdout.reconfigure(encoding="utf-8", errors="strict")
    if stderr is not None and hasattr(stderr, "reconfigure"):
        stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


def execute_code(
    code: str,
    *,
    enforce_static_checks: bool = True,
) -> int:
    """LLM コードを実行し、runner の終了コードを返す。

    `0` は成功、`2` は実行時失敗、`3` は静的解析違反を表す。
    テストでは `enforce_static_checks=False` を使って第二線の import フックを
    単独検証できるようにしている。
    """
    try:
        tree = ast.parse(code, filename="<llm>")
    except SyntaxError:
        traceback.print_exc(file=sys.stderr)
        return 2

    if enforce_static_checks:
        violations = collect_static_violations(tree)
        if violations:
            emit_static_violations(violations)
            return 3

    try:
        # venv の site-packages を有効化したあとでコンパイル済みコードを実行する。
        _enable_site_packages()
        compiled = compile(tree if enforce_static_checks else code, "<llm>", "exec")
        if isinstance(compiled, CodeType):
            code_object = compiled
        else:
            code_object = compile(code, "<llm>", "exec")
        sandbox_globals = {
            "__name__": "__main__",
            "__builtins__": _build_sandbox_builtins(),
        }
        # stdout は LLM コードの `print(fig.to_json())` をそのまま流す。
        exec(code_object, sandbox_globals)
        return 0
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を解釈し、コードファイルのパスを取得する。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-path", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """runner のエントリーポイント。"""
    _configure_stdio()
    args = _parse_args(argv)
    code = Path(args.code_path).read_text(encoding="utf-8")
    return execute_code(code)


if __name__ == "__main__":
    raise SystemExit(main())