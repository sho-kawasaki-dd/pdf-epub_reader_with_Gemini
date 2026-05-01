"""AI 応答 markdown から Plotly spec を抽出する pure service。

Phase 1 の責務は「fenced block を見つけて順序どおり保持する」までで、
JSON parse や Plotly 妥当性確認はここでは行わない。抽出規則を軽く保つ
ことで、LLM 応答の揺らぎを広めに受け止めつつ、描画失敗は後段で
構造化エラーとして扱えるようにしている。
"""

from __future__ import annotations

import re

from pdf_epub_reader.dto import PlotlySpec

_FENCED_BLOCK_PATTERN = re.compile(
    r"```(?P<lang>[^\n`]*)[ \t]*\r?\n(?P<body>.*?)(?:\r?\n```)",
    re.DOTALL,
)


def extract_plotly_specs(markdown_text: str) -> list[PlotlySpec]:
    """Markdown 応答から Plotly fenced block を順序通り抽出する。

    優先順位は Phase 1 の設計どおりで、明示的な `json` ブロックを優先し、
    言語タグ無しブロックは先頭が `{` の場合だけ JSON 候補として扱う。
    """
    specs: list[PlotlySpec] = []
    for match in _FENCED_BLOCK_PATTERN.finditer(markdown_text):
        language = match.group("lang").strip().lower()
        source_text = match.group("body").strip()
        plotly_language = _classify_plotly_block(language, source_text)
        if plotly_language is None:
            continue

        specs.append(
            PlotlySpec(
                index=len(specs),
                language=plotly_language,
                source_text=source_text,
                title=_infer_title(markdown_text[: match.start()]),
            )
        )

    return specs


def _classify_plotly_block(
    language: str,
    source_text: str,
) -> str | None:
    """fenced block を Plotly 対象として採用するか判定する。"""
    if language == "python":
        return "python"
    if language == "json":
        return "json"
    if language:
        # `bash` や `text` のように別言語が明示されていれば対象外とする。
        return None
    if source_text.startswith("{"):
        # Phase 1 のフォールバック規則: 言語タグ無しでも JSON 先頭なら採用する。
        return "json"
    return None


def _infer_title(prefix_text: str) -> str | None:
    """block 直前の見出しか plain text から表示タイトル候補を推測する。"""
    lines = prefix_text.splitlines()

    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("### "):
            return stripped[4:].strip() or None
        if stripped.startswith("## "):
            return stripped[3:].strip() or None

    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("```"):
            # 直前が別コードブロックなら、偶発的な行をタイトル扱いしない。
            return None
        return stripped

    return None