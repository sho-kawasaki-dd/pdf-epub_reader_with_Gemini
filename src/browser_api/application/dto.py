from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from pdf_epub_reader.dto import ModelInfo


class AnalyzeSelectionRect(TypedDict):
    left: float
    top: float
    width: float
    height: float


class AnalyzeSelectionMetadataItem(TypedDict, total=False):
    id: str
    order: int
    source: Literal["text-selection", "free-rectangle"]
    text: str
    include_image: bool
    image_index: int | None
    url: str | None
    page_title: str | None
    viewport_width: float | None
    viewport_height: float | None
    device_pixel_ratio: float | None
    rect: AnalyzeSelectionRect | None


class AnalyzeSelectionMetadata(TypedDict, total=False):
    url: str | None
    page_title: str | None
    viewport_width: float | None
    viewport_height: float | None
    device_pixel_ratio: float | None
    rect: AnalyzeSelectionRect | None
    items: list[AnalyzeSelectionMetadataItem]


@dataclass(frozen=True, slots=True)
class AnalyzeTranslateCommand:
    """Application-layer request detached from HTTP schema and transport details."""

    text: str
    model_name: str | None
    images: list[str]
    mode: Literal["translation", "translation_with_explanation", "custom_prompt"]
    custom_prompt: str | None = None
    selection_metadata: AnalyzeSelectionMetadata | None = None


@dataclass(frozen=True, slots=True)
class AnalyzeTranslateResult:
    """Normalized analyze result returned by the service before HTTP serialization."""

    mode: Literal["translation", "translation_with_explanation", "custom_prompt"]
    translated_text: str
    explanation: str | None
    raw_response: str
    used_mock: bool
    image_count: int
    availability: Literal["live", "mock"] = "live"
    degraded_reason: str | None = None
    selection_metadata: AnalyzeSelectionMetadata | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogResult:
    """Model list plus availability metadata for degraded popup states."""

    models: list[ModelInfo]
    source: Literal["live", "config_fallback"]
    availability: Literal["live", "degraded"]
    detail: str | None = None
    degraded_reason: str | None = None