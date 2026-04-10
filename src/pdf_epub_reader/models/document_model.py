"""文書処理 Model の PyMuPDF 本実装。

PDF および EPUB をページ単位で画像レンダリングし、テキスト抽出・
目次取得・パスワード保護対応を提供する。

**スレッド安全性について:**
PyMuPDF の ``fitz.Document`` はスレッドセーフではないため、
すべての fitz 操作は ``ThreadPoolExecutor(max_workers=1)`` で
直列化して実行する。Presenter から見た呼び出しパターンは常に
``await model.method()`` で統一される。

**LRU キャッシュ:**
レンダリング済みページ画像を ``collections.OrderedDict`` で
手動 LRU 管理する。``functools.lru_cache`` は async 非対応のため使えない。
"""

from __future__ import annotations

import asyncio
import io
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

from pdf_epub_reader.dto import (
    DocumentInfo,
    PageData,
    RectCoords,
    SelectionContent,
    TextSelection,
    ToCEntry,
)
from pdf_epub_reader.utils.config import AppConfig, load_config
from pdf_epub_reader.utils.exceptions import (
    DocumentOpenError,
    DocumentPasswordRequired,
    DocumentRenderError,
)

logger = logging.getLogger(__name__)


def _generate_error_page(width: int, height: int, message: str) -> bytes:
    """レンダリング失敗時に表示するエラーページ画像を生成する。

    薄赤背景にエラーメッセージを描画した PNG バイト列を返す。
    Pillow を使用するため、フォント未インストール環境でも
    デフォルトフォントにフォールバックする。

    Args:
        width: 画像の幅 (px)。
        height: 画像の高さ (px)。
        message: 表示するエラーメッセージ。
    """
    img = Image.new("RGB", (width, height), color=(255, 220, 220))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial", size=14)
    except OSError:
        font = ImageFont.load_default()
    # テキストをページ中央付近に描画する。
    draw.text((20, height // 2 - 10), message, fill=(180, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class DocumentModel:
    """IDocumentModel の PyMuPDF 本実装。

    PDF/EPUB の閲覧に必要なすべての操作を非同期メソッドとして公開する。
    内部では ``ThreadPoolExecutor`` を介してブロッキング I/O と
    CPU-bound 処理をワーカースレッドに逃がす。
    """

    def __init__(self, config: AppConfig | None = None) -> None:
        """DocumentModel を初期化する。

        Args:
            config: アプリケーション設定。None の場合は JSON ファイルまたは
                    デフォルト値から読み込む。テスト時にはカスタム設定を渡せる。
        """
        self._config = config or load_config()
        # PyMuPDF は非スレッドセーフなので、全 fitz 操作を 1 ワーカーで直列化する。
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._doc: fitz.Document | None = None
        self._document_info: DocumentInfo | None = None
        # LRU キャッシュ: (page_number, dpi) → PNG/JPEG bytes
        self._page_cache: OrderedDict[tuple[int, int], bytes] = OrderedDict()

    # --- Public async API (IDocumentModel 準拠) ---

    async def open_document(
        self, file_path: str, password: str | None = None
    ) -> DocumentInfo:
        """文書ファイルを開き、メタデータと目次を返す。

        パスワード保護 PDF を password 引数なしで開こうとした場合は
        ``DocumentPasswordRequired`` を送出する。Presenter はこれを catch し、
        View にパスワードダイアログを表示させてから再呼び出しする。

        Args:
            file_path: 開く文書ファイルの絶対パス。
            password: パスワード保護 PDF 用。不要な場合は None。

        Returns:
            開いた文書のメタデータ (DocumentInfo)。

        Raises:
            DocumentPasswordRequired: パスワード保護文書を password=None で開いた場合。
            DocumentOpenError: ファイルが存在しない、破損、認証失敗など。
        """
        loop = asyncio.get_running_loop()
        try:
            doc_info = await loop.run_in_executor(
                self._executor,
                self._open_document_sync,
                file_path,
                password,
            )
        except (DocumentPasswordRequired, DocumentOpenError):
            # Model 層の例外はそのまま Presenter へ伝播する。
            raise
        except Exception as e:
            raise DocumentOpenError(
                f"Failed to open '{file_path}': {e}"
            ) from e

        return doc_info

    async def render_page(self, page_number: int, dpi: int) -> PageData:
        """指定ページを画像としてレンダリングし PageData を返す。

        LRU キャッシュにヒットした場合はワーカースレッドを使わず即時返却する。
        レンダリングに失敗した場合はエラーページ画像を生成して返す。

        Args:
            page_number: 0-indexed のページ番号。
            dpi: レンダリング解像度。
        """
        cache_key = (page_number, dpi)

        # キャッシュヒット時は即座に返す。
        if cache_key in self._page_cache:
            self._page_cache.move_to_end(cache_key)
            image_data = self._page_cache[cache_key]
            width, height = self._get_page_dimensions(page_number, dpi)
            return PageData(
                page_number=page_number,
                image_data=image_data,
                width=width,
                height=height,
            )

        loop = asyncio.get_running_loop()
        try:
            page_data = await loop.run_in_executor(
                self._executor,
                self._render_page_sync,
                page_number,
                dpi,
            )
        except Exception as e:
            logger.error("Page %d render failed: %s", page_number, e)
            # エラー時はダミーのエラーページ画像を返す（例外は送出しない）。
            width, height = self._get_page_dimensions_fallback(dpi)
            error_image = _generate_error_page(
                width, height, f"Error rendering page {page_number + 1}"
            )
            return PageData(
                page_number=page_number,
                image_data=error_image,
                width=width,
                height=height,
            )

        # キャッシュに追加し、上限超過時は最古エントリを除去する。
        self._page_cache[cache_key] = page_data.image_data
        self._page_cache.move_to_end(cache_key)
        if len(self._page_cache) > self._config.page_cache_max_size:
            self._page_cache.popitem(last=False)

        return page_data

    async def render_page_range(
        self, start: int, end: int, dpi: int
    ) -> list[PageData]:
        """指定範囲の各ページを個別にレンダリングして返す。

        各ページは ``render_page`` を経由するため、キャッシュが活用される。

        Args:
            start: 開始ページ番号 (0-indexed, inclusive)。
            end: 終了ページ番号 (0-indexed, inclusive)。
            dpi: レンダリング解像度。
        """
        return [
            await self.render_page(i, dpi) for i in range(start, end + 1)
        ]

    async def extract_text(
        self, page_number: int, rect: RectCoords
    ) -> TextSelection:
        """指定ページの矩形領域からテキストを抽出する。

        座標は PDF の point 単位 (72dpi 基準) で指定する。

        Args:
            page_number: 0-indexed のページ番号。
            rect: 抽出対象の矩形座標。
        """
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(
            self._executor,
            self._extract_text_sync,
            page_number,
            rect,
        )
        return TextSelection(
            page_number=page_number,
            rect=rect,
            extracted_text=text,
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
        """選択矩形からマルチモーダルコンテンツを抽出する。

        テキストは常に抽出し、設定に応じて埋め込み画像検出・数式フォント
        検出・クロップ画像生成を行う。Presenter から見た呼び出しパターンは
        ``await model.extract_content(...)`` で統一される。

        Args:
            page_number: 0-indexed のページ番号。
            rect: 抽出対象の矩形座標 (PDF point 単位)。
            dpi: クロップ画像生成時のレンダリング解像度。
            force_include_image: True ならば検出結果に関わらず常にクロップ画像を付与。
            auto_detect_embedded_images: True ならば埋め込み画像の自動検出を行う。
            auto_detect_math_fonts: True ならば数式フォントの自動検出を行う。

        Returns:
            マルチモーダルコンテンツを含む SelectionContent。
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._extract_content_sync,
            page_number,
            rect,
            dpi,
            force_include_image,
            auto_detect_embedded_images,
            auto_detect_math_fonts,
        )

    async def extract_all_text(self) -> str:
        """文書全体のテキストを抽出し、ページ区切り付きで返す。

        各ページのテキストを ``--- Page N ---`` の区切り行で連結する。
        ページ番号は 1-indexed で表示する。
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._extract_all_text_sync,
        )

    def close_document(self) -> None:
        """開いている文書を閉じ、内部状態とキャッシュをクリアする。"""
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None
        self._document_info = None
        self._page_cache.clear()

    def get_document_info(self) -> DocumentInfo | None:
        """現在開いている文書のメタデータを返す。未オープンなら None。"""
        return self._document_info

    # --- Private synchronous methods (executor 内で実行) ---

    def _open_document_sync(
        self, file_path: str, password: str | None
    ) -> DocumentInfo:
        """fitz.open による同期的なファイルオープン処理。

        executor 内で呼ばれるため、ここではブロッキング呼び出しを使って良い。
        """
        # 既に開いている文書があればクローズする。
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None
            self._document_info = None
            self._page_cache.clear()

        path = Path(file_path)
        if not path.exists():
            raise DocumentOpenError(f"File not found: {file_path}")

        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise DocumentOpenError(
                f"Failed to open '{file_path}': {e}"
            ) from e

        # パスワード保護の処理
        if doc.needs_pass:
            if password is None:
                doc.close()
                raise DocumentPasswordRequired(file_path)
            if not doc.authenticate(password):
                doc.close()
                raise DocumentOpenError(
                    f"Invalid password for '{file_path}'"
                )

        self._doc = doc

        # メタデータ取得
        title = doc.metadata.get("title") or None
        if title is not None:
            title = title.strip() or None

        # 目次 (ToC) 抽出: fitz は [level, title, page(1-indexed)] を返す。
        # page_number を 0-indexed に変換して ToCEntry に格納する。
        toc_entries: list[ToCEntry] = []
        for entry in doc.get_toc():
            level, toc_title, page_1indexed = entry[0], entry[1], entry[2]
            toc_entries.append(
                ToCEntry(
                    title=toc_title,
                    page_number=max(page_1indexed - 1, 0),
                    level=level,
                )
            )

        # 各ページの PDF ポイントサイズを収集する。レンダリング不要で即座に取得でき、
        # Presenter が DPI 換算してページごとに正確なプレースホルダーを生成できる。
        page_sizes: list[tuple[float, float]] = []
        for i in range(doc.page_count):
            page = doc[i]
            page_sizes.append((page.rect.width, page.rect.height))

        self._document_info = DocumentInfo(
            file_path=file_path,
            total_pages=doc.page_count,
            title=title,
            toc=toc_entries,
            page_sizes=page_sizes,
        )
        return self._document_info

    def _render_page_sync(self, page_number: int, dpi: int) -> PageData:
        """単一ページの同期レンダリング。executor 内で呼ばれる。"""
        if self._doc is None:
            raise DocumentRenderError(
                page_number, "No document is open"
            )
        if page_number < 0 or page_number >= self._doc.page_count:
            raise DocumentRenderError(
                page_number,
                f"Page {page_number} out of range [0, {self._doc.page_count})",
            )

        page = self._doc[page_number]
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # フォーマットに応じた画像バイト列生成
        if self._config.render_format == "jpeg":
            # Pillow 経由で JPEG エンコードする。
            # pix.tobytes() は PNG/PNM のみ対応のため、
            # Pixmap → PIL Image → JPEG bytes の変換を行う。
            pil_image = Image.frombytes(
                "RGB", (pix.width, pix.height), pix.samples
            )
            buf = io.BytesIO()
            pil_image.save(
                buf, format="JPEG", quality=self._config.jpeg_quality
            )
            image_data = buf.getvalue()
        else:
            image_data = pix.tobytes(output="png")

        return PageData(
            page_number=page_number,
            image_data=image_data,
            width=pix.width,
            height=pix.height,
        )

    def _extract_text_sync(
        self, page_number: int, rect: RectCoords
    ) -> str:
        """指定矩形領域内のテキストを同期抽出する。executor 内で呼ばれる。"""
        if self._doc is None:
            return ""
        if page_number < 0 or page_number >= self._doc.page_count:
            return ""
        page = self._doc[page_number]
        clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
        return page.get_text("text", clip=clip)

    def _extract_all_text_sync(self) -> str:
        """全ページのテキストを区切り付きで同期抽出する。executor 内で呼ばれる。"""
        if self._doc is None:
            return ""
        parts: list[str] = []
        for i in range(self._doc.page_count):
            page = self._doc[i]
            text = page.get_text("text")
            parts.append(f"--- Page {i + 1} ---\n{text}")
        return "\n".join(parts)

    def _extract_content_sync(
        self,
        page_number: int,
        rect: RectCoords,
        dpi: int,
        force_include_image: bool,
        auto_detect_embedded_images: bool,
        auto_detect_math_fonts: bool,
    ) -> SelectionContent:
        """マルチモーダルコンテンツ抽出の同期実装。executor 内で呼ばれる。

        以下の順序で処理する:
        1. テキスト抽出（常に実行）
        2. 埋め込み画像検出（auto_detect_embedded_images が True の場合）
        3. 数式フォント検出（auto_detect_math_fonts が True の場合）
        4. クロップ画像生成（force or 検出ヒット時）
        5. 埋め込み画像の個別抽出（画像検出時）
        """
        if self._doc is None or page_number < 0 or page_number >= self._doc.page_count:
            return SelectionContent(
                page_number=page_number,
                rect=rect,
                extracted_text="",
            )

        page = self._doc[page_number]
        clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)

        # 1. テキスト抽出（常に実行）
        extracted_text = page.get_text("text", clip=clip)

        # 2. 埋め込み画像検出
        has_images = False
        image_xrefs: list[int] = []
        if auto_detect_embedded_images:
            has_images, image_xrefs = self._check_embedded_images(page, clip)

        # 3. 数式フォント検出
        has_math = False
        if auto_detect_math_fonts:
            has_math = self._has_math_content(page, clip)

        # 判定ロジック: 検出理由の決定
        detection_reason: str | None = None
        if has_images:
            detection_reason = "embedded_image"
        elif has_math:
            detection_reason = "math_font"

        # 4. クロップ画像生成
        cropped_image: bytes | None = None
        if force_include_image or has_images or has_math:
            cropped_image = self._crop_page_image(page, clip, dpi)

        # 5. 埋め込み画像の個別抽出
        embedded_images: list[bytes] = []
        if has_images and image_xrefs:
            embedded_images = self._extract_embedded_images(image_xrefs)

        return SelectionContent(
            page_number=page_number,
            rect=rect,
            extracted_text=extracted_text,
            cropped_image=cropped_image,
            embedded_images=embedded_images,
            detection_reason=detection_reason,
        )

    def _check_embedded_images(
        self, page: fitz.Page, clip: fitz.Rect
    ) -> tuple[bool, list[int]]:
        """選択矩形内に埋め込み画像があるか検出する。

        page.get_images(full=True) で画像オブジェクト一覧を取得し、
        各画像の表示位置が選択矩形と交差するかを判定する。

        Returns:
            (画像が見つかったか, 交差した画像の xref リスト)
        """
        found_xrefs: list[int] = []
        try:
            images = page.get_images(full=True)
        except Exception:
            return False, []

        for img_info in images:
            xref = img_info[0]
            try:
                # 同じ xref が複数の矩形に配置されうるため全矩形をチェックする
                img_rects = page.get_image_rects(xref)
                for img_rect in img_rects:
                    if img_rect.intersects(clip):
                        found_xrefs.append(xref)
                        break  # 同じ xref は 1 回だけ記録
            except Exception:
                continue

        return bool(found_xrefs), found_xrefs

    def _has_math_content(self, page: fitz.Page, clip: fitz.Rect) -> bool:
        """選択矩形内に数式コンテンツが含まれるかを検出する。

        以下の 2 つの基準で判定する:
        - 数式フォント名 (CMR, CMMI, CMSY, CMEX, Math, Symbol, STIX 等) の検出
        - 数学記号の Unicode 範囲
          (Mathematical Operators U+2200–U+22FF, Greek U+0391–U+03C9 等)

        フォント名検出のみでは Tagged PDF の ActualText を見逃す可能性があるため、
        Unicode 範囲も併せてチェックする。
        """
        # 数式フォント名の部分一致パターン（小文字で比較）
        _MATH_FONT_PATTERNS = (
            "cmmi", "cmsy", "cmr", "cmex",
            "math", "symbol", "stix",
            "cambria math", "asana", "xits",
        )

        try:
            blocks = page.get_text("dict", clip=clip, flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except Exception:
            return False

        for block in blocks.get("blocks", []):
            if block.get("type") != 0:  # テキストブロックのみ
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    # フォント名チェック
                    font_name = span.get("font", "").lower()
                    if any(pat in font_name for pat in _MATH_FONT_PATTERNS):
                        return True

                    # Unicode 範囲チェック
                    text = span.get("text", "")
                    for ch in text:
                        cp = ord(ch)
                        if (
                            0x2200 <= cp <= 0x22FF  # Mathematical Operators
                            or 0x2100 <= cp <= 0x214F  # Letterlike Symbols
                            or 0x2190 <= cp <= 0x21FF  # Arrows
                            or 0x27C0 <= cp <= 0x27EF  # Misc Mathematical Symbols-A
                            or 0x2980 <= cp <= 0x29FF  # Misc Mathematical Symbols-B
                            or 0x2A00 <= cp <= 0x2AFF  # Supplemental Mathematical Operators
                            or 0x0391 <= cp <= 0x03C9  # Greek Letters
                            or 0x1D400 <= cp <= 0x1D7FF  # Mathematical Alphanumeric Symbols
                        ):
                            return True

        return False

    def _crop_page_image(
        self, page: fitz.Page, clip: fitz.Rect, dpi: int
    ) -> bytes:
        """ページの指定矩形をクロップした PNG バイト列を返す。

        get_pixmap(clip=...) を使うことで、矩形部分だけをレンダリングする。
        全ページレンダリングに比べてメモリ消費・処理時間が小さい。
        """
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        return pix.tobytes(output="png")

    def _extract_embedded_images(self, xrefs: list[int]) -> list[bytes]:
        """xref リストに対応する埋め込み画像をバイト列として個別抽出する。

        抽出に失敗した画像はスキップし、取得できたものだけを返す。
        """
        if self._doc is None:
            return []
        result: list[bytes] = []
        for xref in xrefs:
            try:
                img_data = self._doc.extract_image(xref)
                if img_data and img_data.get("image"):
                    result.append(img_data["image"])
            except Exception:
                continue
        return result

    # --- Private helpers ---

    def _get_page_dimensions(
        self, page_number: int, dpi: int
    ) -> tuple[int, int]:
        """文書から指定ページのピクセルサイズを計算する。

        キャッシュヒット時にレンダリングせずにサイズだけ返すために使う。
        """
        if self._doc is None:
            return self._get_page_dimensions_fallback(dpi)
        if page_number < 0 or page_number >= self._doc.page_count:
            return self._get_page_dimensions_fallback(dpi)
        page = self._doc[page_number]
        scale = dpi / 72.0
        return (
            int(page.rect.width * scale),
            int(page.rect.height * scale),
        )

    @staticmethod
    def _get_page_dimensions_fallback(dpi: int) -> tuple[int, int]:
        """文書情報が取得できない場合の US Letter サイズのフォールバック。"""
        return (int(612 * dpi / 72), int(792 * dpi / 72))
