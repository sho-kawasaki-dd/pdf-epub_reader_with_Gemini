"""View 層の契約を定義する Protocol 群。

このプロジェクトでは Passive View を採用しているため、
Presenter は View の「具体的な PySide6 実装」ではなく、
ここで定義した最小限の契約だけを知る。

なぜ Protocol を使うのか:
- 継承関係を強制せず、PySide6 実装も Mock 実装も同じ契約で扱える
- テスト時に GUI を起動せず Presenter の振る舞いを検証できる
- 依存の向きを Presenter → View interface に固定できる
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from pdf_epub_reader.dto import PageData, RectCoords


@runtime_checkable
class IMainView(Protocol):
    """メイン画面が満たすべき契約。

    ここには「Presenter から命令される操作」と
    「View がユーザー操作を通知するためのコールバック登録」を置く。
    逆に、文書解析や AI 呼び出しのような業務ロジックは含めない。
    """

    # --- Display commands (Presenter → View) ---
    # Presenter が View に対して「何を表示するか」だけを命令するための API。
    # どう描画するかは View 実装側の責務であり、Protocol では扱わない。

    def display_pages(self, pages: list[PageData]) -> None: ...
    def scroll_to_page(self, page_number: int) -> None: ...
    def set_zoom_level(self, level: float) -> None: ...
    def show_selection_highlight(
        self, page_number: int, rect: RectCoords
    ) -> None: ...
    def clear_selection(self) -> None: ...
    def set_window_title(self, title: str) -> None: ...
    def show_status_message(self, message: str) -> None: ...
    def update_recent_files(self, files: list[str]) -> None: ...

    # --- Callback registration (View → Presenter) ---
    # View は Presenter を直接知らないため、イベント発生時に呼ぶ関数だけを
    # 事前登録してもらう。この形にすると Passive View を保ちやすい。

    def set_on_file_open_requested(
        self, cb: Callable[[], None]
    ) -> None: ...
    def set_on_file_dropped(self, cb: Callable[[str], None]) -> None: ...
    def set_on_recent_file_selected(
        self, cb: Callable[[str], None]
    ) -> None: ...
    def set_on_area_selected(
        self, cb: Callable[[int, RectCoords], None]
    ) -> None: ...
    def set_on_zoom_changed(
        self, cb: Callable[[float], None]
    ) -> None: ...
    def set_on_cache_management_requested(
        self, cb: Callable[[], None]
    ) -> None: ...


@runtime_checkable
class ISidePanelView(Protocol):
    """AI サイドパネルが満たすべき契約。

    サイドパネルは「選択テキストの表示」「解析結果の表示」
    「ユーザーが押したボタンの通知」に責務を絞る。
    解析の組み立てや例外処理は Presenter 側で行う。
    """

    # --- Display commands (Presenter → View) ---

    def set_selected_text(self, text: str) -> None: ...
    def update_result_text(self, text: str) -> None: ...
    def show_loading(self, loading: bool) -> None: ...
    def update_cache_status_brief(self, text: str) -> None: ...
    def set_active_tab(self, mode: str) -> None: ...

    # --- Callback registration (View → Presenter) ---

    def set_on_translate_requested(
        self, cb: Callable[[bool], None]
    ) -> None: ...
    def set_on_custom_prompt_submitted(
        self, cb: Callable[[str], None]
    ) -> None: ...
    def set_on_tab_changed(
        self, cb: Callable[[str], None]
    ) -> None: ...
