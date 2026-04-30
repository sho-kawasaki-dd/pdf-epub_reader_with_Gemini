"""Plotly spec を Figure/HTML へ変換する pure service。"""

from __future__ import annotations

import json

from plotly.graph_objects import Figure
from plotly.io import from_json, to_html

from pdf_epub_reader.dto import PlotlySpec


class PlotlyRenderError(Exception):
    """Plotly spec の復元失敗を呼び出し側で判別しやすい形に包む例外。"""

    def __init__(
        self,
        code: str,
        details: str,
        *,
        spec_index: int | None = None,
    ) -> None:
        super().__init__(details)
        self.code = code
        self.details = details
        self.spec_index = spec_index


def parse_spec(spec: PlotlySpec) -> Figure:
    """抽出済み Plotly spec を Figure に復元する。"""
    try:
        payload = json.loads(spec.source_text)
    except json.JSONDecodeError as exc:
        raise PlotlyRenderError(
            "invalid_json",
            f"{exc.msg} (line {exc.lineno}, column {exc.colno})",
            spec_index=spec.index,
        ) from exc

    if not isinstance(payload, dict):
        raise PlotlyRenderError(
            "invalid_spec",
            "Plotly spec must be a JSON object.",
            spec_index=spec.index,
        )

    if "data" not in payload and "layout" not in payload:
        raise PlotlyRenderError(
            "invalid_spec",
            "Plotly spec must include at least one of 'data' or 'layout'.",
            spec_index=spec.index,
        )

    try:
        return from_json(json.dumps(payload, ensure_ascii=False))
    except ValueError as exc:
        raise PlotlyRenderError(
            "restore_failed",
            str(exc),
            spec_index=spec.index,
        ) from exc


def figure_to_html(fig: Figure) -> str:
    """Figure をオフライン表示用の完全 HTML に変換する。"""
    return to_html(fig, include_plotlyjs="inline", full_html=True)