"""Model 層の契約を定義する Protocol 群。

Presenter が具象 Model に直接依存すると、テスト時に差し替えが難しくなり、
将来的な実装変更の影響も受けやすくなる。そこで Model についても
Protocol を用意し、Presenter は「何ができるか」だけに依存させる。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pdf_epub_reader.dto import (
    AnalysisRequest,
    AnalysisResult,
    CacheStatus,
    DocumentInfo,
    PageData,
    RectCoords,
    SelectionContent,
    TextSelection,
)
from pdf_epub_reader.utils.config import AppConfig


@runtime_checkable
class IDocumentModel(Protocol):
    """文書処理 Model の契約。

    PyMuPDF を使うかどうかはこの外から見えない実装詳細であり、
    Presenter は「文書を開ける」「ページを描画できる」「選択範囲から
    テキストを抽出できる」という能力だけを知れば十分である。
    """

    async def open_document(
        self, file_path: str, password: str | None = None
    ) -> DocumentInfo: ...
    async def render_page(self, page_number: int, dpi: int) -> PageData: ...
    async def render_page_range(
        self, start: int, end: int, dpi: int
    ) -> list[PageData]: ...
    async def extract_text(
        self, page_number: int, rect: RectCoords
    ) -> TextSelection: ...
    async def extract_content(
        self,
        page_number: int,
        rect: RectCoords,
        dpi: int,
        force_include_image: bool = False,
        auto_detect_embedded_images: bool = True,
        auto_detect_math_fonts: bool = True,
    ) -> SelectionContent: ...
    async def extract_all_text(self) -> str: ...
    def close_document(self) -> None: ...
    def get_document_info(self) -> DocumentInfo | None: ...
    def update_config(self, config: AppConfig) -> None:
        """アプリケーション設定を更新しページキャッシュをクリアする。

        Phase 5 で追加。設定ダイアログで変更された設定を
        DocumentModel に反映するために Presenter が呼び出す。
        """
        ...


@runtime_checkable
class IAIModel(Protocol):
    """AI 解析 Model の契約。

    Gemini API の詳細はこの内側に閉じ込め、Presenter からは
    「解析する」「キャッシュを作る」「キャッシュ状態を読む」といった
    業務上の操作だけが見える形にする。
    """

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult: ...
    async def create_cache(self, full_text: str) -> CacheStatus: ...
    async def get_cache_status(self) -> CacheStatus: ...
    async def invalidate_cache(self) -> None: ...
    async def count_tokens(self, text: str) -> int: ...
