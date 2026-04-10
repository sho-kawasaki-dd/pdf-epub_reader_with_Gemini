"""メイン画面の操作を仲介する Presenter。

MainPresenter の役割は、メインウィンドウで発生したユーザー操作を受け取り、
必要に応じて DocumentModel を呼び出し、その結果を View や SidePanel に渡すこと。

重要なのは、このクラス自身は PySide6 の Widget や描画 API を知らない点である。
あくまで「いつ」「どの Model を呼び」「どの View メソッドを呼ぶか」を決める。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from pdf_epub_reader.dto import PageData, RectCoords
from pdf_epub_reader.interfaces.model_interfaces import IAIModel, IDocumentModel
from pdf_epub_reader.interfaces.view_interfaces import (
    ICacheDialogView,
    IMainView,
    ISettingsDialogView,
)
from pdf_epub_reader.presenters.cache_presenter import CachePresenter
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter
from pdf_epub_reader.presenters.settings_presenter import SettingsPresenter
from pdf_epub_reader.utils.config import AppConfig, save_config
from pdf_epub_reader.utils.exceptions import (
    AICacheError,
    AIKeyMissingError,
    DocumentOpenError,
    DocumentPasswordRequired,
)

logger = logging.getLogger(__name__)


class MainPresenter:
    """IMainView と IDocumentModel の調停役。

    MainPresenter はアプリ全体の司令塔ではあるが、AI 解析の詳細までは持たない。
    選択されたテキストを PanelPresenter に引き渡すことで責務を分離している。
    """

    def __init__(
        self,
        view: IMainView,
        document_model: IDocumentModel,
        panel_presenter: PanelPresenter,
        config: AppConfig | None = None,
        settings_view_factory: Callable[[], ISettingsDialogView] | None = None,
        ai_model: IAIModel | None = None,
        cache_dialog_view_factory: Callable[[], ICacheDialogView] | None = None,
    ) -> None:
        """依存オブジェクトを受け取り、View のイベントを購読する。

        なぜ `__init__` でコールバック登録するのか:
        - Presenter の生成完了時点で View と接続された状態を保証したい
        - 接続漏れによる「ボタンを押しても何も起きない」を防ぎたい
        - テスト時に生成直後からイベントをシミュレートできるようにしたい

        Args:
            config: AppConfig を渡すことで自動検出設定 (auto_detect_embedded_images,
                    auto_detect_math_fonts) を extract_content に引き渡す。
                    None の場合はデフォルト値を使用する。
            settings_view_factory: 設定ダイアログ View のファクトリ。
                    呼び出すたびに新しい ISettingsDialogView を返す。
                    None の場合は設定ダイアログ機能を無効化する。
        """
        self._view = view
        self._document_model = document_model
        self._panel_presenter = panel_presenter
        self._config = config or AppConfig()
        self._settings_view_factory = settings_view_factory
        self._ai_model = ai_model
        self._cache_dialog_view_factory = cache_dialog_view_factory
        self._base_dpi: int = self._config.default_dpi
        dpr = self._view.get_device_pixel_ratio()
        self._render_dpi: int = int(self._base_dpi * dpr)
        self._zoom_level: float = 1.0

        # View は Presenter を知らないため、ここでイベントの受け口を登録する。
        self._view.set_on_file_open_requested(self._on_file_open_requested)
        self._view.set_on_file_dropped(self._on_file_dropped)
        self._view.set_on_recent_file_selected(self._on_recent_file_selected)
        self._view.set_on_area_selected(self._on_area_selected)
        self._view.set_on_zoom_changed(self._on_zoom_changed)
        self._view.set_on_bookmark_selected(self._on_bookmark_selected)
        self._view.set_on_cache_management_requested(
            self._on_cache_management_requested
        )
        self._view.set_on_pages_needed(self._on_pages_needed)
        self._view.set_on_settings_requested(self._on_settings_requested)

        # Phase 6: 初期化時にモデルリストをサイドパネルに設定する
        self._panel_presenter.set_available_models(
            self._config.selected_models
        )
        self._panel_presenter.set_selected_model(
            self._config.gemini_model_name
        )

        # Phase 7: キャッシュ操作のコールバックを登録
        self._panel_presenter.set_on_cache_create_handler(
            self._on_cache_create
        )
        self._panel_presenter.set_on_cache_invalidate_handler(
            self._on_cache_invalidate
        )
        # Phase 7.5: 期限切れ自動リフレッシュ
        self._panel_presenter.set_on_cache_expired_handler(
            self._on_cache_expired
        )

        # Phase 7 Bugfix: 起動時バックグラウンドモデル検証
        if self._ai_model is not None:
            asyncio.ensure_future(self._validate_models_on_startup())

    # --- Public API ---

    async def open_file(self, file_path: str) -> None:
        """文書を開き、必要な初期表示をまとめて行う。

        全ページ分のプレースホルダーを配置し、実画像の読み込みは
        View のビューポート監視による遅延読み込みに委ねる。

        パスワード保護 PDF の場合は View にダイアログを表示させ、
        ユーザーが入力したパスワードで再試行する。
        """
        self._view.show_status_message(f"Opening {file_path}...")

        # Phase 7: 既存キャッシュがあれば破棄する
        if self._ai_model is not None:
            try:
                status = await self._ai_model.get_cache_status()
                if status.is_active:
                    await self._ai_model.invalidate_cache()
                    from pdf_epub_reader.dto import CacheStatus
                    self._panel_presenter.update_cache_status(CacheStatus())
            except Exception:
                logger.debug("Cache invalidation on open_file skipped", exc_info=True)

        try:
            doc_info = await self._document_model.open_document(file_path)
        except DocumentPasswordRequired as e:
            # パスワード保護を検出 → View にダイアログを表示させる。
            password = self._view.show_password_dialog(e.file_path)
            if password is None:
                # ユーザーがキャンセルした場合はオープンを中止する。
                self._view.show_status_message("Open cancelled")
                return
            try:
                doc_info = await self._document_model.open_document(
                    file_path, password
                )
            except DocumentOpenError as retry_e:
                self._view.show_error_dialog(
                    "Open Error", str(retry_e)
                )
                self._view.show_status_message("Open failed")
                return
        except DocumentOpenError as e:
            self._view.show_error_dialog("Open Error", str(e))
            self._view.show_status_message("Open failed")
            return

        self._view.set_window_title(doc_info.title or doc_info.file_path)

        # 各ページの PDF ポイントサイズを基準 DPI で換算してプレースホルダーを配置する。
        # 実際の画像は View がビューポートに基づいて後から要求する。
        scale = self._base_dpi / 72.0
        placeholders = [
            PageData(
                page_number=i,
                image_data=b"",
                width=int(pw * scale),
                height=int(ph * scale),
            )
            for i, (pw, ph) in enumerate(doc_info.page_sizes)
        ]
        self._view.display_pages(placeholders)
        self._view.display_toc(doc_info.toc)
        self._view.show_status_message(
            f"Loaded {doc_info.total_pages} pages"
        )

    # --- Private callback handlers ---

    def _on_file_open_requested(self) -> None:
        """ファイル選択 UI の起点となるフック。

        Phase 1 では GUI を実装していないため処理本体は持たない。
        ただしイベントの流れを Presenter に確保しておくことで、
        Phase 2 で View 実装を差し込んだときの接続先が明確になる。
        """
        pass

    def _on_file_dropped(self, file_path: str) -> None:
        """ドラッグ&ドロップで渡されたパスから非同期オープンを開始する。"""

        # View のイベントハンドラは同期関数として呼ばれる想定なので、
        # ここではタスクを発行して GUI スレッドを止めないようにする。
        asyncio.ensure_future(self.open_file(file_path))

    def _on_recent_file_selected(self, file_path: str) -> None:
        """最近開いたファイルの選択から非同期オープンを開始する。"""
        asyncio.ensure_future(self.open_file(file_path))

    def _on_area_selected(self, page_number: int, rect: RectCoords) -> None:
        """矩形選択イベントを受け取り、抽出処理を非同期で開始する。"""
        asyncio.ensure_future(self._do_area_selected(page_number, rect))

    async def _do_area_selected(
        self, page_number: int, rect: RectCoords
    ) -> None:
        """選択範囲を強調表示し、マルチモーダルコンテンツを抽出してパネルへ渡す。

        まずハイライトを先に出すのは、抽出完了前でもユーザーに
        「選択が受理された」ことを即時に伝えるため。

        Phase 4 で extract_text → extract_content に切り替え、
        埋め込み画像や数式フォントの自動検出結果も含めてパネルへ渡す。
        自動検出でクロップ画像が付与された場合はステータスバーで通知する。
        """
        self._view.show_selection_highlight(page_number, rect)
        content = await self._document_model.extract_content(
            page_number,
            rect,
            self._render_dpi,
            force_include_image=self._panel_presenter.force_include_image,
            auto_detect_embedded_images=self._config.auto_detect_embedded_images,
            auto_detect_math_fonts=self._config.auto_detect_math_fonts,
        )
        # 自動検出でクロップ画像が付与された場合、ユーザーに理由を通知する
        if content.cropped_image and content.detection_reason:
            reason_label = {
                "embedded_image": "画像",
                "math_font": "数式",
            }[content.detection_reason]
            self._view.show_status_message(
                f"{reason_label}を検出 — 画像付きで送信します"
            )
        self._panel_presenter.set_selected_content(content)

    def _on_zoom_changed(self, level: float) -> None:
        """ズーム変更イベントを受け取り、再描画処理を非同期で開始する。"""
        asyncio.ensure_future(self._do_zoom_changed(level))

    def _on_bookmark_selected(self, page_number: int) -> None:
        """しおり項目選択を受け取り、該当ページへスクロールする。"""
        self._view.scroll_to_page(page_number)

    async def _do_zoom_changed(self, level: float) -> None:
        """ズーム率変更を View のビュー変換に反映する。

        DPI は固定のまま、QGraphicsView の setTransform で拡縮する。
        プレースホルダーの再配置やページの再レンダリングは不要。
        """
        self._zoom_level = level
        self._view.set_zoom_level(level)

    def _on_cache_management_requested(self) -> None:
        """キャッシュ管理ダイアログを開くための非同期エントリポイント。

        Phase E で CachePresenter + CacheDialog と統合予定。
        """
        asyncio.ensure_future(self._do_cache_management())

    async def _do_cache_management(self) -> None:
        """キャッシュ管理ダイアログの非同期本体。"""
        if self._ai_model is None or self._cache_dialog_view_factory is None:
            return

        # データ取得
        try:
            cache_status = await self._ai_model.get_cache_status()
            cache_list = await self._ai_model.list_caches()
        except Exception:
            logger.warning("Failed to fetch cache data", exc_info=True)
            self._view.show_status_message(
                "キャッシュ情報の取得に失敗しました"
            )
            return

        # ダイアログ表示
        dialog_view = self._cache_dialog_view_factory()
        presenter = CachePresenter(
            dialog_view, cache_status, cache_list, self._config
        )
        action, new_ttl, selected_name = presenter.show()

        if action is None:
            return

        # アクション実行
        try:
            if action == "create":
                await self._do_cache_create()
            elif action == "delete":
                await self._do_cache_invalidate()
            elif action == "update_ttl":
                status = await self._ai_model.update_cache_ttl(new_ttl)
                self._panel_presenter.update_cache_status(status)
                self._view.show_status_message(
                    f"TTL を {new_ttl} 分に更新しました"
                )
            elif action == "delete_selected" and selected_name:
                # 選択行のキャッシュを削除（外部キャッシュ含む）
                original_name = self._ai_model._cache_name if hasattr(self._ai_model, '_cache_name') else None  # noqa: E501
                try:
                    # 一時的に _cache_name を差し替えて invalidate を呼ぶ
                    if hasattr(self._ai_model, '_cache_name'):
                        self._ai_model._cache_name = selected_name  # type: ignore[attr-defined]
                    await self._ai_model.invalidate_cache()
                    self._view.show_status_message(
                        "選択キャッシュを削除しました"
                    )
                finally:
                    if hasattr(self._ai_model, '_cache_name'):
                        self._ai_model._cache_name = original_name  # type: ignore[attr-defined]
                # 現在のキャッシュが削除されたものと同じならステータス更新
                if cache_status.cache_name == selected_name:
                    from pdf_epub_reader.dto import CacheStatus as CS
                    self._panel_presenter.update_cache_status(CS())
        except Exception as exc:
            logger.warning("Cache management action failed", exc_info=True)
            self._view.show_status_message(f"操作失敗: {exc}")

    # --- Phase 7 Bugfix: 起動時バックグラウンドモデル検証 ---

    async def _validate_models_on_startup(self) -> None:
        """起動直後にバックグラウンドで Gemini API のモデル一覧を取得し、
        config に保存されたモデルが有効か検証する。

        - Fetch 成功 + gemini_model_name が有効 → そのまま継続
        - Fetch 成功 + gemini_model_name が無効/空 → config クリア + 永続化 + 案内
        - AIKeyMissingError → ステータスに API キー設定案内
        - ネットワークエラー等 → 警告 + 既存設定で続行
        """
        assert self._ai_model is not None

        try:
            available = await self._ai_model.list_available_models()
        except AIKeyMissingError:
            self._view.show_status_message(
                "API キーを設定してください (Preferences → AI Models)"
            )
            return
        except Exception:
            logger.warning(
                "起動時モデル検証: モデル一覧取得失敗、既存設定で続行",
                exc_info=True,
            )
            self._view.show_status_message(
                "⚠️ モデル一覧の取得に失敗しました。既存設定で続行します。"
            )
            return

        available_ids = {m.model_id for m in available}
        current_model = self._config.gemini_model_name

        if current_model and current_model in available_ids:
            # 有効なモデル → そのまま継続
            return

        # gemini_model_name が空 or Fetch リストに無い → config クリア
        self._config.gemini_model_name = ""
        save_config(self._config)

        self._panel_presenter.set_available_models(
            self._config.selected_models
        )
        self._panel_presenter.set_selected_model("")
        self._view.show_status_message(
            "⚠️ モデルが未設定または無効です。"
            "Preferences (Ctrl+,) → AI Models タブで設定してください。"
        )

    # --- Phase 7: キャッシュ操作 ---

    def _on_cache_create(self) -> None:
        """キャッシュ作成ボタンからの非同期操作を開始する。"""
        asyncio.ensure_future(self._do_cache_create())

    async def _do_cache_create(self) -> None:
        """ドキュメント全文をキャッシュする。"""
        if self._ai_model is None:
            return
        doc_info = self._document_model.get_document_info()
        if doc_info is None:
            self._view.show_status_message("ドキュメントが開かれていません")
            return

        self._panel_presenter._view.set_cache_button_enabled(False)
        self._view.show_status_message("キャッシュを作成中...")
        try:
            # Phase 7.5: 既存キャッシュがあれば先に削除する（重複作成防止）
            existing = await self._ai_model.get_cache_status()
            if existing.is_active:
                await self._ai_model.invalidate_cache()

            full_text = await self._document_model.extract_all_text()
            display_name = f"pdf-reader: {doc_info.file_path.split('/')[-1].split(chr(92))[-1]}"
            status = await self._ai_model.create_cache(
                full_text,
                model_name=self._panel_presenter.get_current_model(),
                display_name=display_name,
            )
            self._panel_presenter.update_cache_status(status)
            self._view.show_status_message(
                f"キャッシュ作成完了 ({status.token_count or '?'} tokens)"
            )
        except AICacheError as exc:
            self._view.show_status_message(f"キャッシュ作成失敗: {exc}")
            logger.warning("Cache creation failed", exc_info=True)
        finally:
            self._panel_presenter._view.set_cache_button_enabled(True)

    def _on_cache_invalidate(self) -> None:
        """キャッシュ削除ボタンからの非同期操作を開始する。"""
        asyncio.ensure_future(self._do_cache_invalidate())

    def _on_cache_expired(self) -> None:
        """View のカウントダウン 0 到達から非同期リフレッシュを開始する。"""
        asyncio.ensure_future(self._do_cache_expired())

    async def _do_cache_expired(self) -> None:
        """キャッシュ期限切れ時に最新状態を取得して UI を更新する。"""
        if self._ai_model is None:
            return
        try:
            status = await self._ai_model.get_cache_status()
            self._panel_presenter.update_cache_status(status)
        except Exception:
            logger.debug("Cache expired status refresh failed", exc_info=True)
        self._view.show_status_message("キャッシュの有効期限が切れました")

    async def _do_cache_invalidate(self) -> None:
        """キャッシュを無効化する。"""
        if self._ai_model is None:
            return
        self._panel_presenter._view.set_cache_button_enabled(False)
        try:
            await self._ai_model.invalidate_cache()
            from pdf_epub_reader.dto import CacheStatus
            self._panel_presenter.update_cache_status(CacheStatus())
            self._view.show_status_message("キャッシュを削除しました")
        except Exception:
            logger.warning("Cache invalidation failed", exc_info=True)
        finally:
            self._panel_presenter._view.set_cache_button_enabled(True)

    def _on_pages_needed(self, page_numbers: list[int]) -> None:
        """View からページ画像の要求を受け取り、非同期レンダリングを開始する。"""
        asyncio.ensure_future(self._do_render_pages(page_numbers))

    async def _do_render_pages(self, page_numbers: list[int]) -> None:
        """要求されたページをレンダリングし、View に供給する。

        View のビューポート監視により呼ばれる。各ページを個別に
        render_page() で取得し、まとめて update_pages() で返す。
        """
        pages: list[PageData] = []
        for num in page_numbers:
            page = await self._document_model.render_page(
                num, self._render_dpi
            )
            pages.append(page)
        self._view.update_pages(pages)

    # --- Settings dialog ---

    def _on_settings_requested(self) -> None:
        """設定ダイアログの起動を非同期タスクとして開始する。

        SettingsPresenter.show() は同期的にダイアログを実行するため、
        ここではその結果を受けて設定変更を適用する。
        """
        if self._settings_view_factory is None:
            return
        settings_view = self._settings_view_factory()
        presenter = SettingsPresenter(
            settings_view, self._config, ai_model=self._ai_model
        )
        new_config = presenter.show()
        if new_config is not None:
            self._apply_config_changes(new_config)

    def _apply_config_changes(self, new_config: AppConfig) -> None:
        """新しい設定を各コンポーネントに反映する。

        DPI が変更された場合のみプレースホルダーの再配置と再レンダリングを行う。
        それ以外の設定変更は DocumentModel への反映のみで済む。
        """
        old_dpi = self._config.default_dpi
        old_hq = self._config.high_quality_downscale
        self._config = new_config
        self._document_model.update_config(new_config)

        # Phase 6: AI モデルにも設定を反映し、サイドパネルのモデルリストを更新
        if self._ai_model is not None:
            self._ai_model.update_config(new_config)
        self._panel_presenter.set_available_models(
            new_config.selected_models
        )
        self._panel_presenter.set_selected_model(
            new_config.gemini_model_name
        )

        # 高品質縮小の ON/OFF が変わった場合は View に即反映する。
        if old_hq != new_config.high_quality_downscale:
            self._view.set_high_quality_downscale(
                new_config.high_quality_downscale
            )

        if old_dpi != new_config.default_dpi:
            self._base_dpi = new_config.default_dpi
            dpr = self._view.get_device_pixel_ratio()
            self._render_dpi = int(self._base_dpi * dpr)
            asyncio.ensure_future(self._reload_layout())

    async def _reload_layout(self) -> None:
        """DPI 変更後にプレースホルダーを再計算し再描画する。

        現在表示中のページ番号を記憶し、再レイアウト後にスクロール位置を復元する。
        """
        doc_info = self._document_model.get_document_info()
        if doc_info is None:
            return

        # 現在ページを記憶する（get_current_page が未実装の場合は 0）
        try:
            current_page = self._view.get_current_page()
        except (AttributeError, NotImplementedError):
            current_page = 0

        scale = self._base_dpi / 72.0
        placeholders = [
            PageData(
                page_number=i,
                image_data=b"",
                width=int(pw * scale),
                height=int(ph * scale),
            )
            for i, (pw, ph) in enumerate(doc_info.page_sizes)
        ]
        self._view.display_pages(placeholders)
        self._view.scroll_to_page(current_page)
