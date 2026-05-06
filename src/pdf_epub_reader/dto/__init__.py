"""DTO の公開窓口。

`pdf_epub_reader.dto` から主要な型をまとめて import できるようにし、
呼び出し側が細かなファイル構成を意識しなくて済むようにする。
Phase が進んで DTO が増えても import 文の見通しを保ちやすい。
"""

from pdf_epub_reader.dto.ai_dto import (
    AnalysisMode,
    AnalysisRequest,
    AnalysisResult,
    AnalysisUsage,
    CacheStatus,
    ModelInfo,
)
from pdf_epub_reader.dto.plot_dto import (
    PlotTabPayload,
    PlotlyRenderRequest,
    PlotlySpec,
)
from pdf_epub_reader.dto.document_dto import (
    DocumentInfo,
    PageData,
    RectCoords,
    SelectionContent,
    SelectionSlot,
    SelectionSnapshot,
    TextSelection,
    ToCEntry,
)
from pdf_epub_reader.dto.ui_text_dto import (
    BookmarkPanelTexts,
    AnalysisStatusTexts,
    CacheDialogTexts,
    LanguageDialogTexts,
    MainWindowTexts,
    MarkdownExportTexts,
    PlotlyTexts,
    PlotWindowTexts,
    SettingsDialogTexts,
    SidePanelTexts,
)

__all__ = [
    "AnalysisMode",
    "AnalysisRequest",
    "AnalysisResult",
    "AnalysisUsage",
    "BookmarkPanelTexts",
    "AnalysisStatusTexts",
    "CacheStatus",
    "CacheDialogTexts",
    "DocumentInfo",
    "LanguageDialogTexts",
    "MainWindowTexts",
    "MarkdownExportTexts",
    "ModelInfo",
    "PageData",
    "PlotTabPayload",
    "PlotlyRenderRequest",
    "PlotlySpec",
    "PlotlyTexts",
    "PlotWindowTexts",
    "RectCoords",
    "SettingsDialogTexts",
    "SelectionContent",
    "SelectionSlot",
    "SelectionSnapshot",
    "SidePanelTexts",
    "TextSelection",
    "ToCEntry",
]