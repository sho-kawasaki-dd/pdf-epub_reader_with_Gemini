from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pdf_epub_reader.dto import (
    AnalysisMode,
    AnalysisResult,
    AnalysisUsage,
    DocumentInfo,
    RectCoords,
    SelectionSlot,
    SelectionSnapshot,
)
from pdf_epub_reader.services.markdown_export_service import (
    MarkdownExportPayload,
    build_markdown_export_document,
    build_markdown_export_filename,
)
from pdf_epub_reader.services.translation_service import TranslationService
from pdf_epub_reader.utils.config import AppConfig


def _payload(
    *,
    result: AnalysisResult | None = None,
    document_info: DocumentInfo | None = None,
    snapshot: SelectionSnapshot | None = None,
    action_mode: AnalysisMode = AnalysisMode.TRANSLATION,
    model_name: str = "gemini-2.5-pro",
) -> MarkdownExportPayload:
    return MarkdownExportPayload(
        result=result
        or AnalysisResult(
            translated_text="Translated body",
            explanation="Supporting explanation",
            raw_response="Raw response body",
            usage=AnalysisUsage(total_token_count=42),
        ),
        document_info=document_info
        or DocumentInfo(
            file_path=r"C:\docs\Example Paper.pdf",
            total_pages=10,
            title="Example Paper",
        ),
        selection_snapshot=snapshot
        or SelectionSnapshot(
            slots=(
                SelectionSlot(
                    selection_id="sel-1",
                    display_number=1,
                    page_number=0,
                    rect=RectCoords(1, 2, 3, 4),
                    read_state="ready",
                    extracted_text="Selected source paragraph",
                ),
            )
        ),
        action_mode=action_mode,
        model_name=model_name,
    )


class TestMarkdownExportService:
    def test_builds_markdown_with_default_sections(self) -> None:
        texts = TranslationService().build_markdown_export_texts("en")

        markdown = build_markdown_export_document(
            _payload(),
            AppConfig(),
            texts,
            exported_at=datetime(2026, 4, 20, 10, 30, 0, tzinfo=timezone.utc),
        )

        assert markdown.startswith("# Example Paper")
        assert "- Exported At: 2026-04-20T10:30:00Z" in markdown
        assert "## Selections" in markdown
        assert "1. Selected source paragraph" in markdown
        assert "## AI Response" in markdown
        assert "Translated body" in markdown
        assert "## Explanation" in markdown
        assert "Supporting explanation" in markdown
        assert "## Raw Response" not in markdown
        assert "## Document Metadata" not in markdown
        assert "## Usage Metrics" not in markdown
        assert markdown.startswith("---") is False

    def test_includes_optional_sections_when_enabled(self) -> None:
        texts = TranslationService().build_markdown_export_texts("en")
        config = AppConfig(
            export_include_raw_response=True,
            export_include_document_metadata=True,
            export_include_usage_metrics=True,
            export_include_yaml_frontmatter=True,
        )
        payload = _payload(
            action_mode=AnalysisMode.CUSTOM_PROMPT,
            result=AnalysisResult(
                raw_response="Prompt result",
                usage=AnalysisUsage(
                    prompt_token_count=10,
                    cached_content_token_count=5,
                    candidates_token_count=3,
                    total_token_count=18,
                ),
            ),
        )

        markdown = build_markdown_export_document(
            payload,
            config,
            texts,
            exported_at=datetime(2026, 4, 20, 10, 30, 0, tzinfo=timezone.utc),
        )

        assert markdown.startswith("---\n")
        assert 'action: "custom_prompt"' in markdown
        assert "selectionCount: 1" in markdown
        assert "## Raw Response" in markdown
        assert "```text" in markdown
        assert "## Document Metadata" in markdown
        assert "- File Name: Example Paper.pdf" in markdown
        assert "## Usage Metrics" in markdown
        assert "- Total Tokens: 18" in markdown

    def test_localizes_labels_from_ui_language(self) -> None:
        texts = TranslationService().build_markdown_export_texts("ja")

        markdown = build_markdown_export_document(
            _payload(action_mode=AnalysisMode.CUSTOM_PROMPT),
            AppConfig(),
            texts,
            exported_at=datetime(2026, 4, 20, 10, 30, 0, tzinfo=timezone.utc),
        )

        assert "- 保存日時: 2026-04-20T10:30:00Z" in markdown
        assert "- アクション: カスタムプロンプト" in markdown
        assert "## 選択一覧" in markdown
        assert "## AI 応答" in markdown
        assert "## 解説" in markdown

    def test_sanitizes_filename_and_falls_back_to_file_stem(self) -> None:
        document_info = DocumentInfo(
            file_path=r"C:\docs\fallback title.pdf",
            total_pages=1,
            title=None,
        )

        filename = build_markdown_export_filename(
            document_info,
            exported_at=datetime(2026, 4, 20, 10, 30, 45, tzinfo=timezone.utc),
        )

        assert filename == "fallback title_20260420T103045.md"

    def test_uses_sanitized_document_title_for_filename(self) -> None:
        document_info = DocumentInfo(
            file_path=r"C:\docs\paper.pdf",
            total_pages=1,
            title='Example:/\\?%*:|"<> title',
        )

        filename = build_markdown_export_filename(
            document_info,
            exported_at=datetime(2026, 4, 20, 10, 30, 45, tzinfo=timezone.utc),
        )

        assert filename == "Example----------- title_20260420T103045.md"

    def test_rejects_result_without_successful_content(self) -> None:
        texts = TranslationService().build_markdown_export_texts("en")
        payload = _payload(
            result=AnalysisResult(
                translated_text="  ",
                explanation="Explanation only",
                raw_response="  ",
            )
        )

        with pytest.raises(ValueError, match="No successful AI result"):
            build_markdown_export_document(payload, AppConfig(), texts)