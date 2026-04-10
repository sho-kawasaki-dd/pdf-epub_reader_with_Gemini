"""Presenter テスト用の Mock View 実装。

これらの Mock は PySide6 を起動せずに Presenter の振る舞いを検証するためのもの。
実際の描画は行わず、「どのメソッドがどの引数で呼ばれたか」だけを記録する。
"""

from __future__ import annotations

from collections.abc import Callable

from pdf_epub_reader.dto import PageData, RectCoords


class MockMainView:
    """IMainView を満たすテスト用ダミー実装。

    `calls` に呼び出し履歴を残すことで、Presenter が View に対して
    正しい命令を出したかを後から検証できる。
    """

    def __init__(self) -> None:
        # 各 View メソッドの呼び出し履歴を残し、テストで事後検証できるようにする。
        self.calls: list[tuple[str, tuple]] = []

        # show_password_dialog が返す固定値。テスト側で変更可能。
        # None を設定するとキャンセル動作を再現する。
        self._password_dialog_return: str | None = "test123"

        # Presenter から登録されたコールバックを保持する。
        # simulate_* メソッドはこれらを呼び出してユーザー操作を擬似再現する。
        self._on_file_open_requested: Callable[[], None] | None = None
        self._on_file_dropped: Callable[[str], None] | None = None
        self._on_recent_file_selected: Callable[[str], None] | None = None
        self._on_area_selected: Callable[[int, RectCoords], None] | None = None
        self._on_zoom_changed: Callable[[float], None] | None = None
        self._on_cache_management_requested: Callable[[], None] | None = None
        self._on_pages_needed: Callable[[list[int]], None] | None = None
        self._on_settings_requested: Callable[[], None] | None = None

        # get_current_page が返す固定値。テストで変更可能。
        self._current_page: int = 0

    # --- Display commands ---
    # 実 UI ではここで描画や画面更新が行われるが、Mock では記録だけを行う。

    def display_pages(self, pages: list[PageData]) -> None:
        self.calls.append(("display_pages", (pages,)))

    def scroll_to_page(self, page_number: int) -> None:
        self.calls.append(("scroll_to_page", (page_number,)))

    def set_zoom_level(self, level: float) -> None:
        self.calls.append(("set_zoom_level", (level,)))

    def show_selection_highlight(
        self, page_number: int, rect: RectCoords
    ) -> None:
        self.calls.append(("show_selection_highlight", (page_number, rect)))

    def clear_selection(self) -> None:
        self.calls.append(("clear_selection", ()))

    def set_window_title(self, title: str) -> None:
        self.calls.append(("set_window_title", (title,)))

    def show_status_message(self, message: str) -> None:
        self.calls.append(("show_status_message", (message,)))

    def update_recent_files(self, files: list[str]) -> None:
        self.calls.append(("update_recent_files", (files,)))

    def update_pages(self, pages: list[PageData]) -> None:
        self.calls.append(("update_pages", (pages,)))

    def show_error_dialog(self, title: str, message: str) -> None:
        self.calls.append(("show_error_dialog", (title, message)))

    def get_device_pixel_ratio(self) -> float:
        """テスト環境では標準 DPI モニター相当の 1.0 を返す。"""
        return 1.0

    def get_current_page(self) -> int:
        """現在表示中のページ番号を返す Mock。"""
        return self._current_page

    def show_password_dialog(self, file_path: str) -> str | None:
        """パスワード入力ダイアログの Mock。_password_dialog_return を返す。"""
        self.calls.append(("show_password_dialog", (file_path,)))
        return self._password_dialog_return

    # --- Callback registration ---
    # View 自身はロジックを持たず、Presenter から受け取った関数を保持するだけにする。

    def set_on_file_open_requested(self, cb: Callable[[], None]) -> None:
        self._on_file_open_requested = cb

    def set_on_file_dropped(self, cb: Callable[[str], None]) -> None:
        self._on_file_dropped = cb

    def set_on_recent_file_selected(self, cb: Callable[[str], None]) -> None:
        self._on_recent_file_selected = cb

    def set_on_area_selected(
        self, cb: Callable[[int, RectCoords], None]
    ) -> None:
        self._on_area_selected = cb

    def set_on_zoom_changed(self, cb: Callable[[float], None]) -> None:
        self._on_zoom_changed = cb

    def set_on_cache_management_requested(
        self, cb: Callable[[], None]
    ) -> None:
        self._on_cache_management_requested = cb

    def set_on_pages_needed(self, cb: Callable[[list[int]], None]) -> None:
        self._on_pages_needed = cb

    def set_on_settings_requested(self, cb: Callable[[], None]) -> None:
        self._on_settings_requested = cb

    # --- Simulation helpers (for triggering callbacks in tests) ---
    # テストコードからユーザー操作を模擬するための補助メソッド群。

    def simulate_file_open_requested(self) -> None:
        if self._on_file_open_requested:
            self._on_file_open_requested()

    def simulate_file_dropped(self, path: str) -> None:
        if self._on_file_dropped:
            self._on_file_dropped(path)

    def simulate_area_selected(
        self, page_number: int, rect: RectCoords
    ) -> None:
        if self._on_area_selected:
            self._on_area_selected(page_number, rect)

    def simulate_zoom_changed(self, level: float) -> None:
        if self._on_zoom_changed:
            self._on_zoom_changed(level)

    def simulate_pages_needed(self, page_numbers: list[int]) -> None:
        if self._on_pages_needed:
            self._on_pages_needed(page_numbers)

    def simulate_settings_requested(self) -> None:
        if self._on_settings_requested:
            self._on_settings_requested()

    # --- Helpers ---

    def get_calls(self, method_name: str) -> list[tuple]:
        """指定メソッドの呼び出し引数一覧を返す。

        テスト側で `calls` の内部構造を直接触らずに済むようにするための
        小さな問い合わせ API である。
        """
        return [args for name, args in self.calls if name == method_name]


