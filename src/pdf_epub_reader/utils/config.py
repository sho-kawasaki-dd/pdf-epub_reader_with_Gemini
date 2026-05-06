"""アプリケーション全体のデフォルト設定値を定義するモジュール。

秘匿情報は含めず、レイアウトやデフォルト倍率など
コード上で共有するパラメータをここに集約する。
実行時にユーザーが変更する設定は AppConfig dataclass で管理し、
JSON ファイルに永続化する。
"""

from __future__ import annotations

import json
import locale
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import platformdirs

logger = logging.getLogger(__name__)

# --- アプリケーション識別 ---
_APP_NAME = "gem-read"
_APP_AUTHOR = "gem-read"

# --- ウィンドウ ---
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 800
SPLITTER_RATIO = (70, 30)
BOOKMARK_PANEL_WIDTH = 200

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

# --- AI デフォルト設定 ---
DEFAULT_GEMINI_MODEL = ""
DEFAULT_OUTPUT_LANGUAGE = "日本語"
DEFAULT_UI_LANGUAGE: Literal["ja", "en"] = "en"
DEFAULT_TRANSLATION_PROMPT = (
    "You are a translator of academic documents. Translate the given text into {output_language}.\n"
    "- Write mathematical expressions using LaTeX notation ($...$ or $$...$$).\n"
    "- Write chemical formulas using the LaTeX \\ce{{}} command.\n"
    "- Output the response in Markdown format."
)

# 解説付き翻訳モード時にシステムプロンプトへ追記する指示。
# AppConfig フィールドには追加せず、設定ダイアログの対象外とする。
DEFAULT_EXPLANATION_ADDENDUM = (
    "\n翻訳の後に「---」区切り線を入れ、その下に専門用語・概念・背景知識の解説を付けてください。"
)

# --- Markdown export デフォルト設定 ---
DEFAULT_EXPORT_FOLDER = ""
DEFAULT_EXPORT_INCLUDE_EXPLANATION = True
DEFAULT_EXPORT_INCLUDE_SELECTION_LIST = True
DEFAULT_EXPORT_INCLUDE_RAW_RESPONSE = False
DEFAULT_EXPORT_INCLUDE_DOCUMENT_METADATA = False
DEFAULT_EXPORT_INCLUDE_USAGE_METRICS = False
DEFAULT_EXPORT_INCLUDE_YAML_FRONTMATTER = False

# --- Plotly visualization デフォルト設定 ---
DEFAULT_PLOTLY_VISUALIZATION_MODE: Literal["off", "json", "python"] = "off"
DEFAULT_PLOTLY_MULTI_SPEC_MODE: Literal["prompt", "first_only", "all_tabs"] = (
    "all_tabs"
)
DEFAULT_PLOTLY_SANDBOX_TIMEOUT_S = 10.0
PLOTLY_SANDBOX_TIMEOUT_MIN = 1.0
PLOTLY_SANDBOX_TIMEOUT_MAX = 120.0

# --- バリデーション定数 (Phase 5: 設定ダイアログ) ---
DPI_MIN = 72
DPI_MAX = 600
JPEG_QUALITY_MIN = 1
JPEG_QUALITY_MAX = 100
PAGE_CACHE_MIN = 1
PAGE_CACHE_MAX = 500

# --- Context Cache 設定 (Phase 7) ---
DEFAULT_CACHE_TTL_MINUTES = 60
CACHE_TTL_MIN = 1
CACHE_TTL_MAX = 1440

UiLanguage = Literal["ja", "en"]
PlotlyVisualizationMode = Literal["off", "json", "python"]
PlotlyMultiSpecMode = Literal["prompt", "first_only", "all_tabs"]


def _get_system_locale_name() -> str | None:
    """現在の OS ロケール名を返す。"""
    try:
        language_code, _ = locale.getlocale()
    except (TypeError, ValueError):
        return None
    return language_code


