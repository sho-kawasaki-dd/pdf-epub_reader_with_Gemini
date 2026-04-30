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
from typing import Literal, Protocol, runtime_checkable

from pdf_epub_reader.dto import (
    CacheDialogTexts,
    CacheStatus,
    LanguageDialogTexts,
    MainWindowTexts,
    PageData,
    RectCoords,
    SettingsDialogTexts,
    SelectionSnapshot,
    SidePanelTexts,
    ToCEntry,
)
from pdf_epub_reader.utils.config import PlotlyMultiSpecMode


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
    def display_toc(self, entries: list[ToCEntry]) -> None: ...
    def set_zoom_level(self, level: float) -> None: ...
    def show_selection_highlight(
        self, page_number: int, rect: RectCoords
    ) -> None: ...
    def show_selection_highlights(
        self, snapshot: SelectionSnapshot
    ) -> None:
        """複数選択のスナップショット全体を View に同期する。

        Phase 2 以降の正規 API。View は snapshot.slots の順序に従って
        複数ハイライトと番号バッジを再描画する。
        """
        ...
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

    def show_password_dialog(self, title: str, message: str) -> str | None:
        """パスワード保護された文書に対してパスワード入力ダイアログを表示する。

        Passive View の例外的な同期メソッド。モーダルダイアログのため、
        ユーザーが入力を完了するまで制御を返さない。

        Returns:
            ユーザーが入力したパスワード文字列。
            キャンセルされた場合は ``None``。
        """
        ...

    def show_plotly_spec_picker(
        self,
        title: str,
        label: str,
        items: list[str],
        cancel_button_text: str,
    ) -> int | None:
        """複数 Plotly spec から 1 件を選ばせ、選択 index を返す。"""
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
    def set_on_selection_requested(
        self, cb: Callable[[int, RectCoords, bool], None]
    ) -> None:
        """矩形選択要求のコールバックを登録する。

        第 3 引数の bool は追加選択モードを表し、False は通常選択
        (全置換)、True は追加選択 (Ctrl+ドラッグ) を意味する。
        """
        ...
    def set_on_selection_clear_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """Esc などによる全選択クリア要求のコールバックを登録する。"""
        ...
    def set_on_zoom_changed(
        self, cb: Callable[[float], None]
    ) -> None: ...
    def set_on_bookmark_selected(
        self, cb: Callable[[int], None]
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

    def set_on_language_settings_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """表示言語設定ダイアログ起動要求のコールバックを登録する。"""
        ...

    def set_high_quality_downscale(self, enabled: bool) -> None:
        """高品質縮小 (Pillow LANCZOS) の有効/無効を切り替える。

        設定ダイアログから変更されたとき Presenter が呼び出す。
        View は現在のズーム率に応じて即座に表示を更新する。
        """
        ...

    def apply_ui_texts(self, texts: MainWindowTexts) -> None:
        """Presenter が解決済みの UI 文言束を適用する。"""
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
    def set_selection_snapshot(
        self, snapshot: SelectionSnapshot
    ) -> None:
        """選択一覧の表示元となるスナップショットを反映する。"""
        ...

    def set_combined_selection_preview(self, text: str) -> None:
        """AI に送る連結プレビュー文字列を表示する。"""
        ...

    def update_result_text(self, text: str) -> None: ...
    def set_export_enabled(self, enabled: bool) -> None: ...
    def show_loading(self, loading: bool) -> None: ...
    def update_cache_status_brief(self, text: str) -> None: ...
    def set_active_tab(self, mode: str) -> None: ...
    def apply_ui_texts(self, texts: SidePanelTexts) -> None: ...

    # --- Callback registration (View → Presenter) ---

    def set_on_translate_requested(
        self, cb: Callable[[bool], None]
    ) -> None: ...
    def set_on_custom_prompt_submitted(
        self, cb: Callable[[str], None]
    ) -> None: ...
    def set_on_export_requested(
        self, cb: Callable[[], None]
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
    def set_on_plotly_toggled(
        self, cb: Callable[[bool], None]
    ) -> None:
        """Plotly 可視化トグルの切り替えコールバックを登録する。"""
        ...
    def set_on_selection_delete_requested(
        self, cb: Callable[[str], None]
    ) -> None:
        """選択一覧の個別削除要求コールバックを登録する。"""
        ...

    def set_on_clear_selections_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """選択一覧の全消去要求コールバックを登録する。"""
        ...

    # --- Phase 6: モデル選択 ---

    def set_available_models(self, model_names: list[str]) -> None:
        """モデル選択プルダウンの選択肢を設定する。"""
        ...

    def set_selected_model(self, model_name: str) -> None:
        """モデル選択プルダウンの現在値を設定する。"""
        ...

    def set_model_combo_enabled(self, enabled: bool) -> None:
        """モデル選択プルダウンの有効/無効を切り替える。

        モデル未設定時に disabled にし、プレースホルダーを表示する。
        """
        ...

    def set_plotly_toggle_checked(self, checked: bool) -> None:
        """Plotly 可視化トグルのチェック状態を反映する。"""
        ...

    def set_on_model_changed(
        self, cb: Callable[[str], None]
    ) -> None:
        """モデル選択プルダウンの変更時コールバックを登録する。"""
        ...

    # --- Phase 7: キャッシュ操作 ---

    def set_on_cache_create_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """キャッシュ作成ボタン押下時のコールバックを登録する。"""
        ...

    def set_on_cache_invalidate_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """キャッシュ削除ボタン押下時のコールバックを登録する。"""
        ...

    def set_cache_active(self, active: bool) -> None:
        """キャッシュ状態に応じてトグルボタンのテキストを切り替える。

        active=True → "削除" 表示、active=False → "作成" 表示。
        """
        ...

    def set_cache_button_enabled(self, enabled: bool) -> None:
        """キャッシュ操作中にトグルボタンを無効化する。"""
        ...

    def show_confirm_dialog(self, title: str, message: str) -> bool:
        """確認ダイアログを表示し、ユーザーの OK/Cancel を返す。

        モデル切替時のキャッシュ破棄確認等で使用する。
        Passive View の例外的な同期メソッド。
        """
        ...

    # --- Phase 7.5: キャッシュカウントダウン ---

    def start_cache_countdown(self, expire_time: str) -> None:
        """キャッシュ残り時間のカウントダウンを開始する。

        Args:
            expire_time: ISO 8601 形式の有効期限文字列。
                         View は 1 秒間隔で残り時間を H:MM:SS で更新する。
        """
        ...

    def stop_cache_countdown(self) -> None:
        """カウントダウンを停止し、タイマーを解放する。"""
        ...

    def set_on_cache_expired(self, cb: Callable[[], None]) -> None:
        """カウントダウンが 0 に到達したときのコールバックを登録する。

        View のタイマーが残り 0 以下を検出したときに発火される。
        Presenter はこのコールバックで get_cache_status を再取得し UI を更新する。
        """
        ...


@runtime_checkable
class ICacheDialogView(Protocol):
    """キャッシュ管理ダイアログが満たすべき契約。

    Phase 7 で導入。2 タブ構成のモーダルダイアログ:
    - タブ1「現在のキャッシュ」: ステータス表示 + 作成/削除/TTL 更新
    - タブ2「キャッシュ確認」: アプリ用キャッシュ一覧テーブル + 選択行削除
    """

    # --- タブ1: 現在のキャッシュ ---

    def set_cache_name(self, name: str) -> None: ...
    def set_cache_model(self, model: str) -> None: ...
    def set_cache_token_count(self, count: int | None) -> None: ...
    def set_cache_ttl_seconds(self, seconds: int | None) -> None: ...
    def set_cache_expire_time(self, expire_time: str | None) -> None: ...
    def set_cache_is_active(self, active: bool) -> None: ...
    def set_ttl_spin_value(self, minutes: int) -> None: ...
    def get_new_ttl_minutes(self) -> int: ...

    # --- タブ2: キャッシュ確認 ---

    def set_cache_list(self, items: list[CacheStatus]) -> None:
        """アプリ用キャッシュ一覧をテーブルに設定する。"""
        ...

    def get_selected_cache_name(self) -> str | None:
        """テーブルで選択されているキャッシュの name を返す。"""
        ...

    # --- Phase 7.5: カウントダウン ---

    def start_countdown(self, expire_time: str) -> None:
        """タブ1 の残り TTL をリアルタイム更新するカウントダウンを開始する。

        Args:
            expire_time: ISO 8601 形式の有効期限文字列。
                         1 秒間隔で H:MM:SS 形式で _ttl_label を更新する。
        """
        ...

    def stop_countdown(self) -> None:
        """カウントダウンを停止する。"""
        ...

    def apply_ui_texts(self, texts: CacheDialogTexts) -> None:
        """Presenter が解決済みの UI 文言束を適用する。"""
        ...

    # --- Lifecycle ---

    def show(self) -> str | None:
        """ダイアログをモーダル表示し、ユーザーアクションを返す。

        Returns:
            "delete" / "update_ttl" / "create" / "delete_selected" / None（閉じる）
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
    def get_high_quality_downscale(self) -> bool: ...

    # --- Setters (Presenter → View) ---

    def set_render_format(self, value: Literal["png", "jpeg"]) -> None: ...
    def set_jpeg_quality(self, value: int) -> None: ...
    def set_default_dpi(self, value: int) -> None: ...
    def set_page_cache_max_size(self, value: int) -> None: ...
    def set_auto_detect_embedded_images(self, value: bool) -> None: ...
    def set_auto_detect_math_fonts(self, value: bool) -> None: ...
    def set_high_quality_downscale(self, value: bool) -> None: ...

    # --- Callback registration ---

    def set_on_reset_defaults(self, cb: Callable[[], None]) -> None:
        """「Reset to Defaults」ボタン押下時のコールバックを登録する。"""
        ...

    # --- Phase 6: AI Models タブ Getters ---

    def get_gemini_model_name(self) -> str:
        """デフォルトモデル名を取得する。"""
        ...

    def get_selected_models(self) -> list[str]:
        """選択済みモデル一覧を取得する。"""
        ...

    def get_output_language(self) -> str:
        """出力言語を取得する。"""
        ...

    def get_system_prompt_translation(self) -> str:
        """翻訳モード用システムプロンプトを取得する。"""
        ...

    def get_cache_ttl_minutes(self) -> int:
        """Context Cache の TTL（分）を取得する。"""
        ...

    # --- Phase 8: Export タブ Getters ---

    def get_export_folder(self) -> str:
        """Markdown export の保存先フォルダを取得する。"""
        ...

    def get_export_include_explanation(self) -> bool:
        """解説を export に含めるかを取得する。"""
        ...

    def get_export_include_selection_list(self) -> bool:
        """選択元テキスト一覧を export に含めるかを取得する。"""
        ...

    def get_export_include_raw_response(self) -> bool:
        """生レスポンスを export に含めるかを取得する。"""
        ...

    def get_export_include_document_metadata(self) -> bool:
        """文書メタデータを export に含めるかを取得する。"""
        ...

    def get_export_include_usage_metrics(self) -> bool:
        """使用量メトリクスを export に含めるかを取得する。"""
        ...

    def get_export_include_yaml_frontmatter(self) -> bool:
        """YAML frontmatter を export に含めるかを取得する。"""
        ...

    def get_plotly_multi_spec_mode(self) -> PlotlyMultiSpecMode:
        """複数 Plotly spec の扱い設定を取得する。"""
        ...

    # --- Phase 6: AI Models タブ Setters ---

    def set_gemini_model_name(self, value: str) -> None:
        """デフォルトモデル名を設定する。"""
        ...

    def set_selected_models(self, value: list[str]) -> None:
        """選択済みモデル一覧を設定する。"""
        ...

    def set_output_language(self, value: str) -> None:
        """出力言語を設定する。"""
        ...

    def set_system_prompt_translation(self, value: str) -> None:
        """翻訳モード用システムプロンプトを設定する。"""
        ...

    def set_cache_ttl_minutes(self, value: int) -> None:
        """Context Cache の TTL（分）を設定する。"""
        ...

    # --- Phase 8: Export タブ Setters ---

    def set_export_folder(self, value: str) -> None:
        """Markdown export の保存先フォルダを設定する。"""
        ...

    def set_export_include_explanation(self, value: bool) -> None:
        """解説を export に含めるかを設定する。"""
        ...

    def set_export_include_selection_list(self, value: bool) -> None:
        """選択元テキスト一覧を export に含めるかを設定する。"""
        ...

    def set_export_include_raw_response(self, value: bool) -> None:
        """生レスポンスを export に含めるかを設定する。"""
        ...

    def set_export_include_document_metadata(self, value: bool) -> None:
        """文書メタデータを export に含めるかを設定する。"""
        ...

    def set_export_include_usage_metrics(self, value: bool) -> None:
        """使用量メトリクスを export に含めるかを設定する。"""
        ...

    def set_export_include_yaml_frontmatter(self, value: bool) -> None:
        """YAML frontmatter を export に含めるかを設定する。"""
        ...

    def set_plotly_multi_spec_mode(self, value: PlotlyMultiSpecMode) -> None:
        """複数 Plotly spec の扱い設定を反映する。"""
        ...

    def set_available_models_for_selection(
        self, models: list[tuple[str, str]]
    ) -> None:
        """Fetch で取得したモデル一覧を選択ウィジェットに設定する。

        Args:
            models: (model_id, display_name) のタプルリスト。
        """
        ...

    def set_on_fetch_models_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """「Fetch Models」ボタン押下時のコールバックを登録する。"""
        ...

    def set_fetch_models_loading(self, loading: bool) -> None:
        """Fetch Models のローディング表示を制御する。"""
        ...

    def show_fetch_models_error(self, message: str) -> None:
        """Fetch Models 失敗時のエラーメッセージを表示する。"""
        ...

    def apply_ui_texts(self, texts: SettingsDialogTexts) -> None:
        """Presenter が解決済みの UI 文言束を適用する。"""
        ...

    # --- Lifecycle ---

    def exec_dialog(self) -> bool:
        """ダイアログをモーダル表示し、OK なら True / Cancel なら False を返す。"""
        ...


@runtime_checkable
class ILanguageDialogView(Protocol):
    """表示言語設定ダイアログが満たすべき契約。"""

    def get_selected_language(self) -> Literal["ja", "en"]: ...

    def set_selected_language(self, value: Literal["ja", "en"]) -> None: ...

    def set_available_languages(
        self,
        languages: list[tuple[Literal["ja", "en"], str]],
    ) -> None: ...

    def apply_ui_texts(self, texts: LanguageDialogTexts) -> None: ...

    def exec_dialog(self) -> bool: ...
