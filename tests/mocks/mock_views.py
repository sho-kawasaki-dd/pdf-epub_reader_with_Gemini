"""Presenter テスト用の Mock View 実装。

これらの Mock は PySide6 を起動せずに Presenter の振る舞いを検証するためのもの。
実際の描画は行わず、「どのメソッドがどの引数で呼ばれたか」だけを記録する。
"""

from __future__ import annotations

from collections.abc import Callable

from pdf_epub_reader.dto import PageData, RectCoords
from pdf_epub_reader.dto.ai_dto import CacheStatus


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

    def set_high_quality_downscale(self, enabled: bool) -> None:
        self.calls.append(("set_high_quality_downscale", (enabled,)))

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
        self._on_model_changed: Callable[[str], None] | None = None
        self._on_cache_create_requested: Callable[[], None] | None = None
        self._on_cache_invalidate_requested: Callable[[], None] | None = None
        self._cache_is_active: bool = False
        self._confirm_dialog_return: bool = True
        self._on_cache_expired: Callable[[], None] | None = None

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

    def set_available_models(self, model_names: list[str]) -> None:
        self.calls.append(("set_available_models", (model_names,)))

    def set_selected_model(self, model_name: str) -> None:
        self.calls.append(("set_selected_model", (model_name,)))

    def set_on_model_changed(
        self, cb: Callable[[str], None]
    ) -> None:
        self._on_model_changed = cb

    def set_model_combo_enabled(self, enabled: bool) -> None:
        self.calls.append(("set_model_combo_enabled", (enabled,)))

    # --- Phase 7: キャッシュ操作 ---

    def set_on_cache_create_requested(
        self, cb: Callable[[], None]
    ) -> None:
        self._on_cache_create_requested = cb

    def set_on_cache_invalidate_requested(
        self, cb: Callable[[], None]
    ) -> None:
        self._on_cache_invalidate_requested = cb

    def set_cache_active(self, active: bool) -> None:
        self.calls.append(("set_cache_active", (active,)))
        self._cache_is_active = active

    def set_cache_button_enabled(self, enabled: bool) -> None:
        self.calls.append(("set_cache_button_enabled", (enabled,)))

    def show_confirm_dialog(self, title: str, message: str) -> bool:
        self.calls.append(("show_confirm_dialog", (title, message)))
        return self._confirm_dialog_return

    # --- Phase 7.5: カウントダウン ---

    def start_cache_countdown(self, expire_time: str) -> None:
        self.calls.append(("start_cache_countdown", (expire_time,)))

    def stop_cache_countdown(self) -> None:
        self.calls.append(("stop_cache_countdown", ()))

    def set_on_cache_expired(self, cb: Callable[[], None]) -> None:
        self._on_cache_expired = cb

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

    def simulate_model_changed(self, model_name: str) -> None:
        if self._on_model_changed:
            self._on_model_changed(model_name)

    def simulate_cache_create_requested(self) -> None:
        if self._on_cache_create_requested:
            self._on_cache_create_requested()

    def simulate_cache_invalidate_requested(self) -> None:
        if self._on_cache_invalidate_requested:
            self._on_cache_invalidate_requested()

    def simulate_cache_expired(self) -> None:
        """View のカウントダウン 0 到達を擬似するヘルパー。"""
        if self._on_cache_expired:
            self._on_cache_expired()

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
            "high_quality_downscale": True,
            "gemini_model_name": "",
            "selected_models": [],
            "output_language": "日本語",
            "system_prompt_translation": "",
            "cache_ttl_minutes": 60,
        }
        # exec_dialog が返す固定値。True = OK、False = Cancel。
        self._exec_return: bool = True
        self._on_reset_defaults: Callable[[], None] | None = None
        self._on_fetch_models_requested: Callable[[], None] | None = None

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

    def get_high_quality_downscale(self) -> bool:
        return self._values["high_quality_downscale"]

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

    def set_high_quality_downscale(self, value: bool) -> None:
        self.calls.append(("set_high_quality_downscale", (value,)))
        self._values["high_quality_downscale"] = value

    # --- Callback registration ---

    def set_on_reset_defaults(self, cb: Callable[[], None]) -> None:
        self._on_reset_defaults = cb

    def set_on_fetch_models_requested(self, cb: Callable[[], None]) -> None:
        self._on_fetch_models_requested = cb

    # --- Phase 6: AI Models タブ Getters ---

    def get_gemini_model_name(self) -> str:
        return self._values["gemini_model_name"]

    def get_selected_models(self) -> list[str]:
        return self._values["selected_models"]

    def get_output_language(self) -> str:
        return self._values["output_language"]

    def get_system_prompt_translation(self) -> str:
        return self._values["system_prompt_translation"]

    def get_cache_ttl_minutes(self) -> int:
        return self._values["cache_ttl_minutes"]

    # --- Phase 6: AI Models タブ Setters ---

    def set_gemini_model_name(self, value: str) -> None:
        self.calls.append(("set_gemini_model_name", (value,)))
        self._values["gemini_model_name"] = value

    def set_selected_models(self, value: list[str]) -> None:
        self.calls.append(("set_selected_models", (value,)))
        self._values["selected_models"] = value

    def set_output_language(self, value: str) -> None:
        self.calls.append(("set_output_language", (value,)))
        self._values["output_language"] = value

    def set_system_prompt_translation(self, value: str) -> None:
        self.calls.append(("set_system_prompt_translation", (value,)))
        self._values["system_prompt_translation"] = value

    def set_cache_ttl_minutes(self, value: int) -> None:
        self.calls.append(("set_cache_ttl_minutes", (value,)))
        self._values["cache_ttl_minutes"] = value

    def set_available_models_for_selection(
        self, models: list[tuple[str, str]]
    ) -> None:
        self.calls.append(("set_available_models_for_selection", (models,)))

    def set_fetch_models_loading(self, loading: bool) -> None:
        self.calls.append(("set_fetch_models_loading", (loading,)))

    def show_fetch_models_error(self, message: str) -> None:
        self.calls.append(("show_fetch_models_error", (message,)))

    # --- Lifecycle ---

    def exec_dialog(self) -> bool:
        self.calls.append(("exec_dialog", ()))
        return self._exec_return

    # --- Simulation helpers ---

    def simulate_reset_defaults(self) -> None:
        if self._on_reset_defaults:
            self._on_reset_defaults()

    def simulate_fetch_models_requested(self) -> None:
        if self._on_fetch_models_requested:
            self._on_fetch_models_requested()

    # --- Helpers ---

    def get_calls(self, method_name: str) -> list[tuple]:
        """指定メソッドの呼び出し引数一覧を返す。"""
        return [args for name, args in self.calls if name == method_name]