def normalize_ui_language(
    value: str | None,
    *,
    fallback: UiLanguage = DEFAULT_UI_LANGUAGE,
) -> UiLanguage:
    """UI 言語コードを内部表現の ja / en に正規化する。"""
    if not value:
        return fallback

    normalized = value.strip().replace("_", "-").lower()
    if normalized.startswith("ja"):
        return "ja"
    if normalized.startswith("en"):
        return "en"
    return fallback


def normalize_model_name(value: str | None) -> str:
    """AI モデル名の未設定値を空文字に正規化する。"""
    if value is None:
        return ""
    return value.strip()


def normalize_export_folder(value: str | None) -> str:
    """Markdown export の保存先フォルダを空文字またはトリム済み文字列に正規化する。"""
    if value is None:
        return ""
    return value.strip()


def normalize_plotly_multi_spec_mode(
    value: str | None,
) -> PlotlyMultiSpecMode:
    """複数 Plotly spec の扱い設定を既知の値へ正規化する。"""
    if value in {"prompt", "first_only", "all_tabs"}:
        return value
    return DEFAULT_PLOTLY_MULTI_SPEC_MODE


def normalize_plotly_visualization_mode(
    value: str | bool | None,
) -> PlotlyVisualizationMode:
    """Plotly 可視化モードを既知の値へ正規化する。"""
    if value is True:
        # 旧 bool 設定との後方互換。True は従来の JSON 表示に相当する。
        return "json"
    if value in {"json", "python"}:
        return value
    return "off"


def normalize_plotly_sandbox_timeout_s(value: float | int | None) -> float:
    """Sandbox 実行 timeout を許容範囲へ clamp する。"""
    if value is None:
        return DEFAULT_PLOTLY_SANDBOX_TIMEOUT_S
    try:
        timeout_s = float(value)
    except (TypeError, ValueError):
        return DEFAULT_PLOTLY_SANDBOX_TIMEOUT_S
    if timeout_s < PLOTLY_SANDBOX_TIMEOUT_MIN:
        return PLOTLY_SANDBOX_TIMEOUT_MIN
    if timeout_s > PLOTLY_SANDBOX_TIMEOUT_MAX:
        return PLOTLY_SANDBOX_TIMEOUT_MAX
    return timeout_s


