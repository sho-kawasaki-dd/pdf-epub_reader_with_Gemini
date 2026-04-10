"""文書操作で層をまたいで受け渡すデータ型を定義するモジュール。

Phase 1 では Presenter と Model、Presenter と View の間で
PySide6 依存のオブジェクトを直接渡さない方針を取っている。
そのため、描画結果や選択情報はすべて Python 標準の型と
dataclass で表現し、このモジュールに集約する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class RectCoords:
    """PDF ページ上の矩形領域を表す座標。

    なぜ専用の型を作るのか:
    - `(x0, y0, x1, y1)` の裸のタプルだと意味が読み取りづらい
    - View と Model で同じ座標系を共有していることを明示したい
    - 後からバリデーションや補助メソッドを追加しやすい

    座標系は PDF のページ座標を採用する。
    これは画面のピクセル座標ではなく、72dpi 基準の point 単位であり、
    ズーム率や表示 DPI が変わっても Model 側の解釈がぶれにくい。
    """

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class PageData:
    """1ページ分の描画結果を表すデータ。

    `image_data` は View がそのまま描画に使えるバイト列を想定する。
    Presenter は画像の中身を解釈せず、Model が生成した結果を
    View に受け渡すだけに徹する。

    `width` と `height` を持たせている理由は、View が画像デコード前でも
    レイアウト計算やスクロール領域の見積もりを行えるようにするため。
    """

    page_number: int
    image_data: bytes
    width: int
    height: int


@dataclass(frozen=True)
class TextSelection:
    """矩形選択から抽出されたテキストを表すデータ。

    選択結果として文字列だけでなくページ番号と選択矩形を残すことで、
    後から「どこを選んだ結果なのか」を Presenter や View が参照できる。
    たとえば再ハイライト、再解析、履歴保存などに流用しやすくなる。
    """

    page_number: int
    rect: RectCoords
    extracted_text: str


@dataclass(frozen=True)
class ToCEntry:
    """目次 (Table of Contents) の 1 エントリを表すデータ。

    PDF/EPUB が持つ階層型の目次をフラットリストで表現する。
    `level` が階層の深さ（1 が最上位）を示し、View 側でインデント等の
    表示を調整できるようにする。

    PyMuPDF の ``doc.get_toc()`` が返す ``[level, title, page]`` を
    そのままマッピングする設計とした。page_number は 0-indexed に変換して格納する。
    """

    title: str
    page_number: int
    level: int


@dataclass(frozen=True)
class DocumentInfo:
    """開いた文書の基本メタデータ。

    ファイルパス・総ページ数・タイトルを切り出して保持することで、
    Presenter は Model の内部実装を知らずに UI 更新に必要な情報だけを扱える。
    `title` は PDF/EPUB に埋め込まれていない可能性があるため optional とする。
    `toc` は目次情報。目次を持たない文書では空リストとなる。
    `page_sizes` は各ページの PDF ポイント単位 (72dpi 基準) のサイズリスト。
    Presenter が DPI 換算してページごとに正確なプレースホルダーを生成するために使う。
    """

    file_path: str
    total_pages: int
    title: str | None = None
    toc: list[ToCEntry] = field(default_factory=list)
    page_sizes: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class SelectionContent:
    """矩形選択から抽出されたマルチモーダルコンテンツ。

    Phase 4 で導入。テキストだけでなく、数式や埋め込み画像を含む
    選択領域の全情報をまとめて Presenter に返すためのデータ型。

    既存の ``TextSelection`` はテキスト専用で後方互換のため残すが、
    新規のマルチモーダルフローではこちらを使用する。

    Attributes:
        page_number: 0-indexed のページ番号。
        rect: 選択矩形の PDF ポイント座標。
        extracted_text: 選択矩形内のプレーンテキスト（常に抽出される）。
        cropped_image: 選択矩形をページ画像からクロップした PNG バイト列。
            自動検出またはユーザートグルにより付与される。不要時は None。
        embedded_images: PDF 内にオブジェクトとして埋め込まれた画像を
            個別に抽出したバイト列リスト。埋め込み画像検出時のみ使用。
        detection_reason: 自動検出でクロップ画像を付与した理由。
            ``"embedded_image"`` / ``"math_font"`` / ``None``。
            ユーザーがトグルで強制した場合は ``None``。
    """

    page_number: int
    rect: RectCoords
    extracted_text: str
    cropped_image: bytes | None = None
    embedded_images: list[bytes] = field(default_factory=list)
    detection_reason: str | None = None
