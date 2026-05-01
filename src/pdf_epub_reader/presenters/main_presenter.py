"""メイン画面の操作を仲介する Presenter。

MainPresenter の役割は、メインウィンドウで発生したユーザー操作を受け取り、
必要に応じて DocumentModel を呼び出し、その結果を View や SidePanel に渡すこと。

重要なのは、このクラス自身は PySide6 の Widget や描画 API を知らない点である。
あくまで「いつ」「どの Model を呼び」「どの View メソッドを呼ぶか」を決める。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

from pdf_epub_reader.dto import (
    AnalysisStatusTexts,
    PageData,
    PlotlyRenderRequest,
    PlotlySpec,
    RectCoords,
    SelectionSnapshot,
)
from pdf_epub_reader.interfaces.model_interfaces import IAIModel, IDocumentModel
from pdf_epub_reader.interfaces.view_interfaces import (
    ICacheDialogView,
    ILanguageDialogView,
    IMainView,
    ISettingsDialogView,
)
from pdf_epub_reader.presenters.cache_presenter import CachePresenter
from pdf_epub_reader.presenters.language_presenter import LanguagePresenter
from pdf_epub_reader.presenters.panel_presenter import PanelPresenter
from pdf_epub_reader.presenters.selection_coordinator import SelectionCoordinator
from pdf_epub_reader.presenters.settings_presenter import SettingsPresenter
from pdf_epub_reader.services.markdown_export_service import (
    MarkdownExportPayload,
    build_markdown_export_document,
    build_markdown_export_filename,
)
from pdf_epub_reader.services.plotly_render_service import (
    PlotlyRenderError,
    figure_to_html,
    render_spec,
)
from pdf_epub_reader.services.plotly_sandbox import (
    SandboxCancelledError,
    SandboxOutputError,
    SandboxProvisioningError,
    SandboxRuntimeError,
    SandboxStaticCheckError,
    SandboxTimeoutError,
)
from pdf_epub_reader.services.plotly_sandbox.cancel import CancelToken
from pdf_epub_reader.services.plotly_sandbox.executor import SandboxExecutor
from pdf_epub_reader.services.translation_service import TranslationService
from pdf_epub_reader.utils.config import (
    AppConfig,
    normalize_export_folder,
    normalize_plotly_visualization_mode,
    save_config,
)
from pdf_epub_reader.utils.exceptions import (
    AICacheError,
    AIKeyMissingError,
    DocumentOpenError,
    DocumentPasswordRequired,
)

logger = logging.getLogger(__name__)


class _PlotWindowLike(Protocol):
    def show_figure_html(self, html: str, title: str) -> None: ...


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
        settings_view_factory: Callable[[str], ISettingsDialogView] | None = None,
        language_view_factory: Callable[[str], ILanguageDialogView] | None = None,
        ai_model: IAIModel | None = None,
        cache_dialog_view_factory: Callable[[str], ICacheDialogView] | None = None,
        plot_window_factory: Callable[[], _PlotWindowLike] | None = None,
        sandbox_executor: SandboxExecutor | None = None,
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
        self._translation_service = TranslationService()
        self._settings_view_factory = settings_view_factory
        self._language_view_factory = language_view_factory
        self._ai_model = ai_model
        self._cache_dialog_view_factory = cache_dialog_view_factory
        self._plot_window_factory = (
            plot_window_factory or self._build_plot_window
        )
        self._sandbox_executor = sandbox_executor
        self._plotly_worker_pool = ThreadPoolExecutor(max_workers=1)
        self._active_plotly_cancel_token: CancelToken | None = None
        # AI request の running / cancel / timing 文言を language ごとに束ねて保持する。
        self._status_texts: AnalysisStatusTexts = (
            self._translation_service.build_analysis_status_texts(
            self._config.ui_language
            )
        )
        # AI 応答時間は Plotly 描画が続く場合に備えて一時保持する。
        self._latest_ai_elapsed_s: float | None = None
        # AI 応答完了後に、Plotly が来なかった場合だけ遅延表示するための task。
        self._ai_timing_task: asyncio.Task[None] | None = None
        self._plotly_render_requested = False
        self._base_dpi: int = self._config.default_dpi
        dpr = self._view.get_device_pixel_ratio()
        self._render_dpi: int = int(self._base_dpi * dpr)
        self._zoom_level: float = 1.0
        self._selection = SelectionCoordinator(
            on_snapshot_changed=self._on_selection_snapshot_changed,
            on_threshold_crossed=self._on_selection_threshold_crossed,
            warning_threshold=10,
        )
        self._plot_windows: list[_PlotWindowLike] = []

        # View は Presenter を知らないため、ここでイベントの受け口を登録する。
        self._view.set_on_file_open_requested(self._on_file_open_requested)
        self._view.set_on_file_dropped(self._on_file_dropped)
        self._view.set_on_recent_file_selected(self._on_recent_file_selected)
        self._view.set_on_area_selected(self._on_area_selected)
        self._view.set_on_selection_requested(self._on_selection_requested)
        self._view.set_on_selection_clear_requested(
            self._on_selection_clear_requested
        )
        self._view.set_on_zoom_changed(self._on_zoom_changed)
        self._view.set_on_bookmark_selected(self._on_bookmark_selected)
        self._view.set_on_cache_management_requested(
            self._on_cache_management_requested
        )
        self._view.set_on_pages_needed(self._on_pages_needed)
        self._view.set_on_settings_requested(self._on_settings_requested)
        self._view.set_on_language_settings_requested(
            self._on_language_settings_requested
        )
        self._apply_view_texts(self._config.ui_language)

        # Phase 6: 初期化時にモデルリストをサイドパネルに設定する
        self._panel_presenter.set_available_models(
            self._config.selected_models
        )
        self._panel_presenter.set_selected_model(
            self._config.gemini_model_name
        )
        self._panel_presenter.set_plotly_mode(
            self._config.plotly_visualization_mode
        )
        self._panel_presenter.apply_ui_language(self._config.ui_language)
        self._panel_presenter.set_on_selection_delete_handler(
            self._on_selection_delete_requested
        )
        self._panel_presenter.set_on_clear_selections_handler(
            self._on_selection_clear_requested
        )
        self._panel_presenter.set_on_export_requested_handler(
            self._on_export_requested
        )
        self._panel_presenter.set_on_plotly_mode_changed_handler(
            self._on_plotly_mode_changed
        )
        self._panel_presenter.set_on_plotly_render_handler(
            self._on_plotly_render
        )
        # PanelPresenter からは request の状態変化だけを受け取り、
        # status bar の組み立ては MainPresenter 側で一元化する。
        self._panel_presenter.set_on_ai_request_started_handler(
            self._on_ai_request_started
        )
        self._panel_presenter.set_on_ai_request_finished_handler(
            self._on_ai_request_finished
        )
        self._panel_presenter.set_on_ai_request_cancelled_handler(
            self._on_ai_request_cancelled
        )
        self._panel_presenter.set_on_ai_request_failed_handler(
            self._on_ai_request_failed
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
        self._clear_selection_state(increment_generation=True)
        self._view.show_status_message(
            self._translate("main.status.opening", file_path=file_path)
        )

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
            password = self._view.show_password_dialog(
                self._translation_service.build_main_window_texts(
                    self._config.ui_language
                ).password_dialog_title,
                self._translation_service.build_main_window_texts(
                    self._config.ui_language
                ).password_dialog_message_template.format(
                    file_path=e.file_path
                ),
            )
            if password is None:
                # ユーザーがキャンセルした場合はオープンを中止する。
                self._view.show_status_message(
                    self._translate("main.status.open_cancelled")
                )
                return
            try:
                doc_info = await self._document_model.open_document(
                    file_path, password
                )
            except DocumentOpenError as retry_e:
                self._show_open_error(str(retry_e))
                self._view.show_status_message(
                    self._translate("main.status.open_failed")
                )
                return
        except DocumentOpenError as e:
            self._show_open_error(str(e))
            self._view.show_status_message(
                self._translate("main.status.open_failed")
            )
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
            self._translate(
                "main.status.loaded_pages",
                count=doc_info.total_pages,
            )
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
        """旧 API 互換の単一選択イベントを新フローへ委譲する。"""
        self._schedule_selection(page_number, rect, append=False)

    def _on_selection_requested(
        self, page_number: int, rect: RectCoords, append: bool
    ) -> None:
        """矩形選択イベントを受け取り、複数選択フローを開始する。"""
        self._schedule_selection(page_number, rect, append=append)

    def _on_selection_clear_requested(self) -> None:
        """Esc などによる全選択クリア要求を処理する。"""
        self._clear_selection_state(increment_generation=True)

    def _on_selection_delete_requested(self, selection_id: str) -> None:
        """個別選択の削除要求を処理する。"""
        self._selection.delete_slot(selection_id)

    def _schedule_selection(
        self, page_number: int, rect: RectCoords, *, append: bool
    ) -> None:
        """選択スロットを先に確保し、抽出だけを非同期で進める。"""
        selection_id, generation = self._selection.reserve_slot(
            page_number, rect, append=append
        )
        asyncio.ensure_future(
            self._extract_selection_content(
                selection_id, generation, page_number, rect
            )
        )

    async def _do_area_selected(
        self, page_number: int, rect: RectCoords
    ) -> None:
        """テスト互換のため、単一選択を直接完了させるヘルパーを残す。"""
        selection_id, generation = self._selection.reserve_slot(
            page_number, rect, append=False
        )
        await self._extract_selection_content(
            selection_id, generation, page_number, rect
        )

    async def _extract_selection_content(
        self,
        selection_id: str,
        generation: int,
        page_number: int,
        rect: RectCoords,
    ) -> None:
        """確保済みスロットに対応する抽出結果を差し込む。"""
        try:
            content = await self._document_model.extract_content(
                page_number,
                rect,
                self._render_dpi,
                force_include_image=self._panel_presenter.force_include_image,
                auto_detect_embedded_images=self._config.auto_detect_embedded_images,
                auto_detect_math_fonts=self._config.auto_detect_math_fonts,
            )
        except Exception as exc:
            if self._selection.mark_error(selection_id, generation, str(exc)):
                self._view.show_status_message(
                    self._translate("main.status.selection.read_failed")
                )
            return

        if not self._selection.apply_extracted_content(
            selection_id, generation, content
        ):
            return

        if content.cropped_image and content.detection_reason:
            reason_label = self._translate(
                f"main.reason.{content.detection_reason}"
            )
            self._view.show_status_message(
                self._translate(
                    "main.status.selection.auto_image_send",
                    reason=reason_label,
                )
            )

    def _clear_selection_state(self, *, increment_generation: bool) -> None:
        """現在の選択状態を消去し、関連 View を同期する。"""
        self._selection.clear(increment_generation=increment_generation)

    def _on_selection_snapshot_changed(
        self, snapshot: SelectionSnapshot
    ) -> None:
        """SelectionCoordinator からの状態変化通知を View / Panel に伝搬する。"""
        self._view.show_selection_highlights(snapshot)
        self._panel_presenter.set_selection_snapshot(snapshot)

    def _on_selection_threshold_crossed(self) -> None:
        """選択数が警告閾値を超えた瞬間にステータスメッセージを表示する。"""
        self._view.show_status_message(
            self._translate("side.selection.warning")
        )

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
                self._translate("main.status.cache.fetch_failed")
            )
            return

        # ダイアログ表示
        dialog_view = self._cache_dialog_view_factory(self._config.ui_language)
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
                    self._translate(
                        "main.status.cache.ttl_updated",
                        minutes=new_ttl,
                    )
                )
            elif action == "delete_selected" and selected_name:
                # 選択行のキャッシュを削除（外部キャッシュ含む）
                await self._ai_model.delete_cache(selected_name)
                self._view.show_status_message(
                    self._translate("main.status.cache.selected_deleted")
                )
                # 現在のキャッシュが削除されたものと同じならステータス更新
                if cache_status.cache_name == selected_name:
                    from pdf_epub_reader.dto import CacheStatus as CS
                    self._panel_presenter.update_cache_status(CS())
        except Exception as exc:
            logger.warning("Cache management action failed", exc_info=True)
            self._view.show_status_message(
                self._translate(
                    "main.status.cache.action_failed",
                    details=str(exc),
                )
            )

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
                self._translate("main.status.startup.api_key_missing")
            )
            return
        except Exception:
            logger.warning(
                "起動時モデル検証: モデル一覧取得失敗、既存設定で続行",
                exc_info=True,
            )
            self._view.show_status_message(
                self._translate("main.status.startup.model_fetch_failed")
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
            self._translate("main.status.startup.invalid_model")
        )

    # --- Phase 7: キャッシュ操作 ---

    def _on_cache_create(self) -> None:
        """キャッシュ作成ボタンからの非同期操作を開始する。"""
        asyncio.ensure_future(self._do_cache_create())

    def _on_export_requested(self) -> None:
        """サイドパネルからの Markdown export 要求を開始する。"""
        asyncio.ensure_future(self._do_export_markdown())

    async def _do_export_markdown(self) -> None:
        """アクティブな AI 結果を Markdown に保存する。"""
        export_state = self._panel_presenter.export_state
        if export_state is None:
            return

        export_texts = self._translation_service.build_markdown_export_texts(
            self._config.ui_language
        )
        export_folder = normalize_export_folder(self._config.export_folder)
        if not export_folder:
            self._view.show_status_message(export_texts.folder_unset_message)
            return

        doc_info = await self._document_model.get_document_info()
        if doc_info is None:
            self._view.show_status_message(
                export_texts.failure_message_template.format(
                    details=self._translate("main.status.cache.no_document")
                )
            )
            return

        try:
            export_dir = Path(export_folder)
            export_dir.mkdir(parents=True, exist_ok=True)

            markdown = build_markdown_export_document(
                MarkdownExportPayload(
                    result=export_state.result,
                    document_info=doc_info,
                    selection_snapshot=export_state.selection_snapshot,
                    action_mode=export_state.action_mode,
                    model_name=export_state.model_name,
                ),
                self._config,
                export_texts,
            )
            file_path = export_dir / build_markdown_export_filename(doc_info)
            file_path.write_text(markdown, encoding="utf-8")
        except Exception as exc:
            self._view.show_status_message(
                export_texts.failure_message_template.format(details=str(exc))
            )
            logger.warning("Markdown export failed", exc_info=True)
            return

        self._view.show_status_message(
            export_texts.success_message_template.format(
                file_path=str(file_path)
            )
        )

    async def _do_cache_create(self) -> None:
        """ドキュメント全文をキャッシュする。"""
        if self._ai_model is None:
            return
        doc_info = await self._document_model.get_document_info()
        if doc_info is None:
            self._view.show_status_message(
                self._translate("main.status.cache.no_document")
            )
            return

        self._panel_presenter.set_cache_button_enabled(False)
        self._view.show_status_message(
            self._translate("main.status.cache.creating")
        )
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
                self._translate(
                    "main.status.cache.created",
                    token_count=status.token_count or "?",
                )
            )
        except AICacheError as exc:
            self._view.show_status_message(
                self._translate(
                    "main.status.cache.create_failed",
                    details=str(exc),
                )
            )
            logger.warning("Cache creation failed", exc_info=True)
        finally:
            self._panel_presenter.set_cache_button_enabled(True)

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
        self._view.show_status_message(
            self._translate("main.status.cache.expired")
        )

    async def _do_cache_invalidate(self) -> None:
        """キャッシュを無効化する。"""
        if self._ai_model is None:
            return
        self._panel_presenter.set_cache_button_enabled(False)
        try:
            await self._ai_model.invalidate_cache()
            from pdf_epub_reader.dto import CacheStatus
            self._panel_presenter.update_cache_status(CacheStatus())
            self._view.show_status_message(
                self._translate("main.status.cache.deleted")
            )
        except Exception:
            logger.warning("Cache invalidation failed", exc_info=True)
        finally:
            self._panel_presenter.set_cache_button_enabled(True)

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
        settings_view = self._settings_view_factory(self._config.ui_language)
        presenter = SettingsPresenter(
            settings_view, self._config, ai_model=self._ai_model
        )
        new_config = presenter.show()
        if new_config is not None:
            self._run_async_config_update(new_config)

    def _on_language_settings_requested(self) -> None:
        """表示言語設定ダイアログを開いて UI 表示言語を反映する。"""
        if self._language_view_factory is None:
            return
        language_view = self._language_view_factory(self._config.ui_language)
        presenter = LanguagePresenter(language_view, self._config)
        new_config = presenter.show()
        if new_config is not None:
            self._run_async_config_update(
                new_config,
                status_message=self._translation_service.translate(
                    "presenter.language.updated",
                    new_config.ui_language,
                ),
            )

    async def _apply_config_changes(self, new_config: AppConfig) -> None:
        """新しい設定を各コンポーネントに反映する。

        DPI が変更された場合のみプレースホルダーの再配置と再レンダリングを行う。
        それ以外の設定変更は DocumentModel への反映のみで済む。
        """
        old_dpi = self._config.default_dpi
        old_hq = self._config.high_quality_downscale
        old_ui_language = self._config.ui_language
        self._config = new_config
        await self._document_model.update_config(new_config)

        # Phase 6: AI モデルにも設定を反映し、サイドパネルのモデルリストを更新
        if self._ai_model is not None:
            await self._ai_model.update_config(new_config)
        self._panel_presenter.set_available_models(
            new_config.selected_models
        )
        self._panel_presenter.set_selected_model(
            new_config.gemini_model_name
        )
        self._panel_presenter.set_plotly_mode(
            new_config.plotly_visualization_mode
        )

        if old_ui_language != new_config.ui_language:
            self._apply_view_texts(new_config.ui_language)
            self._panel_presenter.apply_ui_language(new_config.ui_language)

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

    def _run_async_config_update(
        self,
        new_config: AppConfig,
        *,
        status_message: str | None = None,
    ) -> None:
        """設定変更を async 文脈へ安全に流し込む。"""
        async def _runner() -> None:
            await self._apply_config_changes(new_config)
            if status_message is not None:
                self._view.show_status_message(status_message)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_runner())
            return

        loop.create_task(_runner())

    def _on_plotly_mode_changed(self, mode: str) -> None:
        """サイドパネルの Plotly モード変更を設定へ永続化する。"""
        self._config.plotly_visualization_mode = normalize_plotly_visualization_mode(
            mode
        )
        save_config(self._config)

    def _on_ai_request_started(self) -> None:
        """AI request 開始時に running UI を表示する。

        ここでは前回 request に紐づく timing 予約を破棄し、今まさに動いている
        request の timing 状態だけを初期化する。
        """
        self._cancel_ai_timing_task()
        self._latest_ai_elapsed_s = None
        self._plotly_render_requested = False

    def _on_ai_request_finished(self, elapsed_s: float) -> None:
        """AI request 成功時に running UI を解除し、timing 表示を保留する。

        Plotly へ進む可能性があるので、ここでは即時に timing を確定させず、
        まず elapsed 値だけを保持して後段の描画結果に合わせる。
        """
        self._latest_ai_elapsed_s = elapsed_s
        self._schedule_ai_timing_message()

    def _on_ai_request_cancelled(self) -> None:
        """AI request cancel 時に running UI を解除し、cancel status を出す。

        cancel 後に遅延表示が残ると誤解を招くため、保持していた timing state も
        ここで消しておく。
        """
        self._cancel_ai_timing_task()
        self._latest_ai_elapsed_s = None
        self._plotly_render_requested = False
        self._view.show_status_message(self._status_texts.cancelled_message)

    def _on_ai_request_failed(self) -> None:
        """AI request が失敗したときに running UI を解除する。

        エラー本文は PanelPresenter 側で既に View に出しているため、ここでは
        進行中表示だけを片付ける。cancel / failure の取り残しを防ぐ最終地点。
        """
        self._cancel_ai_timing_task()
        self._latest_ai_elapsed_s = None
        self._plotly_render_requested = False

    def _on_plotly_render(self, request: PlotlyRenderRequest) -> None:
        """PanelPresenter から渡された Plotly spec を復元して表示する。

        Phase 1 では JSON spec を即時描画し、複数 spec は設定に応じて選択する。
        Phase 2 では同じ入口から Python spec も受け取り、必要時だけ sandbox
        実行へ分岐する。

        ``ai_response_elapsed_s`` が付いていればそれを優先し、無ければ直前の
        AI request 完了時に保持した値を使う。これにより Plotly 経路でも
        AI 応答時間と graph render 時間を 1 つの status にまとめられる。
        """
        if not request.specs:
            return

        self._plotly_render_requested = True
        ai_elapsed_s = request.ai_response_elapsed_s
        if ai_elapsed_s is None:
            ai_elapsed_s = self._latest_ai_elapsed_s
        elif ai_elapsed_s is not None:
            self._latest_ai_elapsed_s = ai_elapsed_s

        plotly_texts = self._translation_service.build_plotly_texts(
            self._config.ui_language
        )
        selected = self._select_plotly_spec(request.specs, plotly_texts)
        if selected is None:
            return

        title = self._resolve_plotly_spec_title(selected, plotly_texts)
        if request.origin_mode == "python" and selected.language == "json":
            # Python モード送信でも python block が無かった場合の fallback 通知。
            self._view.show_status_message(
                plotly_texts.sandbox_fallback_to_json_message
            )

        if selected.language == "python":
            self._start_plotly_python_render(
                selected,
                title,
                plotly_texts,
                ai_elapsed_s=ai_elapsed_s,
            )
            return

        self._render_and_show_plotly_figure(
            selected,
            title,
            plotly_texts,
            ai_elapsed_s=ai_elapsed_s,
        )

    def _render_and_show_plotly_figure(
        self,
        spec: PlotlySpec,
        title: str,
        plotly_texts,
        *,
        ai_elapsed_s: float | None = None,
    ) -> None:
        """JSON spec を同期復元し、PlotWindow へ表示する。

        計測対象は AI 応答待ちではなく、復元処理とウィンドウ表示そのものだけ。
        そのため start / end はこのメソッドの中で閉じ、AI 時間と混ぜない。
        """
        try:
            start_time = time.perf_counter()
            figure = render_spec(
                spec,
                sandbox=None,
                timeout_s=self._config.plotly_sandbox_timeout_s,
                cancel_token=CancelToken(),
            )
            html = figure_to_html(figure)
            window = self._plot_window_factory()
            self._plot_windows.append(window)
            window.show_figure_html(
                html,
                plotly_texts.window_title_template.format(title=title),
            )
            # 画面に出す直前までを graph render の対象として測る。
            graph_elapsed_s = time.perf_counter() - start_time
        except PlotlyRenderError as exc:
            self._view.show_status_message(
                self._build_plotly_render_error_message(exc, plotly_texts)
            )
            return

        self._show_plotly_render_success_status(
            plotly_texts,
            title=title,
            ai_elapsed_s=ai_elapsed_s,
            graph_elapsed_s=graph_elapsed_s,
        )

    def _start_plotly_python_render(
        self,
        spec: PlotlySpec,
        title: str,
        plotly_texts,
        *,
        ai_elapsed_s: float | None = None,
    ) -> None:
        """Python spec の sandbox 描画を非同期で開始する。

        sandbox 準備や実行時間が長くなり得るため、ここでは先に進行中 UI を出し、
        実処理は background task に流す。
        """
        cancel_token = CancelToken()
        self._active_plotly_cancel_token = cancel_token
        # 初回は venv 準備が走る可能性があるため、開始直後に進捗 UI を出す。
        self._view.show_status_message(plotly_texts.sandbox_provisioning_message)
        self._view.show_plotly_running(cancel_token.cancel)
        self._run_plotly_render_coroutine(
            self._render_plotly_python_async(
                spec,
                title,
                plotly_texts,
                cancel_token,
                ai_elapsed_s=ai_elapsed_s,
            )
        )

    async def _render_plotly_python_async(
        self,
        spec: PlotlySpec,
        title: str,
        plotly_texts,
        cancel_token: CancelToken,
        *,
        ai_elapsed_s: float | None = None,
    ) -> None:
        """QThreadPool 上で sandbox 描画を実行し、結果を UI に反映する。

        ここで測るのは sandbox での Plotly 図生成から UI 表示までの時間であり、
        AI 応答待ち時間は caller から渡された値をそのまま使う。
        """
        try:
            start_time = time.perf_counter()
            loop = asyncio.get_running_loop()
            figure = await loop.run_in_executor(
                self._plotly_worker_pool,
                lambda: render_spec(
                    spec,
                    sandbox=self._get_sandbox_executor(),
                    timeout_s=self._config.plotly_sandbox_timeout_s,
                    cancel_token=cancel_token,
                ),
            )
            html = figure_to_html(figure)
            window = self._plot_window_factory()
            self._plot_windows.append(window)
            window.show_figure_html(
                html,
                plotly_texts.window_title_template.format(title=title),
            )
            # HTML 生成とウィンドウ表示が完了した時点を graph render 完了とみなす。
            graph_elapsed_s = time.perf_counter() - start_time
        except PlotlyRenderError as exc:
            self._view.show_status_message(
                self._build_plotly_render_error_message(exc, plotly_texts)
            )
            return
        except SandboxTimeoutError:
            # AI 応答自体は残しつつ、図だけを諦める。
            self._view.show_status_message(plotly_texts.sandbox_timeout_message)
            return
        except SandboxCancelledError:
            self._view.show_status_message(plotly_texts.sandbox_cancelled_message)
            return
        except SandboxStaticCheckError as exc:
            # 禁止 import 名や builtin 名をそのまま UI へ返せるようにしている。
            self._view.show_status_message(
                plotly_texts.sandbox_static_check_error_message.format(
                    names=", ".join(exc.disallowed)
                )
            )
            return
        except (SandboxRuntimeError, SandboxOutputError):
            self._view.show_status_message(
                plotly_texts.sandbox_runtime_error_message
            )
            return
        except SandboxProvisioningError as exc:
            message = plotly_texts.sandbox_provisioning_failed_message
            if "network" in str(exc).lower() or "offline" in str(exc).lower():
                message = plotly_texts.sandbox_provisioning_failed_offline_message
            self._view.show_status_message(message)
            return
        finally:
            self._active_plotly_cancel_token = None
            self._view.clear_plotly_running()

        self._show_plotly_render_success_status(
            plotly_texts,
            title=title,
            ai_elapsed_s=ai_elapsed_s,
            graph_elapsed_s=graph_elapsed_s,
        )

    def _run_plotly_render_coroutine(self, coro: asyncio.Future | asyncio.coroutines) -> None:
        """イベントループの有無に応じて Plotly 描画 coroutine を起動する。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return
        loop.create_task(coro)

    def _get_sandbox_executor(self) -> SandboxExecutor:
        """SandboxExecutor を遅延初期化して再利用する。"""
        if self._sandbox_executor is None:
            self._sandbox_executor = SandboxExecutor()
        return self._sandbox_executor

    def _show_open_error(self, details: str) -> None:
        self._view.show_error_dialog(
            self._translate("main.error.open.title"),
            self._translate("main.error.open.message", details=details),
        )

    def _apply_view_texts(self, language: str) -> None:
        """MainWindow に対して解決済み UI 文言束を適用する。"""
        self._status_texts = self._translation_service.build_analysis_status_texts(
            language
        )
        self._view.apply_ui_texts(
            self._translation_service.build_main_window_texts(language)
        )

    def _cancel_ai_timing_task(self) -> None:
        if self._ai_timing_task is not None:
            self._ai_timing_task.cancel()
            self._ai_timing_task = None

    def _schedule_ai_timing_message(self) -> None:
        """Plotly が来なかった AI request だけ timing を遅延表示する。

        1 イベントループ分だけ遅らせることで、直後に Plotly render が始まった場合は
        graph timing 側に上書きさせる余地を残す。
        """
        if self._latest_ai_elapsed_s is None:
            return

        self._cancel_ai_timing_task()

        async def _runner() -> None:
            try:
                await asyncio.sleep(0)
                if self._plotly_render_requested:
                    return
                elapsed_s = self._latest_ai_elapsed_s
                if elapsed_s is None:
                    return
                self._view.show_status_message(
                    self._status_texts.timing_only.format(
                        ai_seconds=self._format_seconds(elapsed_s)
                    )
                )
            finally:
                if self._ai_timing_task is asyncio.current_task():
                    self._ai_timing_task = None

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if not self._plotly_render_requested:
                elapsed_s = self._latest_ai_elapsed_s
                if elapsed_s is not None:
                    self._view.show_status_message(
                        self._status_texts.timing_only.format(
                            ai_seconds=self._format_seconds(elapsed_s)
                        )
                    )
            return

        self._ai_timing_task = loop.create_task(_runner())

    @staticmethod
    def _format_seconds(value: float) -> str:
        return f"{value:.1f}"

    def _translate(self, key: str, **kwargs: object) -> str:
        return self._translation_service.translate(
            key,
            self._config.ui_language,
            **kwargs,
        )

    def _select_plotly_spec(
        self,
        specs: list[PlotlySpec],
        plotly_texts,
    ) -> PlotlySpec | None:
        """複数 Plotly spec から表示対象を 1 件選ぶ。"""
        if len(specs) == 1 or self._config.plotly_multi_spec_mode == "first_only":
            return specs[0]

        # `prompt` モードでは View に選択ダイアログを委譲する。
        labels = [
            self._resolve_plotly_spec_title(spec, plotly_texts)
            for spec in specs
        ]
        selected_index = self._view.show_plotly_spec_picker(
            plotly_texts.multi_select_dialog_title,
            plotly_texts.multi_select_dialog_label,
            labels,
            plotly_texts.multi_select_cancel_button_text,
        )
        if selected_index is None:
            return None
        if selected_index < 0 or selected_index >= len(specs):
            return None
        return specs[selected_index]

    def _resolve_plotly_spec_title(self, spec: PlotlySpec, plotly_texts) -> str:
        """spec からウィンドウ表示用タイトルを解決する。"""
        if spec.title:
            return spec.title
        return plotly_texts.spec_fallback_title_template.format(
            index=spec.index + 1
        )

    def _build_plotly_render_error_message(
        self,
        error: PlotlyRenderError,
        plotly_texts,
    ) -> str:
        if error.code == "invalid_json":
            return plotly_texts.invalid_json_message_template.format(
                details=error.details
            )
        return plotly_texts.restore_failed_message_template.format(
            details=error.details
        )

    def _show_plotly_render_success_status(
        self,
        plotly_texts,
        *,
        title: str,
        ai_elapsed_s: float | None,
        graph_elapsed_s: float,
    ) -> None:
        """AI timing と graph timing のどちらを status bar に出すかを決める。"""
        if ai_elapsed_s is None:
            self._view.show_status_message(
                plotly_texts.render_success_message_template.format(title=title)
            )
            return

        self._view.show_status_message(
            self._status_texts.timing_with_graph.format(
                ai_seconds=self._format_seconds(ai_elapsed_s),
                graph_seconds=self._format_seconds(graph_elapsed_s),
            )
        )

    def _build_plot_window(self) -> _PlotWindowLike:
        from pdf_epub_reader.views.plot_window import PlotWindow

        return PlotWindow()

    async def _reload_layout(self) -> None:
        """DPI 変更後にプレースホルダーを再計算し再描画する。

        現在表示中のページ番号を記憶し、再レイアウト後にスクロール位置を復元する。
        """
        doc_info = await self._document_model.get_document_info()
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