class MockCacheDialogView:
    """ICacheDialogView を満たすテスト用ダミー実装。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        # show() が返す固定値。テスト側で変更可能。
        self._show_return: str | None = None
        self._ttl_value: int = 60
        self._selected_cache_name: str | None = None
        self._cache_list: list[CacheStatus] = []

    # --- タブ1: 現在のキャッシュ setter ---

    def set_cache_name(self, name: str) -> None:
        self.calls.append(("set_cache_name", (name,)))

    def set_cache_model(self, model: str) -> None:
        self.calls.append(("set_cache_model", (model,)))

    def set_cache_token_count(self, count: int | None) -> None:
        self.calls.append(("set_cache_token_count", (count,)))

    def set_cache_ttl_seconds(self, seconds: int | None) -> None:
        self.calls.append(("set_cache_ttl_seconds", (seconds,)))

    def set_cache_expire_time(self, expire_time: str | None) -> None:
        self.calls.append(("set_cache_expire_time", (expire_time,)))

    def set_cache_is_active(self, active: bool) -> None:
        self.calls.append(("set_cache_is_active", (active,)))

    def set_ttl_spin_value(self, minutes: int) -> None:
        self.calls.append(("set_ttl_spin_value", (minutes,)))
        # テスト側で _ttl_value を事前設定していない場合のみ反映する。
        # テスト側は __init__ 後に _ttl_value を変更してユーザー入力を模擬する。

    def get_new_ttl_minutes(self) -> int:
        return self._ttl_value

    # --- タブ2: キャッシュ確認 ---

    def set_cache_list(self, items: list[CacheStatus]) -> None:
        self.calls.append(("set_cache_list", (items,)))
        self._cache_list = items

    def get_selected_cache_name(self) -> str | None:
        return self._selected_cache_name

    # --- Lifecycle ---

    def show(self) -> str | None:
        self.calls.append(("show", ()))
        return self._show_return

    # --- Phase 7.5: カウントダウン ---

    def start_countdown(self, expire_time: str) -> None:
        self.calls.append(("start_countdown", (expire_time,)))

    def stop_countdown(self) -> None:
        self.calls.append(("stop_countdown", ()))

    # --- Helpers ---

    def get_calls(self, method_name: str) -> list[tuple]:
        """指定メソッドの呼び出し引数一覧を返す。"""
        return [args for name, args in self.calls if name == method_name]
