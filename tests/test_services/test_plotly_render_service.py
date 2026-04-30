from __future__ import annotations

import pytest

from pdf_epub_reader.dto import PlotlySpec
from pdf_epub_reader.services.plotly_render_service import (
    PlotlyRenderError,
    figure_to_html,
    parse_spec,
)


def _spec(source_text: str, *, index: int = 0) -> PlotlySpec:
    return PlotlySpec(
        index=index,
        language="json",
        source_text=source_text,
        title="Example Plot",
    )


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