class MockSidePanelView:
    """ISidePanelView を満たすテスト用ダミー実装。"""

    def __init__(self) -> None:
        # MainView と同じく、呼び出し履歴と登録コールバックだけを持つ。
        self.calls: list[tuple[str, tuple]] = []

        self._on_translate_requested: Callable[[bool], None] | None = None
        self._on_custom_prompt_submitted: Callable[[str], None] | None = None
        self._on_tab_changed: Callable[[str], None] | None = None
        self._on_force_image_toggled: Callable[[bool], None] | None = None

    # --- Display commands ---

    def set_selected_text(self, text: str) -> None:
        self.calls.append(("set_selected_text", (text,)))

    def set_selected_content_preview(
        self, text: str, thumbnail: bytes | None
    ) -> None:
        self.calls.append(("set_selected_content_preview", (text, thumbnail)))

    def update_result_text(self, text: str) -> None:
        self.calls.append(("update_result_text", (text,)))

    def show_loading(self, loading: bool) -> None:
        self.calls.append(("show_loading", (loading,)))

    def update_cache_status_brief(self, text: str) -> None:
        self.calls.append(("update_cache_status_brief", (text,)))

    def set_active_tab(self, mode: str) -> None:
        self.calls.append(("set_active_tab", (mode,)))

    # --- Callback registration ---

    def set_on_translate_requested(self, cb: Callable[[bool], None]) -> None:
        self._on_translate_requested = cb

    def set_on_custom_prompt_submitted(
        self, cb: Callable[[str], None]
    ) -> None:
        self._on_custom_prompt_submitted = cb

    def set_on_tab_changed(self, cb: Callable[[str], None]) -> None:
        self._on_tab_changed = cb

    def set_on_force_image_toggled(
        self, cb: Callable[[bool], None]
    ) -> None:
        self._on_force_image_toggled = cb

    # --- Simulation helpers ---

    def simulate_translate_requested(self, include_explanation: bool) -> None:
        if self._on_translate_requested:
            self._on_translate_requested(include_explanation)

    def simulate_custom_prompt_submitted(self, prompt: str) -> None:
        if self._on_custom_prompt_submitted:
            self._on_custom_prompt_submitted(prompt)

    def simulate_force_image_toggled(self, checked: bool) -> None:
        if self._on_force_image_toggled:
            self._on_force_image_toggled(checked)

    # --- Helpers ---

    def get_calls(self, method_name: str) -> list[tuple]:
        """指定メソッドの呼び出し引数一覧を返す。"""
        return [args for name, args in self.calls if name == method_name]


class MockSettingsDialogView:
    """ISettingsDialogView を満たすテスト用ダミー実装。

    辞書ベースの set/get で値を保持し、exec_dialog の返り値は
    テスト側から _exec_return で制御する。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._values: dict[str, object] = {
            "render_format": "png",
            "jpeg_quality": 85,
            "default_dpi": 144,
            "page_cache_max_size": 50,
            "auto_detect_embedded_images": True,
            "auto_detect_math_fonts": True,
        }
        # exec_dialog が返す固定値。True = OK、False = Cancel。
        self._exec_return: bool = True
        self._on_reset_defaults: Callable[[], None] | None = None

    # --- Getters ---

    def get_render_format(self):
        return self._values["render_format"]

    def get_jpeg_quality(self) -> int:
        return self._values["jpeg_quality"]

    def get_default_dpi(self) -> int:
        return self._values["default_dpi"]

    def get_page_cache_max_size(self) -> int:
        return self._values["page_cache_max_size"]

    def get_auto_detect_embedded_images(self) -> bool:
        return self._values["auto_detect_embedded_images"]

    def get_auto_detect_math_fonts(self) -> bool:
        return self._values["auto_detect_math_fonts"]

    # --- Setters ---

    def set_render_format(self, value) -> None:
        self.calls.append(("set_render_format", (value,)))
        self._values["render_format"] = value

    def set_jpeg_quality(self, value: int) -> None:
        self.calls.append(("set_jpeg_quality", (value,)))
        self._values["jpeg_quality"] = value

    def set_default_dpi(self, value: int) -> None:
        self.calls.append(("set_default_dpi", (value,)))
        self._values["default_dpi"] = value

    def set_page_cache_max_size(self, value: int) -> None:
        self.calls.append(("set_page_cache_max_size", (value,)))
        self._values["page_cache_max_size"] = value

    def set_auto_detect_embedded_images(self, value: bool) -> None:
        self.calls.append(("set_auto_detect_embedded_images", (value,)))
        self._values["auto_detect_embedded_images"] = value

    def set_auto_detect_math_fonts(self, value: bool) -> None:
        self.calls.append(("set_auto_detect_math_fonts", (value,)))
        self._values["auto_detect_math_fonts"] = value

    # --- Callback registration ---

    def set_on_reset_defaults(self, cb: Callable[[], None]) -> None:
        self._on_reset_defaults = cb

    # --- Lifecycle ---

    def exec_dialog(self) -> bool:
        self.calls.append(("exec_dialog", ()))
        return self._exec_return

    # --- Simulation helpers ---

    def simulate_reset_defaults(self) -> None:
        if self._on_reset_defaults:
            self._on_reset_defaults()

    # --- Helpers ---

    def get_calls(self, method_name: str) -> list[tuple]:
        """指定メソッドの呼び出し引数一覧を返す。"""
        return [args for name, args in self.calls if name == method_name]
