"""Markdown export document assembly helpers for desktop AI results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pdf_epub_reader.dto import (
    AnalysisMode,
    AnalysisResult,
    DocumentInfo,
    MarkdownExportTexts,
    SelectionSnapshot,
)
from pdf_epub_reader.utils.config import AppConfig


@dataclass(frozen=True)
class MarkdownExportPayload:
    """Pure input bundle for Markdown export generation."""

    result: AnalysisResult
    document_info: DocumentInfo
    selection_snapshot: SelectionSnapshot
    action_mode: AnalysisMode
    model_name: str = ""


def build_markdown_export_document(
    payload: MarkdownExportPayload,
    config: AppConfig,
    texts: MarkdownExportTexts,
    *,
    exported_at: datetime | None = None,
) -> str:
    """Build a Markdown document for a successful desktop AI result."""
    if not has_exportable_content(payload.result):
        raise ValueError("No successful AI result is available to export.")

    exported_at_utc = _normalize_exported_at(exported_at)
    primary_response = _resolve_primary_response(payload.result)
    explanation = (payload.result.explanation or "").strip()
    raw_response = payload.result.raw_response.strip()
    title = resolve_document_title(payload.document_info)
    source_file = Path(payload.document_info.file_path).name
    selections = resolve_selection_list(payload.selection_snapshot)

    lines: list[str] = []

    if config.export_include_yaml_frontmatter:
        lines.extend(
            [
                "---",
                f"title: {_to_yaml_string(title)}",
                f"exportedAt: {_to_yaml_string(_format_iso8601(exported_at_utc))}",
                f"action: {_to_yaml_string(payload.action_mode.value)}",
                f"documentTitle: {_to_yaml_string(title)}",
                f"sourceFile: {_to_yaml_string(source_file)}",
                f"selectionCount: {len(selections)}",
            ]
        )
        if payload.model_name.strip():
            lines.append(f"modelName: {_to_yaml_string(payload.model_name.strip())}")
        lines.extend(["---", ""])

    lines.extend(
        [
            f"# {title}",
            "",
            f"- {texts.exported_at_label}: {_format_iso8601(exported_at_utc)}",
            f"- {texts.action_label}: {format_action_label(payload.action_mode, texts)}",
            f"- {texts.model_label}: {payload.model_name.strip() or 'Not recorded'}",
            f"- {texts.source_document_label}: {title}",
            f"- {texts.source_file_label}: {source_file}",
            "",
        ]
    )

    if config.export_include_selection_list and selections:
        lines.append(f"## {texts.selections_section_title}")
        lines.append("")
        for index, selection in enumerate(selections, start=1):
            lines.append(f"{index}. {selection}")
        lines.append("")

    lines.append(f"## {texts.ai_response_section_title}")
    lines.append("")
    lines.append(primary_response)
    lines.append("")

    if config.export_include_explanation and explanation:
        lines.append(f"## {texts.explanation_section_title}")
        lines.append("")
        lines.append(explanation)
        lines.append("")

    if config.export_include_raw_response and raw_response:
        lines.append(f"## {texts.raw_response_section_title}")
        lines.append("")
        lines.append("```text")
        lines.append(raw_response)
        lines.append("```")
        lines.append("")

    if config.export_include_document_metadata:
        lines.append(f"## {texts.document_metadata_section_title}")
        lines.append("")
        lines.append(f"- {texts.document_title_label}: {title}")
        lines.append(f"- {texts.file_name_label}: {source_file}")
        lines.append(f"- {texts.selection_count_label}: {len(selections)}")
        lines.append("")

    if config.export_include_usage_metrics and has_usage_metrics(payload.result):
        usage = payload.result.usage
        lines.append(f"## {texts.usage_metrics_section_title}")
        lines.append("")
        if usage is not None and usage.prompt_token_count is not None:
            lines.append(
                f"- {texts.prompt_tokens_label}: {usage.prompt_token_count}"
            )
        if usage is not None and usage.cached_content_token_count is not None:
            lines.append(
                f"- {texts.cached_tokens_label}: {usage.cached_content_token_count}"
            )
        if usage is not None and usage.candidates_token_count is not None:
            lines.append(
                f"- {texts.candidates_tokens_label}: {usage.candidates_token_count}"
            )
        if usage is not None and usage.total_token_count is not None:
            lines.append(
                f"- {texts.total_tokens_label}: {usage.total_token_count}"
            )
        lines.append("")

    return _trim_trailing_blank_lines(lines)


def build_markdown_export_filename(
    document_info: DocumentInfo,
    *,
    exported_at: datetime | None = None,
) -> str:
    """Build the default markdown export filename."""
    exported_at_utc = _normalize_exported_at(exported_at)
    sanitized_title = sanitize_export_title(resolve_document_title(document_info))
    return f"{sanitized_title}_{_format_filename_timestamp(exported_at_utc)}.md"


def resolve_document_title(document_info: DocumentInfo) -> str:
    """Resolve the export title from document metadata or file basename."""
    title = (document_info.title or "").strip()
    if title:
        return title
    fallback = Path(document_info.file_path).stem.strip()
    return fallback or "gem-read-export"


def sanitize_export_title(title: str) -> str:
    """Sanitize a title for use in a filesystem-safe export filename."""
    sanitized = (
        title.strip()
        .replace("/", "-")
        .replace("\\", "-")
        .replace("?", "-")
        .replace("%", "-")
        .replace("*", "-")
        .replace(":", "-")
        .replace("|", "-")
        .replace('"', "-")
        .replace("<", "-")
        .replace(">", "-")
    )
    sanitized = " ".join(sanitized.split())[:80].rstrip(" -").strip()
    return sanitized or "gem-read-export"


def resolve_selection_list(snapshot: SelectionSnapshot) -> list[str]:
    """Resolve non-empty extracted texts from the snapshot in display order."""
    selections: list[str] = []
    for slot in snapshot.slots:
        text = slot.extracted_text.strip()
        if text:
            selections.append(text)
    return selections


def has_exportable_content(result: AnalysisResult) -> bool:
    """Return True when the result contains exportable content."""
    return bool((result.translated_text or "").strip() or result.raw_response.strip())


def has_usage_metrics(result: AnalysisResult) -> bool:
    """Return True when any usage metric is available."""
    usage = result.usage
    return bool(
        usage is not None
        and (
            usage.prompt_token_count is not None
            or usage.cached_content_token_count is not None
            or usage.candidates_token_count is not None
            or usage.total_token_count is not None
        )
    )


def format_action_label(
    action_mode: AnalysisMode,
    texts: MarkdownExportTexts,
) -> str:
    """Resolve the localized action label for the export document."""
    if action_mode is AnalysisMode.CUSTOM_PROMPT:
        return texts.action_custom_prompt_label
    return texts.action_translation_label


def _resolve_primary_response(result: AnalysisResult) -> str:
    translated_text = (result.translated_text or "").strip()
    if translated_text:
        return translated_text
    return result.raw_response.strip()


def _normalize_exported_at(exported_at: datetime | None) -> datetime:
    value = exported_at or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_iso8601(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _format_filename_timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _to_yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _trim_trailing_blank_lines(lines: list[str]) -> str:
    next_lines = list(lines)
    while next_lines and next_lines[-1] == "":
        next_lines.pop()
    return "\n".join(next_lines)