"""Qt イベントループと asyncio を qasync で統合するモジュール。

本アプリは Qt のメインスレッドで asyncio の await を使いたいため、
qasync を用いて両者のイベントループを一本化する。
この橋渡しコードは infrastructure 層に隔離し、
Model / Presenter が Qt に依存しないアーキテクチャを維持する。
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable

from PySide6.QtWidgets import QApplication
import qasync


def run_app(
    app_main: Callable[[], Awaitable[None]],
    *,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """QApplication と asyncio イベントループを統合してアプリを起動する。

    Parameters
    ----------
    app_main:
        非同期コンテキスト内で MVP コンポーネントを組み立てるコルーチン関数。
    on_shutdown:
        アプリ終了時に呼ばれる非同期コールバック。
        キャッシュの自動破棄など、終了前のクリーンアップに使用する。
        例外が発生しても他のクリーンアップ処理を妨げない。

    この関数は以下の手順で動作する:
    1. QApplication を生成（既存インスタンスがあれば再利用）
    2. Fusion スタイルを適用
    3. qasync で Qt と asyncio のイベントループを統合
    4. app_main コルーチンをタスクとして投入
    5. run_forever() で統合ループを回す
    6. 終了後にクリーンアップ
    """
    # テスト時など QApplication が既に存在する場合は重複生成を防ぐ。
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    asyncio.ensure_future(app_main())

    try:
        loop.run_forever()
    finally:
        if on_shutdown is not None:
            try:
                loop.run_until_complete(on_shutdown())
            except Exception:  # noqa: BLE001
                pass  # シャットダウンエラーでもクリーンアップを続行する
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
