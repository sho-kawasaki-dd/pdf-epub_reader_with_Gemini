"""AI 応答 markdown から Plotly spec を抽出する pure service。"""

from __future__ import annotations

import re

from pdf_epub_reader.dto import PlotlySpec

_FENCED_BLOCK_PATTERN = re.compile(
    r"```(?P<lang>[^\n`]*)[ \t]*\r?\n(?P<body>.*?)(?:\r?\n```)",
    re.DOTALL,
)


def extract_plotly_specs(markdown_text: str) -> list[PlotlySpec]:
    """Markdown 応答から Plotly fenced block を順序通り抽出する。"""
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
    if language == "python":
        return "python"
    if language == "json":
        return "json"
    if language:
        return None
    if source_text.startswith("{"):
        return "json"
    return None


def _infer_title(prefix_text: str) -> str | None:
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
            return None
        return stripped

    return None