def normalize_plotly_sandbox_log_dir(value: str | None) -> str | None:
    """Sandbox stderr ログ保存先を空文字/None なら未設定として扱う。"""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def get_default_ui_language(locale_name: str | None = None) -> UiLanguage:
    """既定の UI 言語を OS ロケールから決定する。"""
    return normalize_ui_language(
        locale_name or _get_system_locale_name(),
        fallback=DEFAULT_UI_LANGUAGE,
    )


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
    ui_language: UiLanguage = field(default_factory=get_default_ui_language)

    # 最近のファイル
    recent_files: list[str] = field(default_factory=list)

    # 縮小表示時に Pillow LANCZOS でリサイズして文字のジャギーを抑える。
    # CPU 負荷が気になる場合はユーザーが OFF にできる。
    high_quality_downscale: bool = True

    # Phase 4: 選択領域の自動検出設定
    # 矩形選択時に埋め込み画像やLaTeX数式フォントを自動検出し、
    # クロップ画像を Gemini Vision に送信するかを制御する。
    auto_detect_embedded_images: bool = True
    auto_detect_math_fonts: bool = True

    # Phase 6: AI 設定
    # Gemini API で使用するモデル名・選択済みモデル一覧・
    # システムプロンプト・出力言語を永続化する。
    gemini_model_name: str = DEFAULT_GEMINI_MODEL
    selected_models: list[str] = field(
        default_factory=list
    )
    system_prompt_translation: str = DEFAULT_TRANSLATION_PROMPT
    output_language: str = DEFAULT_OUTPUT_LANGUAGE

    # Phase 7: Context Cache 設定
    # サーバー側キャッシュの有効期間（分）。設定ダイアログの AI Models タブで変更可能。
    cache_ttl_minutes: int = DEFAULT_CACHE_TTL_MINUTES

    # Phase 8: Markdown export 設定
    export_folder: str = DEFAULT_EXPORT_FOLDER
    export_include_explanation: bool = DEFAULT_EXPORT_INCLUDE_EXPLANATION
    export_include_selection_list: bool = DEFAULT_EXPORT_INCLUDE_SELECTION_LIST
    export_include_raw_response: bool = DEFAULT_EXPORT_INCLUDE_RAW_RESPONSE
    export_include_document_metadata: bool = (
        DEFAULT_EXPORT_INCLUDE_DOCUMENT_METADATA
    )
    export_include_usage_metrics: bool = DEFAULT_EXPORT_INCLUDE_USAGE_METRICS
    export_include_yaml_frontmatter: bool = (
        DEFAULT_EXPORT_INCLUDE_YAML_FRONTMATTER
    )

    # Phase 9: Plotly visualization 設定
    # モード自体はサイドパネルで切り替えるが、永続化は config が担う。
    plotly_visualization_mode: PlotlyVisualizationMode = (
        DEFAULT_PLOTLY_VISUALIZATION_MODE
    )
    # 複数 spec を返した場合に選択ダイアログを出すか、先頭だけ使うかを制御する。
    plotly_multi_spec_mode: PlotlyMultiSpecMode = (
        DEFAULT_PLOTLY_MULTI_SPEC_MODE
    )
    # Python sandbox 実行の timeout と stderr ログ保存先。
    plotly_sandbox_timeout_s: float = DEFAULT_PLOTLY_SANDBOX_TIMEOUT_S
    plotly_sandbox_log_dir: str | None = None

    def __post_init__(self) -> None:
        self.ui_language = normalize_ui_language(self.ui_language)
        self.gemini_model_name = normalize_model_name(self.gemini_model_name)
        self.export_folder = normalize_export_folder(self.export_folder)
        self.plotly_visualization_mode = normalize_plotly_visualization_mode(
            self.plotly_visualization_mode
        )
        self.plotly_multi_spec_mode = normalize_plotly_multi_spec_mode(
            self.plotly_multi_spec_mode
        )
        self.plotly_sandbox_timeout_s = normalize_plotly_sandbox_timeout_s(
            self.plotly_sandbox_timeout_s
        )
        self.plotly_sandbox_log_dir = normalize_plotly_sandbox_log_dir(
            self.plotly_sandbox_log_dir
        )
        normalized_models: list[str] = []
        for name in self.selected_models:
            normalized = normalize_model_name(name)
            if normalized and normalized not in normalized_models:
                normalized_models.append(normalized)
        self.selected_models = normalized_models


def _get_config_path() -> Path:
    """設定ファイルの保存先パスを返す。

    platformdirs を使ってOS標準のユーザー設定ディレクトリを取得する。
    - Windows: %LOCALAPPDATA%/gem-read/config.json
    - macOS:   ~/Library/Application Support/gem-read/config.json
    - Linux:   ~/.config/gem-read/config.json
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
        if (
            "plotly_visualization_mode" not in data
            and "plotly_visualization_enabled" in data
        ):
            # Phase 1 の bool 設定を Phase 2 の 3 状態モードへ移行する。
            data["plotly_visualization_mode"] = normalize_plotly_visualization_mode(
                data.get("plotly_visualization_enabled")
            )
        # JSON に含まれないフィールドはデフォルト値で補完されるため、
        # 設定項目が増えても古い設定ファイルがそのまま使える。
        known_fields = {f.name for f in AppConfig.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        filtered.setdefault("ui_language", get_default_ui_language())
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
        payload = asdict(config)
        payload["ui_language"] = normalize_ui_language(payload.get("ui_language"))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("設定ファイルの保存に失敗しました: %s", e)
