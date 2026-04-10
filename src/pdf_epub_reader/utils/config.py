"""アプリケーション全体のデフォルト設定値を定義するモジュール。

秘匿情報は含めず、レイアウトやデフォルト倍率など
コード上で共有するパラメータをここに集約する。
実行時にユーザーが変更する設定は AppConfig dataclass で管理し、
JSON ファイルに永続化する。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import platformdirs

logger = logging.getLogger(__name__)

# --- アプリケーション識別 ---
_APP_NAME = "pdf-epub-reader"
_APP_AUTHOR = "pdf-epub-reader"

# --- ウィンドウ ---
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 800
SPLITTER_RATIO = (70, 30)

# --- レンダリング ---
DEFAULT_DPI = 144

# --- レンダリング画像フォーマット ---
DEFAULT_RENDER_FORMAT: Literal["png", "jpeg"] = "png"
DEFAULT_JPEG_QUALITY = 85

# --- ページキャッシュ ---
PAGE_CACHE_MAX_SIZE = 50

# --- ズーム ---
ZOOM_MIN = 0.25
ZOOM_MAX = 4.0
ZOOM_STEP = 0.25

# --- ドキュメント表示 ---
PAGE_GAP = 10               # ページ間の余白 (ピクセル)
VIEWPORT_BUFFER_PAGES = 2   # ビューポート前後に先読みするページ数

# --- 最近のファイル ---
MAX_RECENT_FILES = 10

# --- 環境変数名 ---
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"


# ---------------------------------------------------------------------------
# AppConfig: ユーザーが変更可能な設定をまとめた dataclass
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    """ユーザーが GUI やファイル編集で変更可能な設定値をまとめたクラス。

    Phase 3 ではコード経由でのみ変更可能とし、Phase 3.5 で
    設定ダイアログ UI を追加してユーザーが直接操作できるようにする。

    各フィールドのデフォルト値はモジュール冒頭の定数と一致させている。
    JSON 永続化時はこの dataclass を丸ごとシリアライズする。
    """

    # レンダリング設定
    render_format: Literal["png", "jpeg"] = DEFAULT_RENDER_FORMAT
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    default_dpi: int = DEFAULT_DPI

    # キャッシュ設定
    page_cache_max_size: int = PAGE_CACHE_MAX_SIZE

    # ウィンドウ設定
    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT

    # 最近のファイル
    recent_files: list[str] = field(default_factory=list)

    # Phase 4: 選択領域の自動検出設定
    # 矩形選択時に埋め込み画像やLaTeX数式フォントを自動検出し、
    # クロップ画像を Gemini Vision に送信するかを制御する。
    auto_detect_embedded_images: bool = True
    auto_detect_math_fonts: bool = True


def _get_config_path() -> Path:
    """設定ファイルの保存先パスを返す。

    platformdirs を使ってOS標準のユーザー設定ディレクトリを取得する。
    - Windows: %LOCALAPPDATA%/pdf-epub-reader/config.json
    - macOS:   ~/Library/Application Support/pdf-epub-reader/config.json
    - Linux:   ~/.config/pdf-epub-reader/config.json
    """
    config_dir = Path(platformdirs.user_config_dir(_APP_NAME, _APP_AUTHOR))
    return config_dir / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    """JSON ファイルから AppConfig を読み込む。

    ファイルが存在しない場合やパースに失敗した場合はデフォルト値を返す。
    設定ファイルの破損でアプリが起動できなくなることを防ぐための安全策。

    Args:
        path: 設定ファイルパス。None ならOS標準の場所を使う。
              テスト時に一時ディレクトリを指定できるようにするための引数。
    """
    config_path = path or _get_config_path()
    if not config_path.exists():
        return AppConfig()

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        # JSON に含まれないフィールドはデフォルト値で補完されるため、
        # 設定項目が増えても古い設定ファイルがそのまま使える。
        known_fields = {f.name for f in AppConfig.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return AppConfig(**filtered)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.warning("設定ファイルの読み込みに失敗しました: %s — デフォルト値を使用します", e)
        return AppConfig()


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """AppConfig を JSON ファイルに保存する。

    ディレクトリが存在しない場合は自動作成する。
    書き込みに失敗した場合はログ出力のみで例外を伝播させない。
    設定保存の失敗でアプリ全体がクラッシュするのを防ぐため。

    Args:
        config: 保存する設定。
        path: 保存先パス。None ならOS標準の場所を使う。
    """
    config_path = path or _get_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("設定ファイルの保存に失敗しました: %s", e)
