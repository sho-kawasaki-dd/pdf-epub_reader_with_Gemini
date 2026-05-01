"""AI サイドパネルの操作を仲介する Presenter。

PanelPresenter は、ユーザーが選択したテキストに対して
「翻訳する」「カスタムプロンプトで解析する」といった AI 操作を担当する。
メイン画面側の文書操作とは責務を分離し、サイドパネル固有の流れだけに集中させる。
"""

from __future__ import annotations

import asyncio
import time

from collections.abc import Callable
from dataclasses import dataclass, replace

from pdf_epub_reader.dto import (
    AnalysisMode,
    AnalysisRequest,
    AnalysisResult,
    CacheStatus,
    PlotlyRenderRequest,
    PlotlySpec,
    RectCoords,
    SelectionContent,
    SelectionSlot,
    SelectionSnapshot,
)
from pdf_epub_reader.interfaces.model_interfaces import IAIModel
from pdf_epub_reader.interfaces.view_interfaces import ISidePanelView
from pdf_epub_reader.services.plotly_extraction_service import extract_plotly_specs
from pdf_epub_reader.services.translation_service import TranslationService
from pdf_epub_reader.utils.config import (
    PlotlyVisualizationMode,
    normalize_model_name,
    normalize_plotly_visualization_mode,
    normalize_ui_language,
)
from pdf_epub_reader.utils.exceptions import (
    AIAPIError,
    AIKeyMissingError,
    AIRateLimitError,
)


@dataclass(frozen=True)
class ExportState:
    """現在 export 可能な AI 結果のスナップショット。"""

    result: AnalysisResult
    action_mode: AnalysisMode
    include_explanation: bool
    model_name: str
    selection_snapshot: SelectionSnapshot


