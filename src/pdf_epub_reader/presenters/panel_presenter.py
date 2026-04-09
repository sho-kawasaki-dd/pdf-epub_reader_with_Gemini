"""AI サイドパネルの操作を仲介する Presenter。

PanelPresenter は、ユーザーが選択したテキストに対して
「翻訳する」「カスタムプロンプトで解析する」といった AI 操作を担当する。
メイン画面側の文書操作とは責務を分離し、サイドパネル固有の流れだけに集中させる。
"""

from __future__ import annotations

import asyncio

from pdf_epub_reader.dto import AnalysisMode, AnalysisRequest
from pdf_epub_reader.interfaces.model_interfaces import IAIModel
from pdf_epub_reader.interfaces.view_interfaces import ISidePanelView


class PanelPresenter:
    """ISidePanelView と IAIModel の調停役。

    この Presenter は「どのテキストを解析対象にするか」を内部状態として保持する。
    これは、サイドパネルが毎回全文を持つ必要をなくし、View を単純に保つためである。
    """

    def __init__(self, view: ISidePanelView, ai_model: IAIModel) -> None:
        """依存オブジェクトを受け取り、サイドパネルのイベントを購読する。"""
        self._view = view
        self._ai_model = ai_model
        self._selected_text: str = ""

        # View は「どの関数を呼ぶか」だけを知ればよい。
        # 実際の処理内容は Presenter 側に閉じ込める。
        self._view.set_on_translate_requested(self._on_translate_requested)
        self._view.set_on_custom_prompt_submitted(self._on_custom_prompt_submitted)

    # --- Public API (called by MainPresenter) ---

    def set_selected_text(self, text: str) -> None:
        """現在の解析対象テキストを更新し、View にも反映する。

        MainPresenter から呼ばれる公開 API であり、
        サイドパネルが文書選択の詳細を知らなくても済むようにする橋渡しでもある。
        """
        self._selected_text = text
        self._view.set_selected_text(text)

    # --- Private callback handlers ---

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
            )
            result = await self._ai_model.analyze(request)
            # カスタムプロンプトでは出力形式が固定でないため、
            # Presenter は raw_response をそのまま表示に渡す。
            self._view.update_result_text(result.raw_response)
        finally:
            self._view.show_loading(False)
