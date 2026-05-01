from __future__ import annotations

from pdf_epub_reader.services.plotly_extraction_service import extract_plotly_specs


class TestPlotlyExtractionService:
    def test_extracts_json_fenced_block(self) -> None:
        markdown = (
            "## Velocity Plot\n\n"
            "```json\n"
            '{"data": [{"type": "scatter"}], "layout": {"title": "Velocity"}}\n'
            "```"
        )

        specs = extract_plotly_specs(markdown)

        assert len(specs) == 1
        assert specs[0].index == 0
        assert specs[0].language == "json"
        assert specs[0].title == "Velocity Plot"
        assert '"type": "scatter"' in specs[0].source_text

    def test_extracts_unlabeled_json_block_when_body_starts_with_object(self) -> None:
        markdown = (
            "Plot summary\n\n"
            "```\n"
            '{"data": [], "layout": {}}\n'
            "```"
        )

        specs = extract_plotly_specs(markdown)

        assert len(specs) == 1
        assert specs[0].title == "Plot summary"
        assert specs[0].source_text == '{"data": [], "layout": {}}'

    def test_ignores_non_json_language_blocks(self) -> None:
        markdown = (
            "```text\n"
            "not python or json\n"
            "```\n\n"
            "```text\n"
            "not json\n"
            "```"
        )

        specs = extract_plotly_specs(markdown)

        assert specs == []

    def test_extracts_multiple_blocks_and_preserves_order(self) -> None:
        markdown = (
            "## First Plot\n\n"
            "```json\n"
            '{"data": [{"name": "a"}], "layout": {}}\n'
            "```\n\n"
            "Interim note\n\n"
            "```\n"
            '{"data": [{"name": "b"}], "layout": {}}\n'
            "```"
        )

        specs = extract_plotly_specs(markdown)

        assert [spec.index for spec in specs] == [0, 1]
        assert specs[0].title == "First Plot"
        assert specs[1].title == "First Plot"
        assert '"name": "a"' in specs[0].source_text
        assert '"name": "b"' in specs[1].source_text

    def test_extracts_python_blocks_and_preserves_mixed_order(self) -> None:
        markdown = (
            "## First Plot\n\n"
            "```python\n"
            "print(fig.to_json())\n"
            "```\n\n"
            "```json\n"
            '{"data": [{"name": "b"}], "layout": {}}\n'
            "```"
        )

        specs = extract_plotly_specs(markdown)

        assert [spec.language for spec in specs] == ["python", "json"]
        assert specs[0].title == "First Plot"
        assert specs[1].title == "First Plot"
        assert specs[0].source_text == "print(fig.to_json())"

    def test_returns_empty_list_for_empty_or_irrelevant_markdown(self) -> None:
        assert extract_plotly_specs("") == []
        assert extract_plotly_specs("No fenced blocks here.") == []

    def test_keeps_invalid_json_as_raw_source_text(self) -> None:
        markdown = (
            "### Broken Plot\n\n"
            "```json\n"
            '{"data": [}\n'
            "```"
        )

        specs = extract_plotly_specs(markdown)

        assert len(specs) == 1
        assert specs[0].title == "Broken Plot"
        assert specs[0].source_text == '{"data": [}'