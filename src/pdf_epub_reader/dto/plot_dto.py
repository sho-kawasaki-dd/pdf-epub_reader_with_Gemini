"""Plotly 可視化フローで受け渡す DTO。

Phase 1 では JSON fenced block の抽出・描画だけを扱い、Phase 2 で
Python sandbox 実行が加わった。両フェーズで同じ DTO を流用できるよう、
ここでは「抽出した生 spec」と「描画要求」を最小限の形で定義する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PlotlySpec:
    """LLM 応答から抽出した Plotly spec の生データ。

    `source_text` は parse 前の文字列をそのまま保持する。これにより、
    抽出 service は markdown 解析だけに責務を限定し、JSON 妥当性確認や
    Python sandbox 実行は後段の service に委ねられる。
    """

    index: int
    # Phase 1 は `json` のみ、Phase 2 で `python` が追加された。
    language: Literal["json", "python"]
    source_text: str
    title: str | None = None


@dataclass(frozen=True)
class PlotlyRenderRequest:
    """MainPresenter へ渡す Plotly 描画要求。

    `origin_mode` は「どの送信モードでこの応答を得たか」を保持する。
    Phase 2 では Python モード送信時に JSON fallback が起き得るため、
    表示メッセージを決める材料として必要になる。
    """

    specs: list[PlotlySpec]
    origin_mode: Literal["json", "python"]