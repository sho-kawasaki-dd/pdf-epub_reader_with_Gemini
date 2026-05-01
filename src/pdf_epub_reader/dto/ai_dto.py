"""AI 解析まわりでやり取りするデータ型を定義するモジュール。

AI リクエストは入力値が増えやすく、関数引数を増やしていくと
呼び出し側の意図が読みにくくなる。そのため、解析要求と結果を
明示的な dataclass にまとめて扱う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class AnalysisMode(Enum):
    """AI 解析の実行モード。

    文字列のベタ書きを避けて Enum にしておくことで、
    Presenter 側の分岐やテストでタイプミスを防ぎやすくする。
    """

    TRANSLATION = "translation"
    CUSTOM_PROMPT = "custom_prompt"


@dataclass(frozen=True)
class AnalysisRequest:
    """AI 解析に必要な入力値をひとまとめにした要求オブジェクト。

    `mode` によって有効なフィールドが変わる。
    - `TRANSLATION`: `include_explanation` を参照
    - `CUSTOM_PROMPT`: `custom_prompt` を参照

    この形にしておくと、後から「対象言語」「温度」「モデル名」などを
    追加してもメソッドシグネチャを大きく崩さずに拡張できる。
    """

    text: str
    mode: AnalysisMode
    include_explanation: bool = False
    custom_prompt: str | None = None
    system_prompt: str | None = None
    images: list[bytes] = field(default_factory=list)
    model_name: str | None = None
    cache_name: str | None = None
    # Phase 2: Plotly 可視化要求。
    # `off` は抽出自体を行わず、`json` は fenced JSON を優先、
    # `python` は fenced Python を優先し、無ければ JSON fallback を許可する。
    request_plotly_mode: Literal["off", "json", "python"] = "off"


@dataclass(frozen=True)
class AnalysisUsage:
    """Gemini usage metadata normalized for UI and API consumers."""

    prompt_token_count: int | None = None
    cached_content_token_count: int | None = None
    candidates_token_count: int | None = None
    total_token_count: int | None = None


@dataclass(frozen=True)
class AnalysisResult:
    """AI 解析の結果。

    `translated_text` や `explanation` を分離しているのは、
    View 側で表示方法を切り替えやすくするため。
    一方 `raw_response` は、整形前の結果を保持しておく退避先であり、
    モードに応じて最低限の表示内容を失わないために残している。
    """

    translated_text: str | None = None
    explanation: str | None = None
    raw_response: str = ""
    usage: AnalysisUsage | None = None
    cache_request_attempted: bool = False
    cache_request_failed: bool = False
    cache_fallback_reason: str | None = None


@dataclass(frozen=True)
class ModelInfo:
    """利用可能な AI モデルの情報。

    設定ダイアログでモデル一覧を表示する際や、
    サイドパネルのプルダウンで選択肢を作る際に使用する。
    """

    model_id: str
    display_name: str


@dataclass(frozen=True)
class CacheStatus:
    """Context Cache の状態を表すデータ。

    Phase 1 では簡易表示しか扱わないが、TTL やトークン数まで保持しておくことで
    Phase 5 で詳細ダイアログを作るときに型を再設計せずに済む。

    Phase 7 で ``model_name``（キャッシュ紐付きモデル名）と
    ``expire_time``（ISO 形式の有効期限）を追加。
    キャッシュ管理ダイアログでの詳細表示やモデル一致判定に使用する。
    """

    is_active: bool = False
    ttl_seconds: int | None = None
    token_count: int | None = None
    cache_name: str | None = None
    display_name: str | None = None
    model_name: str | None = None
    expire_time: str | None = None