class PanelPresenter:
    """ISidePanelView と IAIModel の調停役。

    この Presenter は「どの選択スロット集合を解析対象にするか」を内部状態として保持する。
    Phase 5 では単一選択の内部状態をやめ、複数選択スナップショットから
    AI 入力テキストと画像配列を組み立てる。
    """

    def __init__(
        self,
        view: ISidePanelView,
        ai_model: IAIModel,
        ui_language: str = "ja",
    ) -> None:
        """依存オブジェクトを受け取り、サイドパネルのイベントを購読する。"""
        self._view = view
        self._ai_model = ai_model
        self._translation_service = TranslationService()
        self._ui_language = normalize_ui_language(ui_language, fallback="en")
        self._selection_snapshot = SelectionSnapshot()
        self._force_include_image: bool = False
        self._plotly_mode: PlotlyVisualizationMode = (
            normalize_plotly_visualization_mode("off")
        )
        self._latest_plotly_specs: list[PlotlySpec] = []
        self._active_tab_mode = AnalysisMode.TRANSLATION
        self._export_states: dict[AnalysisMode, ExportState] = {}
        # Phase 6: リクエスト単位のモデル選択
        self._available_models: list[str] = []
        self._current_model: str = ""
        self._active_analysis_task: asyncio.Task[None] | None = None
        self._on_selection_delete_handler: (
            Callable[[str], None] | None
        ) = None
        self._on_clear_selections_handler: Callable[[], None] | None = None
        self._on_export_requested_handler: Callable[[], None] | None = None
        self._on_plotly_mode_changed_handler: Callable[[str], None] | None = None
        self._on_plotly_render_handler: (
            Callable[[PlotlyRenderRequest], None] | None
        ) = None
        self._on_ai_request_started_handler: Callable[[], None] | None = None
        self._on_ai_request_finished_handler: (
            Callable[[float], None] | None
        ) = None
        self._on_ai_request_cancelled_handler: Callable[[], None] | None = None
        self._on_ai_request_failed_handler: Callable[[], None] | None = None
        # Phase 7: キャッシュ状態と MainPresenter 向けコールバック
        self._cache_status = CacheStatus()
        self._on_cache_create_handler: Callable[[], None] | None = None
        self._on_cache_invalidate_handler: Callable[[], None] | None = None
        # Phase 7.5: 期限切れコールバック
        self._on_cache_expired_handler: Callable[[], None] | None = None

        # View は「どの関数を呼ぶか」だけを知ればよい。
        # 実際の処理内容は Presenter 側に閉じ込める。
        self._view.set_on_translate_requested(self._on_translate_requested)
        self._view.set_on_custom_prompt_submitted(self._on_custom_prompt_submitted)
        self._view.set_on_export_requested(self._fire_export_requested)
        self._view.set_on_tab_changed(self._on_tab_changed)
        self._view.set_on_force_image_toggled(self._on_force_image_toggled)
        self._view.set_on_plotly_mode_changed(self._on_plotly_mode_changed)
        self._view.set_on_selection_delete_requested(
            self._fire_selection_delete_requested
        )
        self._view.set_on_clear_selections_requested(
            self._fire_clear_selections_requested
        )
        self._view.set_on_model_changed(self._on_model_changed)
        self._view.set_on_cache_create_requested(self._fire_cache_create)
        self._view.set_on_cache_invalidate_requested(
            self._fire_cache_invalidate
        )
        self._view.set_on_cache_expired(self._on_cache_expired)
        self._view.apply_ui_texts(
            self._translation_service.build_side_panel_texts(
                self._ui_language
            )
        )
        self._refresh_export_enabled()

    # --- Public API (called by MainPresenter) ---

    @property
    def force_include_image(self) -> bool:
        """「画像としても送信」トグルの現在値を返す。

        MainPresenter が extract_content に渡す force_include_image の
        ソースとして使う。
        """
        return self._force_include_image

    @property
    def export_state(self) -> ExportState | None:
        """現在アクティブなタブに対応する export 状態を返す。"""
        return self._export_states.get(self._active_tab_mode)

    def set_selected_text(self, text: str) -> None:
        """現在の解析対象テキストを更新し、View にも反映する。

        後方互換のために残す。新規フローでは set_selection_snapshot を使用する。
        """
        self.set_selection_snapshot(
            SelectionSnapshot(
                slots=(
                    SelectionSlot(
                        selection_id="legacy-selection",
                        display_number=1,
                        page_number=0,
                        rect=RectCoords(0.0, 0.0, 0.0, 0.0),
                        read_state="ready",
                        extracted_text=text,
                    ),
                ),
            )
        )

    def set_selected_content(self, content: SelectionContent) -> None:
        """マルチモーダルコンテンツを受け取り、View にプレビューを反映する。

        後方互換のために残す。新規フローでは set_selection_snapshot を使用する。
        """
        self.set_selection_snapshot(
            SelectionSnapshot(
                slots=(
                    SelectionSlot(
                        selection_id="legacy-selection",
                        display_number=1,
                        page_number=content.page_number,
                        rect=content.rect,
                        read_state="ready",
                        extracted_text=content.extracted_text,
                        has_thumbnail=content.cropped_image is not None,
                        content=content,
                    ),
                )
            )
        )

    def set_selection_snapshot(self, snapshot: SelectionSnapshot) -> None:
        """複数選択スナップショットを View に反映する。

        Phase 3 では主に MainPresenter からの先行スロット反映に使う。
        AI 解析入力の組み立ては Phase 5 でこの状態に寄せる。
        """
        self._selection_snapshot = self._normalized_snapshot(snapshot)
        self._clear_export_states()
        self._reset_plotly_specs()
        self._view.set_selection_snapshot(self._selection_snapshot)
        self._view.set_combined_selection_preview(
            self._build_analysis_text()
        )

    def set_available_models(self, model_names: list[str]) -> None:
        """モデル選択プルダウンの選択肢を設定する。"""
        self._available_models = []
        for model_name in model_names:
            normalized = normalize_model_name(model_name)
            if normalized and normalized not in self._available_models:
                self._available_models.append(normalized)

        if self._current_model not in self._available_models:
            self._current_model = ""

        self._view.set_available_models(self._available_models)
        self._view.set_selected_model(self._current_model)
        self._view.set_model_combo_enabled(bool(self._current_model))

    def set_selected_model(self, model_name: str) -> None:
        """モデル選択プルダウンの現在値を設定する。"""
        normalized = normalize_model_name(model_name)
        if normalized and normalized in self._available_models:
            self._current_model = normalized
        else:
            self._current_model = ""
        self._view.set_selected_model(self._current_model)
        self._view.set_model_combo_enabled(bool(self._current_model))

    def apply_ui_language(self, language: str) -> None:
        """表示言語を更新し、現在の表示内容を即時更新する。"""
        self._ui_language = normalize_ui_language(language, fallback="en")
        self._view.apply_ui_texts(
            self._translation_service.build_side_panel_texts(
                self._ui_language
            )
        )
        self._view.set_selected_model(self._current_model)
        self._view.set_model_combo_enabled(bool(self._current_model))
        self._view.set_selection_snapshot(self._selection_snapshot)
        self._view.set_combined_selection_preview(self._build_analysis_text())
        self.update_cache_status(self._cache_status)
        self._refresh_export_enabled()

    def get_current_model(self) -> str:
        """サイドパネルで現在選択中のモデル名を返す。

        MainPresenter がキャッシュ作成時に使用するモデルを取得するために呼ぶ。
        モデル未選択時は空文字を返す。
        """
        return self._current_model

    # --- Phase 7: キャッシュ連携 ---

    def set_on_cache_create_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録するキャッシュ作成ハンドラ。"""
        self._on_cache_create_handler = cb

    def set_on_selection_delete_handler(
        self, cb: Callable[[str], None]
    ) -> None:
        """MainPresenter が登録する選択削除ハンドラ。"""
        self._on_selection_delete_handler = cb

    def set_on_clear_selections_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録する全選択クリアハンドラ。"""
        self._on_clear_selections_handler = cb

    def set_on_export_requested_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録する export 要求ハンドラ。"""
        self._on_export_requested_handler = cb

    def set_on_plotly_mode_changed_handler(
        self, cb: Callable[[str], None]
    ) -> None:
        """MainPresenter が登録する Plotly モード変更ハンドラ。"""
        self._on_plotly_mode_changed_handler = cb

    def set_on_plotly_render_handler(
        self, cb: Callable[[PlotlyRenderRequest], None]
    ) -> None:
        """MainPresenter が登録する Plotly 描画要求ハンドラ。"""
        self._on_plotly_render_handler = cb

    def set_on_ai_request_started_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録する AI request 開始ハンドラ。"""
        self._on_ai_request_started_handler = cb

    def set_on_ai_request_finished_handler(
        self, cb: Callable[[float], None]
    ) -> None:
        """MainPresenter が登録する AI request 完了ハンドラ。"""
        self._on_ai_request_finished_handler = cb

    def set_on_ai_request_cancelled_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録する AI request cancel ハンドラ。"""
        self._on_ai_request_cancelled_handler = cb

    def set_on_ai_request_failed_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録する AI request failure ハンドラ。"""
        self._on_ai_request_failed_handler = cb

    def set_plotly_mode(self, mode: str) -> None:
        """Plotly mode を保持しつつ、サイドパネル UI へ反映する。

        もともとは Phase 1 の boolean トグルだったが、Phase 2 で 3 状態化した。
        Presenter 側は常に正規化済みモードを保持し、View にはそのまま渡す。
        """
        normalized = normalize_plotly_visualization_mode(mode)
        self._plotly_mode = normalized
        self._view.set_plotly_mode(normalized)

    def set_on_cache_invalidate_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録するキャッシュ削除ハンドラ。"""
        self._on_cache_invalidate_handler = cb

    def set_cache_button_enabled(self, enabled: bool) -> None:
        """キャッシュ操作ボタンの有効/無効を View に反映する。"""
        self._view.set_cache_button_enabled(enabled)

    def update_cache_status(self, status: CacheStatus) -> None:
        """キャッシュ状態を内部に保持し、View を更新する。

        active + expire_time が存在する場合はカウントダウンを開始し、
        inactive の場合はカウントダウンを停止する。
        """
        self._cache_status = status
        self._view.set_cache_active(status.is_active)
        if status.is_active:
            status_text = self._translate("cache.status.active")
            brief = self._translate(
                "presenter.panel.cache.on",
                status=status_text,
                token_count=status.token_count or "?",
            )
        else:
            brief = self._translate(
                "presenter.panel.cache.off",
                status=self._translate("cache.status.inactive"),
            )
        self._view.update_cache_status_brief(brief)

        # Phase 7.5: カウントダウン連携
        if status.is_active and status.expire_time:
            self._view.start_cache_countdown(status.expire_time)
        else:
            self._view.stop_cache_countdown()

    def set_on_cache_expired_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録する期限切れハンドラ。"""
        self._on_cache_expired_handler = cb

    def _on_cache_expired(self) -> None:
        """View のカウントダウンが 0 に到達したとき呼ばれる。

        MainPresenter に委譲して get_cache_status の再取得を行う。
        """
        if self._on_cache_expired_handler:
            self._on_cache_expired_handler()

    # --- Private callback handlers ---

    def _on_force_image_toggled(self, checked: bool) -> None:
        """「画像としても送信」チェックボックスの状態変更を記録する。"""
        self._force_include_image = checked

    def _on_plotly_mode_changed(self, mode: str) -> None:
        """Plotly 可視化モードの変更を記録して MainPresenter に通知する。"""
        normalized = normalize_plotly_visualization_mode(mode)
        self._plotly_mode = normalized
        if self._on_plotly_mode_changed_handler is not None:
            self._on_plotly_mode_changed_handler(normalized)

    def _on_tab_changed(self, mode: str) -> None:
        """アクティブタブ変更に応じて export 可能状態を更新する。"""
        if mode == AnalysisMode.CUSTOM_PROMPT.value:
            self._active_tab_mode = AnalysisMode.CUSTOM_PROMPT
        else:
            self._active_tab_mode = AnalysisMode.TRANSLATION
        self._refresh_export_enabled()

    def _on_model_changed(self, model_name: str) -> None:
        """モデルプルダウンの変更を内部状態に反映する。

        キャッシュが active かつモデルが異なる場合は確認ダイアログを出す。
        OK → invalidate ハンドラ発火 + モデル更新
        Cancel → プルダウンを元のモデルに戻す
        """
        normalized = normalize_model_name(model_name)
        if not normalized or normalized not in self._available_models:
            return

        previous_model = self._current_model
        if (
            self._cache_status.is_active
            and self._cache_status.model_name
            and self._cache_status.model_name != normalized
        ):
            ok = self._view.show_confirm_dialog(
                self._translate("presenter.panel.model_change.title"),
                self._translate("presenter.panel.model_change.message"),
            )
            if not ok:
                self._current_model = previous_model
                self._view.set_selected_model(previous_model)
                self._view.set_model_combo_enabled(bool(previous_model))
                return
            if self._on_cache_invalidate_handler:
                self._on_cache_invalidate_handler()
        self._current_model = normalized
        self._view.set_model_combo_enabled(True)

    def _on_translate_requested(self, include_explanation: bool) -> None:
        """翻訳ボタン押下を受け取り、非同期処理を開始する。"""

        # ボタンクリック自体は同期イベントなので、その場で await せず
        # タスク化して UI スレッドをふさがないようにする。
        if self._active_analysis_task is not None:
            self._active_analysis_task.cancel()
        self._active_analysis_task = asyncio.create_task(
            self._do_translate(include_explanation)
        )

    async def _do_translate(self, include_explanation: bool) -> None:
        """翻訳モードで AI 解析を実行し、結果を View に返す。"""
        self._active_tab_mode = AnalysisMode.TRANSLATION
        current_task = asyncio.current_task()
        if self._active_analysis_task is None and current_task is not None:
            self._active_analysis_task = current_task
        try:
            analysis_text = self._build_analysis_text()
            if not analysis_text:
                self._refresh_export_enabled()
                return
            if not self._current_model:
                self._refresh_export_enabled()
                self._view.update_result_text(
                    self._translate("presenter.panel.model_unset")
                )
                return
            self._view.show_loading(True)
            try:
                if self._on_ai_request_started_handler is not None:
                    self._on_ai_request_started_handler()
                start_time = time.perf_counter()
                request = AnalysisRequest(
                    text=analysis_text,
                    mode=AnalysisMode.TRANSLATION,
                    include_explanation=include_explanation,
                    images=self._collect_images(),
                    model_name=self._current_model,
                    request_plotly_mode=self._plotly_mode,
                )
                result = await self._ai_model.analyze(request)
                elapsed_s = time.perf_counter() - start_time

                display = result.translated_text or result.raw_response
                if include_explanation and result.explanation:
                    display += "\n\n---\n\n" + result.explanation
                self._view.update_result_text(display)
                self._store_export_state(
                    action_mode=AnalysisMode.TRANSLATION,
                    result=result,
                    include_explanation=include_explanation,
                )
                if self._on_ai_request_finished_handler is not None:
                    self._on_ai_request_finished_handler(elapsed_s)
                self._handle_plotly_response(request, result, elapsed_s)
            except AIKeyMissingError:
                self._reset_plotly_specs()
                self._invalidate_export_state(AnalysisMode.TRANSLATION)
                self._view.update_result_text(
                    self._translate("presenter.panel.api_key_missing")
                )
            except AIRateLimitError:
                self._reset_plotly_specs()
                self._invalidate_export_state(AnalysisMode.TRANSLATION)
                self._view.update_result_text(
                    self._translate("presenter.panel.rate_limit")
                )
            except AIAPIError as exc:
                self._reset_plotly_specs()
                self._invalidate_export_state(AnalysisMode.TRANSLATION)
                self._view.update_result_text(
                    self._translate(
                        "presenter.panel.api_error",
                        message=exc.message,
                    )
                )
            except asyncio.CancelledError:
                if self._active_analysis_task is asyncio.current_task():
                    if self._on_ai_request_cancelled_handler is not None:
                        self._on_ai_request_cancelled_handler()
                raise
            except Exception:
                if self._active_analysis_task is asyncio.current_task():
                    if self._on_ai_request_failed_handler is not None:
                        self._on_ai_request_failed_handler()
                raise
            finally:
                if self._active_analysis_task is asyncio.current_task():
                    self._view.show_loading(False)
        finally:
            self._clear_active_analysis_task_if_current()

    def _on_custom_prompt_submitted(self, prompt: str) -> None:
        """カスタムプロンプト送信を受け取り、非同期処理を開始する。"""
        if self._active_analysis_task is not None:
            self._active_analysis_task.cancel()
        self._active_analysis_task = asyncio.create_task(
            self._do_custom_prompt(prompt)
        )

    async def _do_custom_prompt(self, prompt: str) -> None:
        """カスタムプロンプトモードで AI 解析を実行する。"""
        self._active_tab_mode = AnalysisMode.CUSTOM_PROMPT
        current_task = asyncio.current_task()
        if self._active_analysis_task is None and current_task is not None:
            self._active_analysis_task = current_task
        try:
            analysis_text = self._build_analysis_text()
            if not analysis_text:
                self._refresh_export_enabled()
                return
            if not self._current_model:
                self._refresh_export_enabled()
                self._view.update_result_text(
                    self._translate("presenter.panel.model_unset")
                )
                return
            self._view.show_loading(True)
            try:
                if self._on_ai_request_started_handler is not None:
                    self._on_ai_request_started_handler()
                start_time = time.perf_counter()
                request = AnalysisRequest(
                    text=analysis_text,
                    mode=AnalysisMode.CUSTOM_PROMPT,
                    custom_prompt=prompt,
                    images=self._collect_images(),
                    model_name=self._current_model,
                    request_plotly_mode=self._plotly_mode,
                )
                result = await self._ai_model.analyze(request)
                elapsed_s = time.perf_counter() - start_time
                self._view.update_result_text(result.raw_response)
                self._store_export_state(
                    action_mode=AnalysisMode.CUSTOM_PROMPT,
                    result=result,
                    include_explanation=False,
                )
                if self._on_ai_request_finished_handler is not None:
                    self._on_ai_request_finished_handler(elapsed_s)
                self._handle_plotly_response(request, result, elapsed_s)
            except AIKeyMissingError:
                self._reset_plotly_specs()
                self._invalidate_export_state(AnalysisMode.CUSTOM_PROMPT)
                self._view.update_result_text(
                    self._translate("presenter.panel.api_key_missing")
                )
            except AIRateLimitError:
                self._reset_plotly_specs()
                self._invalidate_export_state(AnalysisMode.CUSTOM_PROMPT)
                self._view.update_result_text(
                    self._translate("presenter.panel.rate_limit")
                )
            except AIAPIError as exc:
                self._reset_plotly_specs()
                self._invalidate_export_state(AnalysisMode.CUSTOM_PROMPT)
                self._view.update_result_text(
                    self._translate(
                        "presenter.panel.api_error",
                        message=exc.message,
                    )
                )
            except asyncio.CancelledError:
                if self._active_analysis_task is asyncio.current_task():
                    if self._on_ai_request_cancelled_handler is not None:
                        self._on_ai_request_cancelled_handler()
                raise
            except Exception:
                if self._active_analysis_task is asyncio.current_task():
                    if self._on_ai_request_failed_handler is not None:
                        self._on_ai_request_failed_handler()
                raise
            finally:
                if self._active_analysis_task is asyncio.current_task():
                    self._view.show_loading(False)
        finally:
            self._clear_active_analysis_task_if_current()

    def _fire_cache_create(self) -> None:
        """View のキャッシュ作成ボタンを MainPresenter のハンドラに中継する。"""
        if not self._current_model:
            self._view.update_result_text(
                self._translate("presenter.panel.model_unset")
            )
            return
        if self._on_cache_create_handler:
            self._on_cache_create_handler()

    def _fire_cache_invalidate(self) -> None:
        """View のキャッシュ削除ボタンを MainPresenter のハンドラに中継する。"""
        if self._on_cache_invalidate_handler:
            self._on_cache_invalidate_handler()

    def _fire_selection_delete_requested(self, selection_id: str) -> None:
        """View の個別削除要求を MainPresenter のハンドラに中継する。"""
        if self._on_selection_delete_handler:
            self._on_selection_delete_handler(selection_id)

    def _fire_clear_selections_requested(self) -> None:
        """View の全消去要求を MainPresenter のハンドラに中継する。"""
        if self._on_clear_selections_handler:
            self._on_clear_selections_handler()

    def _fire_export_requested(self) -> None:
        """View の export 要求を MainPresenter のハンドラに中継する。"""
        if self.export_state is None:
            return
        if self._on_export_requested_handler:
            self._on_export_requested_handler()

    # --- Private helpers ---

    def _normalized_snapshot(
        self, snapshot: SelectionSnapshot
    ) -> SelectionSnapshot:
        """表示番号を現行順に詰め直したスナップショットを返す。"""
        return SelectionSnapshot(
            slots=tuple(
                replace(slot, display_number=index)
                for index, slot in enumerate(snapshot.slots, start=1)
            )
        )

    def _build_analysis_text(self) -> str:
        """AI に送る本文を選択順・明示的区切り付きで構築する。"""
        parts: list[str] = []
        for slot in self._selection_snapshot.slots:
            if slot.read_state != "ready":
                continue
            text = slot.extracted_text.strip()
            if not text:
                continue
            parts.append(
                self._translate(
                    "presenter.panel.selection_block",
                    number=slot.display_number,
                    page=slot.page_number + 1,
                    text=text,
                )
            )
        return "\n\n".join(parts)

    def _translate(self, key: str, **kwargs: object) -> str:
        return self._translation_service.translate(
            key,
            self._ui_language,
            **kwargs,
        )

    def _store_export_state(
        self,
        *,
        action_mode: AnalysisMode,
        result: AnalysisResult,
        include_explanation: bool,
    ) -> None:
        self._export_states[action_mode] = ExportState(
            result=result,
            action_mode=action_mode,
            include_explanation=include_explanation,
            model_name=self._current_model,
            selection_snapshot=self._selection_snapshot,
        )
        self._refresh_export_enabled()

    def _invalidate_export_state(self, action_mode: AnalysisMode) -> None:
        self._export_states.pop(action_mode, None)
        self._refresh_export_enabled()

    def _clear_export_states(self) -> None:
        self._export_states.clear()
        self._refresh_export_enabled()

    def _refresh_export_enabled(self) -> None:
        self._view.set_export_enabled(self.export_state is not None)

    def cancel_active_request(self) -> None:
        """進行中の AI request task を cancel する。"""
        if self._active_analysis_task is not None:
            self._active_analysis_task.cancel()

    def _clear_active_analysis_task_if_current(self) -> None:
        if self._active_analysis_task is asyncio.current_task():
            self._active_analysis_task = None

    def _handle_plotly_response(
        self,
        request: AnalysisRequest,
        result: AnalysisResult,
        elapsed_s: float,
    ) -> None:
        """AI 応答から Plotly spec を抽出し、描画要求へ変換する。

        `request_plotly_mode` は送信時点のスナップショットなので、応答待ち中に
        UI 側のモードが切り替わっても、この処理は元の要求に従って判定する。
        """
        if request.request_plotly_mode == "off":
            self._reset_plotly_specs()
            return

        extracted_specs = extract_plotly_specs(result.raw_response)
        # Python モード時は python spec を優先し、無ければ JSON fallback を使う。
        selected_specs = self._select_plotly_specs_for_render(
            extracted_specs,
            request.request_plotly_mode,
        )
        self._latest_plotly_specs = selected_specs
        if selected_specs and self._on_plotly_render_handler is not None:
            self._on_plotly_render_handler(
                PlotlyRenderRequest(
                    specs=selected_specs,
                    origin_mode=request.request_plotly_mode,
                    ai_response_elapsed_s=elapsed_s,
                )
            )

    def _reset_plotly_specs(self) -> None:
        """直近の Plotly 抽出結果を破棄する。"""
        self._latest_plotly_specs = []

    @staticmethod
    def _select_plotly_specs_for_render(
        specs: list[PlotlySpec],
        request_plotly_mode: str,
    ) -> list[PlotlySpec]:
        """要求モードに応じて描画対象 spec を絞り込む。"""
        if request_plotly_mode == "json":
            return [spec for spec in specs if spec.language == "json"]
        if request_plotly_mode == "python":
            python_specs = [spec for spec in specs if spec.language == "python"]
            if python_specs:
                return python_specs
            # Python ブロックが無い応答でも、JSON があれば描画まで進める。
            return [spec for spec in specs if spec.language == "json"]
        return []

    def _collect_images(self) -> list[bytes]:
        """現在の選択スナップショットから cropped_image を順序通り収集する。"""
        images: list[bytes] = []
        for slot in self._selection_snapshot.slots:
            if slot.read_state != "ready" or slot.content is None:
                continue
            if slot.content.cropped_image:
                images.append(slot.content.cropped_image)
        return images
