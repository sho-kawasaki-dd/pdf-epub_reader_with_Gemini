"""Plotly spec を Figure/HTML へ変換する pure service。"""

from __future__ import annotations

import json

from plotly.graph_objects import Figure
from plotly.io import from_json, to_html

from pdf_epub_reader.dto import PlotlySpec
from pdf_epub_reader.services.plotly_sandbox.cancel import CancelToken
from pdf_epub_reader.services.plotly_sandbox.executor import SandboxExecutor


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
    return _figure_from_json_text(spec.source_text, spec_index=spec.index)


def render_spec(
    spec: PlotlySpec,
    *,
    sandbox: SandboxExecutor | None,
    timeout_s: float,
    cancel_token: CancelToken,
) -> Figure:
    """Plotly spec の言語に応じて Figure を復元する。"""
    if spec.language == "python":
        if sandbox is None:
            raise PlotlyRenderError(
                "restore_failed",
                "Sandbox executor is required for Plotly Python specs.",
                spec_index=spec.index,
            )
        json_payload = sandbox.run(
            spec.source_text,
            timeout_s=timeout_s,
            cancel_token=cancel_token,
        )
        return _figure_from_json_text(json_payload, spec_index=spec.index)
    return parse_spec(spec)


def _figure_from_json_text(source_text: str, *, spec_index: int | None) -> Figure:
    """JSON 文字列を Plotly Figure に復元する。"""
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        raise PlotlyRenderError(
            "invalid_json",
            f"{exc.msg} (line {exc.lineno}, column {exc.colno})",
            spec_index=spec_index,
        ) from exc

    if not isinstance(payload, dict):
        raise PlotlyRenderError(
            "invalid_spec",
            "Plotly spec must be a JSON object.",
            spec_index=spec_index,
        )

    if "data" not in payload and "layout" not in payload:
        raise PlotlyRenderError(
            "invalid_spec",
            "Plotly spec must include at least one of 'data' or 'layout'.",
            spec_index=spec_index,
        )

    try:
        return from_json(json.dumps(payload, ensure_ascii=False))
    except ValueError as exc:
        raise PlotlyRenderError(
            "restore_failed",
            str(exc),
            spec_index=spec_index,
        ) from exc


def figure_to_html(fig: Figure) -> str:
    """Figure をオフライン表示用の完全 HTML に変換する。"""
    return to_html(
        fig,
        include_plotlyjs="inline",
        full_html=True,
        default_width="100%",
        default_height="100vh",
    )