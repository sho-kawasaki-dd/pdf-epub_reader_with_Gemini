"""Presenter テスト用の Mock Model 実装。

本物の PyMuPDF や Gemini API を使わず、Presenter の制御フローだけを
検証したいときに使う。呼び出し履歴を保存し、戻り値は意図的に単純化した
ダミーデータを返す。
"""

from __future__ import annotations

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
from pdf_epub_reader.utils.exceptions import (
    DocumentOpenError,
    DocumentPasswordRequired,
)


class MockDocumentModel:
    """IDocumentModel を満たす文書処理のダミー実装。"""

    def __init__(self) -> None:
        # Presenter がどの順序で何を要求したかを後から確認するための履歴。
        self.calls: list[tuple[str, tuple]] = []
        self._document_info: DocumentInfo | None = None
        # テストでパスワード要求の振る舞いを制御するフラグ。
        # True にすると open_document が password なしで
        # DocumentPasswordRequired を送出する。
        self._should_require_password: bool = False
        # パスワード認証時に受け入れるパスワード。
        self._accepted_password: str = "test123"
        # テストで自動検出シナリオを制御するフラグ。
        # None 以外を設定すると extract_content がクロップ画像付きで返す。
        self._simulate_detection_reason: str | None = None

    async def open_document(
        self, file_path: str, password: str | None = None
    ) -> DocumentInfo:
        # open_document 後に get_document_info が使えるよう内部状態も更新する。
        self.calls.append(("open_document", (file_path, password)))
        if self._should_require_password and password is None:
            raise DocumentPasswordRequired(file_path)
        if (
            self._should_require_password
            and password is not None
            and password != self._accepted_password
        ):
            raise DocumentOpenError(f"Invalid password for {file_path}")
        self._document_info = DocumentInfo(
            file_path=file_path,
            total_pages=3,
            title="Mock Document",
            page_sizes=[(612.0, 792.0)] * 3,
        )
        return self._document_info

    async def render_page(self, page_number: int, dpi: int) -> PageData:
        # 幅と高さは PDF の代表的なレターサイズを簡易計算して返す。
        # Presenter にとって重要なのは「dpi が伝播しているか」であり、
        # 実画像の正しさではない。
        self.calls.append(("render_page", (page_number, dpi)))
        return PageData(
            page_number=page_number,
            image_data=b"fake-image-data",
            width=int(612 * dpi / 72),
            height=int(792 * dpi / 72),
        )

    async def render_page_range(
        self, start: int, end: int, dpi: int
    ) -> list[PageData]:
        # 複数ページ描画のテストでは「指定レンジの件数が返ること」が重要なので、
        # ページ番号に応じて区別できるダミーデータを作る。
        self.calls.append(("render_page_range", (start, end, dpi)))
        return [
            PageData(
                page_number=i,
                image_data=f"fake-image-{i}".encode(),
                width=int(612 * dpi / 72),
                height=int(792 * dpi / 72),
            )
            for i in range(start, end + 1)
        ]

    async def extract_text(
        self, page_number: int, rect: RectCoords
    ) -> TextSelection:
        # 選択結果にページ番号を埋めておくと、テストで伝播を確認しやすい。
        self.calls.append(("extract_text", (page_number, rect)))
        return TextSelection(
            page_number=page_number,
            rect=rect,
            extracted_text="Mock extracted text from page "
            + str(page_number),
        )

    async def extract_content(
        self,
        page_number: int,
        rect: RectCoords,
        dpi: int,
        force_include_image: bool = False,
        auto_detect_embedded_images: bool = True,
        auto_detect_math_fonts: bool = True,
    ) -> SelectionContent:
        """マルチモーダルコンテンツ抽出のダミー実装。

        force_include_image が True の場合のみダミーのクロップ画像を付与する。
        テストで伝播チェックに使うため、引数をすべて記録する。
        """
        self.calls.append((
            "extract_content",
            (page_number, rect, dpi, force_include_image,
             auto_detect_embedded_images, auto_detect_math_fonts),
        ))
        detection = self._simulate_detection_reason
        cropped = (
            b"fake-cropped-image"
            if force_include_image or detection
            else None
        )
        return SelectionContent(
            page_number=page_number,
            rect=rect,
            extracted_text="Mock extracted text from page "
            + str(page_number),
            cropped_image=cropped,
            detection_reason=detection,
        )

    async def extract_all_text(self) -> str:
        """文書全文取得のダミー実装。"""
        self.calls.append(("extract_all_text", ()))
        return "Full mock document text."

    def close_document(self) -> None:
        """文書クローズを記録し、内部状態を初期化する。"""
        self.calls.append(("close_document", ()))
        self._document_info = None

    def get_document_info(self) -> DocumentInfo | None:
        """最後に open した文書情報を返す。"""
        return self._document_info

    def get_calls(self, method_name: str) -> list[tuple]:
        """指定メソッドの呼び出し引数一覧を返す。"""
        return [args for name, args in self.calls if name == method_name]


class MockAIModel:
    """IAIModel を満たす AI 解析のダミー実装。"""

    def __init__(self) -> None:
        # API 呼び出しの代わりに、要求内容と戻り値だけを deterministic にする。
        self.calls: list[tuple[str, tuple]] = []

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        # Request の内容に応じて戻り値を少し変えることで、
        # Presenter の分岐が正しいかを検証しやすくする。
        self.calls.append(("analyze", (request,)))
        return AnalysisResult(
            translated_text="Mock translation of: " + request.text,
            explanation=(
                "Mock explanation" if request.include_explanation else None
            ),
            raw_response="Raw: " + request.text,
        )

    async def create_cache(self, full_text: str) -> CacheStatus:
        """キャッシュ作成成功時を模した固定レスポンスを返す。"""
        self.calls.append(("create_cache", (full_text,)))
        return CacheStatus(
            is_active=True,
            ttl_seconds=3600,
            token_count=1000,
            cache_name="mock-cache",
        )

    async def get_cache_status(self) -> CacheStatus:
        """キャッシュ未作成の状態を返す。"""
        self.calls.append(("get_cache_status", ()))
        return CacheStatus(is_active=False)

    async def invalidate_cache(self) -> None:
        """キャッシュ無効化呼び出しを記録する。"""
        self.calls.append(("invalidate_cache", ()))

    async def count_tokens(self, text: str) -> int:
        """単語数ベースの簡易トークン数を返すダミー実装。"""
        self.calls.append(("count_tokens", (text,)))
        return len(text.split())

    def get_calls(self, method_name: str) -> list[tuple]:
        """指定メソッドの呼び出し引数一覧を返す。"""
        return [args for name, args in self.calls if name == method_name]
