from __future__ import annotations

import pytest

from pdf_epub_reader.dto import PlotlySpec
from pdf_epub_reader.services.plotly_sandbox.cancel import CancelToken
from pdf_epub_reader.services.plotly_render_service import (
    PlotlyRenderError,
    figure_to_html,
    parse_spec,
    render_spec,
)


def _spec(source_text: str, *, index: int = 0) -> PlotlySpec:
    return PlotlySpec(
        index=index,
        language="json",
        source_text=source_text,
        title="Example Plot",
    )


class _FakeSandboxExecutor:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls: list[tuple[str, float, CancelToken]] = []

    def run(
        self,
        code: str,
        *,
        timeout_s: float,
        cancel_token: CancelToken,
    ) -> str:
        self.calls.append((code, timeout_s, cancel_token))
        return self.payload


class TestPlotlyRenderService:
    def test_parse_spec_restores_figure(self) -> None:
        spec = _spec(
            '{"data": [{"type": "scatter", "x": [1, 2], "y": [3, 4]}], '
            '"layout": {"title": {"text": "Velocity"}}}'
        )

        figure = parse_spec(spec)

        assert len(figure.data) == 1
        assert figure.data[0].type == "scatter"
        assert figure.layout.title.text == "Velocity"

    def test_parse_spec_raises_invalid_json_error(self) -> None:
        spec = _spec('{"data": [}')

        with pytest.raises(PlotlyRenderError) as exc_info:
            parse_spec(spec)

        assert exc_info.value.code == "invalid_json"
        assert exc_info.value.spec_index == 0

    def test_parse_spec_raises_when_required_keys_missing(self) -> None:
        spec = _spec('{"frames": []}')

        with pytest.raises(PlotlyRenderError) as exc_info:
            parse_spec(spec)

        assert exc_info.value.code == "invalid_spec"
        assert "data' or 'layout" in exc_info.value.details

    def test_parse_spec_raises_when_json_is_not_object(self) -> None:
        spec = _spec('[1, 2, 3]')

        with pytest.raises(PlotlyRenderError) as exc_info:
            parse_spec(spec)

        assert exc_info.value.code == "invalid_spec"
        assert exc_info.value.details == "Plotly spec must be a JSON object."

    def test_figure_to_html_inlines_plotly_js(self) -> None:
        figure = parse_spec(
            _spec(
                '{"data": [{"type": "bar", "x": ["A"], "y": [5]}], '
                '"layout": {"title": {"text": "Bars"}}}'
            )
        )

        html = figure_to_html(figure)

        assert html.lstrip().startswith("<html>")
        assert "Plotly.newPlot" in html
        assert 'src="https://cdn.plot.ly' not in html
        assert 'style="height:100vh; width:100%;"' in html

    def test_render_spec_uses_sandbox_for_python_specs(self) -> None:
        spec = PlotlySpec(
            index=0,
            language="python",
            source_text="print(fig.to_json())",
            title="Python Plot",
        )
        sandbox = _FakeSandboxExecutor('{"data": [{"type": "scatter"}], "layout": {}}')
        cancel_token = CancelToken()

        figure = render_spec(
            spec,
            sandbox=sandbox,
            timeout_s=5.0,
            cancel_token=cancel_token,
        )

        assert len(figure.data) == 1
        assert sandbox.calls == [
            ("print(fig.to_json())", 5.0, cancel_token)
        ]