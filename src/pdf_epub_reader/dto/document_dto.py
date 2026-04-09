"""文書操作で層をまたいで受け渡すデータ型を定義するモジュール。

Phase 1 では Presenter と Model、Presenter と View の間で
PySide6 依存のオブジェクトを直接渡さない方針を取っている。
そのため、描画結果や選択情報はすべて Python 標準の型と
dataclass で表現し、このモジュールに集約する。
"""

from __future__ import annotations

from dataclasses import dataclass


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
class DocumentInfo:
    """開いた文書の基本メタデータ。

    ファイルパス・総ページ数・タイトルを切り出して保持することで、
    Presenter は Model の内部実装を知らずに UI 更新に必要な情報だけを扱える。
    `title` は PDF/EPUB に埋め込まれていない可能性があるため optional とする。
    """

    file_path: str
    total_pages: int
    title: str | None = None
