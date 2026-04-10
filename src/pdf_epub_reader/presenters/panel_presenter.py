"""AI サイドパネルの操作を仲介する Presenter。

PanelPresenter は、ユーザーが選択したテキストに対して
「翻訳する」「カスタムプロンプトで解析する」といった AI 操作を担当する。
メイン画面側の文書操作とは責務を分離し、サイドパネル固有の流れだけに集中させる。
"""

from __future__ import annotations

import asyncio

from pdf_epub_reader.dto import AnalysisMode, AnalysisRequest, SelectionContent
from pdf_epub_reader.interfaces.model_interfaces import IAIModel
from pdf_epub_reader.interfaces.view_interfaces import ISidePanelView


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

        # View は「どの関数を呼ぶか」だけを知ればよい。
        # 実際の処理内容は Presenter 側に閉じ込める。
        self._view.set_on_translate_requested(self._on_translate_requested)
        self._view.set_on_custom_prompt_submitted(self._on_custom_prompt_submitted)
        self._view.set_on_force_image_toggled(self._on_force_image_toggled)

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

    # --- Private callback handlers ---

    def _on_force_image_toggled(self, checked: bool) -> None:
        """「画像としても送信」チェックボックスの状態変更を記録する。"""
        self._force_include_image = checked

    def _on_translate_requested(self, include_explanation: bool) -> None:
        """翻訳ボタン押下を受け取り、非同期処理を開始する。"""

        # ボタンクリック自体は同期イベントなので、その場で await せず
        # タスク化して UI スレッドをふさがないようにする。
        asyncio.ensure_future(self._do_translate(include_explanation))

    async def _do_translate(self, include_explanation: bool) -> None:
        """翻訳モードで AI 解析を実行し、結果を View に返す。"""
        if not self._selected_text:
            # 解析対象が無いときは API を呼ばず静かに抜ける。
            # View 側に分岐を持たせないため、この判定は Presenter に置く。
            return
        self._view.show_loading(True)
        try:
            request = AnalysisRequest(
                text=self._selected_text,
                mode=AnalysisMode.TRANSLATION,
                include_explanation=include_explanation,
                images=self._collect_images(),
            )
            result = await self._ai_model.analyze(request)

            # 翻訳結果がある場合はそれを優先し、無い場合だけ raw_response を使う。
            # こうしておくと、将来レスポンス形式が多少揺れても表示が壊れにくい。
            display = result.translated_text or result.raw_response
            if include_explanation and result.explanation:
                # 説明は翻訳本文と視覚的に分けたいので簡易区切りを入れる。
                display += "\n\n---\n\n" + result.explanation
            self._view.update_result_text(display)
        finally:
            # 失敗時でもローディングを解除しないと UI が固まって見えるため、
            # finally で必ず終了処理を行う。
            self._view.show_loading(False)

    def _on_custom_prompt_submitted(self, prompt: str) -> None:
        """カスタムプロンプト送信を受け取り、非同期処理を開始する。"""
        asyncio.ensure_future(self._do_custom_prompt(prompt))

    async def _do_custom_prompt(self, prompt: str) -> None:
        """カスタムプロンプトモードで AI 解析を実行する。"""
        if not self._selected_text:
            return
        self._view.show_loading(True)
        try:
            request = AnalysisRequest(
                text=self._selected_text,
                mode=AnalysisMode.CUSTOM_PROMPT,
                custom_prompt=prompt,
                images=self._collect_images(),
            )
            result = await self._ai_model.analyze(request)
            # カスタムプロンプトでは出力形式が固定でないため、
            # Presenter は raw_response をそのまま表示に渡す。
            self._view.update_result_text(result.raw_response)
        finally:
            self._view.show_loading(False)

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
