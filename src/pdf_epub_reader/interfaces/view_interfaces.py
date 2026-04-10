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

from typing import Literal

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

    def display_pages(self, pages: list[PageData]) -> None:
        """全ページ分のレイアウト空間（プレースホルダー）を設定する。

        ``PageData.image_data`` は空 ``bytes`` が渡される場合があり、
        その場合はプレースホルダー表示にする。
        実際の画像は後から ``update_pages()`` で供給される。
        """
        ...

    def update_pages(self, pages: list[PageData]) -> None:
        """Presenter が遅延レンダリング結果を差分で View に供給するメソッド。

        ``display_pages()`` がプレースホルダー配置用であるのに対し、
        こちらは **画像データを含む** ``PageData`` を渡して
        プレースホルダーを実画像に差し替える。
        """
        ...

    def scroll_to_page(self, page_number: int) -> None: ...
    def set_zoom_level(self, level: float) -> None: ...
    def show_selection_highlight(
        self, page_number: int, rect: RectCoords
    ) -> None: ...
    def clear_selection(self) -> None: ...
    def set_window_title(self, title: str) -> None: ...
    def show_status_message(self, message: str) -> None: ...
    def update_recent_files(self, files: list[str]) -> None: ...
    def get_device_pixel_ratio(self) -> float:
        """画面のデバイスピクセル比を返す。

        Presenter がレンダリング DPI を算出するために使用する。
        高 DPI モニター (Retina/4K) では 2.0、Windows 150% スケーリングでは 1.5 等。
        標準モニターでは 1.0 を返す。
        """
        ...

    def show_error_dialog(self, title: str, message: str) -> None:
        """重大エラー発生時にモーダルダイアログを表示する。

        Phase 3-4 のファイル読み込み失敗・API エラー等で使用する。
        """
        ...

    def show_password_dialog(self, file_path: str) -> str | None:
        """パスワード保護された文書に対してパスワード入力ダイアログを表示する。

        Passive View の例外的な同期メソッド。モーダルダイアログのため、
        ユーザーが入力を完了するまで制御を返さない。

        Args:
            file_path: パスワード保護が検出されたファイルのパス。
                       ダイアログ上でどのファイルか表示するために使う。

        Returns:
            ユーザーが入力したパスワード文字列。
            キャンセルされた場合は ``None``。
        """
        ...

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
    def set_on_pages_needed(
        self, cb: Callable[[list[int]], None]
    ) -> None:
        """ビューポート内に未レンダリングのページがあるとき呼ぶコールバックを登録する。

        View がスクロール位置から必要ページを判断し、
        そのページ番号リストを引数に Presenter を呼び出す。
        遅延読み込みを View 主導で行うための仕組み。
        """
        ...

    def set_on_cache_management_requested(
        self, cb: Callable[[], None]
    ) -> None: ...
    def set_on_settings_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """設定ダイアログ起動要求のコールバックを登録する。

        View の Edit > Preferences メニューや Ctrl+, で発火される。
        """
        ...


@runtime_checkable
class ISidePanelView(Protocol):
    """AI サイドパネルが満たすべき契約。

    サイドパネルは「選択テキストの表示」「解析結果の表示」
    「ユーザーが押したボタンの通知」に責務を絞る。
    解析の組み立てや例外処理は Presenter 側で行う。
    """

    # --- Display commands (Presenter → View) ---

    def set_selected_text(self, text: str) -> None: ...
    def set_selected_content_preview(
        self, text: str, thumbnail: bytes | None
    ) -> None:
        """選択テキストとサムネイル画像のプレビューを表示する。

        Phase 4 で追加。テキストに加え、クロップ画像のサムネイルも
        表示できるようにする。thumbnail が None ならサムネイルは非表示。
        """
        ...

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
    def set_on_force_image_toggled(
        self, cb: Callable[[bool], None]
    ) -> None:
        """「画像としても送信」チェックボックスの切り替えコールバックを登録する。

        Phase 4 で追加。ユーザーがクロップ画像の強制送信を ON/OFF した
        ときに Presenter へ通知する。
        """
        ...


@runtime_checkable
class ISettingsDialogView(Protocol):
    """設定ダイアログが満たすべき契約。

    Phase 5 で導入。モーダルダイアログとして表示し、
    ユーザーが OK/Cancel で設定を一括適用する。
    """

    # --- Getters (Presenter ← View) ---

    def get_render_format(self) -> Literal["png", "jpeg"]: ...
    def get_jpeg_quality(self) -> int: ...
    def get_default_dpi(self) -> int: ...
    def get_page_cache_max_size(self) -> int: ...
    def get_auto_detect_embedded_images(self) -> bool: ...
    def get_auto_detect_math_fonts(self) -> bool: ...

    # --- Setters (Presenter → View) ---

    def set_render_format(self, value: Literal["png", "jpeg"]) -> None: ...
    def set_jpeg_quality(self, value: int) -> None: ...
    def set_default_dpi(self, value: int) -> None: ...
    def set_page_cache_max_size(self, value: int) -> None: ...
    def set_auto_detect_embedded_images(self, value: bool) -> None: ...
    def set_auto_detect_math_fonts(self, value: bool) -> None: ...

    # --- Callback registration ---

    def set_on_reset_defaults(self, cb: Callable[[], None]) -> None:
        """「Reset to Defaults」ボタン押下時のコールバックを登録する。"""
        ...

    # --- Lifecycle ---

    def exec_dialog(self) -> bool:
        """ダイアログをモーダル表示し、OK なら True / Cancel なら False を返す。"""
        ...
