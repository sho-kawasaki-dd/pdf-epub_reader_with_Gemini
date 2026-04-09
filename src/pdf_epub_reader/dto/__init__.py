"""DTO の公開窓口。

`pdf_epub_reader.dto` から主要な型をまとめて import できるようにし、
呼び出し側が細かなファイル構成を意識しなくて済むようにする。
Phase が進んで DTO が増えても import 文の見通しを保ちやすい。
"""

from pdf_epub_reader.dto.ai_dto import (
    AnalysisMode,
    AnalysisRequest,
    AnalysisResult,
    CacheStatus,
)
from pdf_epub_reader.dto.document_dto import (
    DocumentInfo,
    PageData,
    RectCoords,
    TextSelection,
)

__all__ = [
    "AnalysisMode",
    "AnalysisRequest",
    "AnalysisResult",
    "CacheStatus",
    "DocumentInfo",
    "PageData",
    "RectCoords",
    "TextSelection",
]