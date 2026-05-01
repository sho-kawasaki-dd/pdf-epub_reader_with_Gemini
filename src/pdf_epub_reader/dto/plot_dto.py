"""Plotly 可視化で使う DTO。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PlotlySpec:
    """LLM 応答から抽出した Plotly spec の生データ。"""

    index: int
    language: Literal["json", "python"]
    source_text: str
    title: str | None = None


@dataclass(frozen=True)
class PlotlyRenderRequest:
    """MainPresenter へ渡す Plotly 描画要求。"""

    specs: list[PlotlySpec]
    origin_mode: Literal["json", "python"]