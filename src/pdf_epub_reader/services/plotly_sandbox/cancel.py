"""Plotly sandbox 実行を停止するための軽量キャンセルトークン。"""

from __future__ import annotations

from threading import Event


class CancelToken:
    """sandbox 実行ヘルパ間で共有する thread-safe な停止フラグ。

    `threading.Event` を薄くラップし、呼び出し側は `cancel()`、監視側は
    `cancelled` または `wait()` を通して状態を確認する。
    """

    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelled(self) -> bool:
        """キャンセル要求が一度でも発行されていれば `True` を返す。"""
        return self._event.is_set()

    def cancel(self) -> None:
        """呼び出し側向けの意味づけされたエイリアス。"""
        self._event.set()

    def set(self) -> None:
        """`Event` 互換 API を保つための別名。"""
        self._event.set()

    def wait(self, timeout: float | None = None) -> bool:
        """指定時間だけ待機し、その間にキャンセルされたら `True` を返す。"""
        return self._event.wait(timeout)