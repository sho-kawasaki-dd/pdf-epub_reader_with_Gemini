"""AI サイドパネルの操作を仲介する Presenter。

PanelPresenter は、ユーザーが選択したテキストに対して
「翻訳する」「カスタムプロンプトで解析する」といった AI 操作を担当する。
メイン画面側の文書操作とは責務を分離し、サイドパネル固有の流れだけに集中させる。
"""

from __future__ import annotations

import asyncio

from collections.abc import Callable

from pdf_epub_reader.dto import (
    AnalysisMode,
    AnalysisRequest,
    CacheStatus,
    SelectionContent,
)
from pdf_epub_reader.interfaces.model_interfaces import IAIModel
from pdf_epub_reader.interfaces.view_interfaces import ISidePanelView
from pdf_epub_reader.utils.exceptions import (
    AIAPIError,
    AIKeyMissingError,
    AIRateLimitError,
)


class PanelPresenter:
    """ISidePanelView と IAIModel の調停役。

    この Presenter は「どのテキストを解析対象にするか」を内部状態として保持する。
    Phase 4 でマルチモーダル対応が追加され、選択コンテンツにクロップ画像が
    含まれる場合は AI に画像も送信する。
    """

    def __init__(self, view: ISidePanelView, ai_model: IAIModel) -> None:
        """依存オブジェクトを受け取り、サイドパネルのイベントを購読する。"""
        self._view = view
        self._ai_model = ai_model
        self._selected_text: str = ""
        # Phase 4: マルチモーダル対応の内部状態
        self._selected_content: SelectionContent | None = None
        self._force_include_image: bool = False
        # Phase 6: リクエスト単位のモデル選択
        self._current_model: str | None = None
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
        self._view.set_on_force_image_toggled(self._on_force_image_toggled)
        self._view.set_on_model_changed(self._on_model_changed)
        self._view.set_on_cache_create_requested(self._fire_cache_create)
        self._view.set_on_cache_invalidate_requested(
            self._fire_cache_invalidate
        )
        self._view.set_on_cache_expired(self._on_cache_expired)

    # --- Public API (called by MainPresenter) ---

    @property
    def force_include_image(self) -> bool:
        """「画像としても送信」トグルの現在値を返す。

        MainPresenter が extract_content に渡す force_include_image の
        ソースとして使う。
        """
        return self._force_include_image

    def set_selected_text(self, text: str) -> None:
        """現在の解析対象テキストを更新し、View にも反映する。

        後方互換のために残す。新規フローでは set_selected_content を使用する。
        """
        self._selected_text = text
        self._selected_content = None
        self._view.set_selected_text(text)

    def set_selected_content(self, content: SelectionContent) -> None:
        """マルチモーダルコンテンツを受け取り、View にプレビューを反映する。

        MainPresenter から呼ばれる。テキスト＋サムネイルを View に渡す。
        内部状態も更新し、後続の analyze 時に画像を添付できるようにする。
        """
        self._selected_content = content
        self._selected_text = content.extracted_text
        self._view.set_selected_content_preview(
            content.extracted_text,
            content.cropped_image,
        )

    def set_available_models(self, model_names: list[str]) -> None:
        """モデル選択プルダウンの選択肢を設定する。"""
        self._view.set_available_models(model_names)

    def set_selected_model(self, model_name: str) -> None:
        """モデル選択プルダウンの現在値を設定する。"""
        self._current_model = model_name
        self._view.set_selected_model(model_name)

    def get_current_model(self) -> str | None:
        """サイドパネルで現在選択中のモデル名を返す。

        MainPresenter がキャッシュ作成時に使用するモデルを取得するために呼ぶ。
        モデル未選択時は None を返す。
        """
        return self._current_model

    # --- Phase 7: キャッシュ連携 ---

    def set_on_cache_create_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録するキャッシュ作成ハンドラ。"""
        self._on_cache_create_handler = cb

    def set_on_cache_invalidate_handler(
        self, cb: Callable[[], None]
    ) -> None:
        """MainPresenter が登録するキャッシュ削除ハンドラ。"""
        self._on_cache_invalidate_handler = cb

    def update_cache_status(self, status: CacheStatus) -> None:
        """キャッシュ状態を内部に保持し、View を更新する。

        active + expire_time が存在する場合はカウントダウンを開始し、
        inactive の場合はカウントダウンを停止する。
        """
        self._cache_status = status
        self._view.set_cache_active(status.is_active)
        if status.is_active:
            brief = f"キャッシュ: ON ({status.token_count or '?'} tokens)"
        else:
            brief = "キャッシュ: OFF"
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

    def _on_model_changed(self, model_name: str) -> None:
        """モデルプルダウンの変更を内部状態に反映する。

        キャッシュが active かつモデルが異なる場合は確認ダイアログを出す。
        OK → invalidate ハンドラ発火 + モデル更新
        Cancel → プルダウンを元のモデルに戻す
        """
        if (
            self._cache_status.is_active
            and self._cache_status.model_name
            and self._cache_status.model_name != model_name
        ):
            ok = self._view.show_confirm_dialog(
                "モデル変更確認",
                "キャッシュは現在のモデル専用です。"
                "モデルを変更するとキャッシュが削除されます。\n"
                "続行しますか？",
            )
            if not ok:
                self._view.set_selected_model(
                    self._cache_status.model_name
                )
                return
            if self._on_cache_invalidate_handler:
                self._on_cache_invalidate_handler()
        self._current_model = model_name

    _MODEL_UNSET_MSG = (
        "⚠️ モデルが未設定です。"
        "Preferences (Ctrl+,) → AI Models タブで Fetch Models を実行してください。"
    )

    def _on_translate_requested(self, include_explanation: bool) -> None:
        """翻訳ボタン押下を受け取り、非同期処理を開始する。"""

        # ボタンクリック自体は同期イベントなので、その場で await せず
        # タスク化して UI スレッドをふさがないようにする。
        asyncio.ensure_future(self._do_translate(include_explanation))

    async def _do_translate(self, include_explanation: bool) -> None:
        """翻訳モードで AI 解析を実行し、結果を View に返す。"""
        if not self._selected_text:
            return
        if not self._current_model:
            self._view.update_result_text(self._MODEL_UNSET_MSG)
            return
        self._view.show_loading(True)
        try:
            request = AnalysisRequest(
                text=self._selected_text,
                mode=AnalysisMode.TRANSLATION,
                include_explanation=include_explanation,
                images=self._collect_images(),
                model_name=self._current_model,
            )
            result = await self._ai_model.analyze(request)

            display = result.translated_text or result.raw_response
            if include_explanation and result.explanation:
                display += "\n\n---\n\n" + result.explanation
            self._view.update_result_text(display)
        except AIKeyMissingError:
            self._view.update_result_text(
                "⚠️ API キーが設定されていません。"
                "設定ダイアログまたは環境変数で GEMINI_API_KEY を設定してください。"
            )
        except AIRateLimitError:
            self._view.update_result_text(
                "⚠️ API レート制限に達しました。しばらく待ってから再試行してください。"
            )
        except AIAPIError as exc:
            self._view.update_result_text(
                f"⚠️ API エラー: {exc.message}"
            )
        finally:
            self._view.show_loading(False)

    def _on_custom_prompt_submitted(self, prompt: str) -> None:
        """カスタムプロンプト送信を受け取り、非同期処理を開始する。"""
        asyncio.ensure_future(self._do_custom_prompt(prompt))

    async def _do_custom_prompt(self, prompt: str) -> None:
        """カスタムプロンプトモードで AI 解析を実行する。"""
        if not self._selected_text:
            return
        if not self._current_model:
            self._view.update_result_text(self._MODEL_UNSET_MSG)
            return
        self._view.show_loading(True)
        try:
            request = AnalysisRequest(
                text=self._selected_text,
                mode=AnalysisMode.CUSTOM_PROMPT,
                custom_prompt=prompt,
                images=self._collect_images(),
                model_name=self._current_model,
            )
            result = await self._ai_model.analyze(request)
            self._view.update_result_text(result.raw_response)
        except AIKeyMissingError:
            self._view.update_result_text(
                "⚠️ API キーが設定されていません。"
                "設定ダイアログまたは環境変数で GEMINI_API_KEY を設定してください。"
            )
        except AIRateLimitError:
            self._view.update_result_text(
                "⚠️ API レート制限に達しました。しばらく待ってから再試行してください。"
            )
        except AIAPIError as exc:
            self._view.update_result_text(
                f"⚠️ API エラー: {exc.message}"
            )
        finally:
            self._view.show_loading(False)

    def _fire_cache_create(self) -> None:
        """View のキャッシュ作成ボタンを MainPresenter のハンドラに中継する。"""
        if not self._current_model:
            self._view.update_result_text(self._MODEL_UNSET_MSG)
            return
        if self._on_cache_create_handler:
            self._on_cache_create_handler()

    def _fire_cache_invalidate(self) -> None:
        """View のキャッシュ削除ボタンを MainPresenter のハンドラに中継する。"""
        if self._on_cache_invalidate_handler:
            self._on_cache_invalidate_handler()

    # --- Private helpers ---

    def _collect_images(self) -> list[bytes]:
        """現在の選択コンテンツからクロップ画像のリストを構築する。

        AnalysisRequest.images に渡すための画像バイト列を収集する。
        クロップ画像がある場合のみリストに含める。
        """
        images: list[bytes] = []
        if self._selected_content and self._selected_content.cropped_image:
            images.append(self._selected_content.cropped_image)
        return images
