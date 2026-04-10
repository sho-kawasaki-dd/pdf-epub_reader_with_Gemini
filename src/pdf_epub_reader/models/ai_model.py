"""AI 解析 Model — google-genai SDK を用いた Gemini API 連携。

Presenter からは ``await ai_model.analyze(request)`` の形で呼び出される。
API キー未設定でもインスタンス化は可能だが、API 呼び出し時に
``AIKeyMissingError`` を送出する（ドキュメント閲覧専用利用を妨げない）。

Context Caching 関連メソッド（create_cache / get_cache_status /
invalidate_cache / count_tokens）は Phase 7 で本実装に差し替える。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from pdf_epub_reader.dto import (
    AnalysisMode,
    AnalysisRequest,
    AnalysisResult,
    CacheStatus,
    ModelInfo,
)
from pdf_epub_reader.utils.config import AppConfig, DEFAULT_EXPLANATION_ADDENDUM
from pdf_epub_reader.utils.exceptions import (
    AIAPIError,
    AIKeyMissingError,
    AIRateLimitError,
)

logger = logging.getLogger(__name__)

# --- 定数 ---
_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 1.0
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# カスタムプロンプトモード用のシステム指示テンプレート
_CUSTOM_PROMPT_SYSTEM_TEMPLATE = (
    "{output_language} で回答してください。Markdown 形式で回答してください。"
)


class AIModel:
    """Gemini API を利用した AI 解析 Model。

    ``IAIModel`` Protocol を満たす。API キーが設定されていない場合でも
    インスタンス化でき、``analyze()`` 等の API 呼び出し時に初めて
    ``AIKeyMissingError`` を送出する。

    Args:
        api_key: Gemini API キー。None の場合は API 呼び出し不可。
        config: アプリケーション設定。None ならデフォルト値を使用。
    """

    def __init__(
        self,
        api_key: str | None = None,
        config: AppConfig | None = None,
    ) -> None:
        self._config = config or AppConfig()
        self._client: genai.Client | None = None
        if api_key:
            self._client = genai.Client(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """テキスト（+画像）を Gemini API に送信し解析結果を返す。

        Args:
            request: 解析要求。mode / text / images / model_name 等を含む。

        Returns:
            AnalysisResult: API の応答を DTO にマッピングした結果。

        Raises:
            AIKeyMissingError: API キーが未設定の場合。
            AIAPIError: API 通信エラー。
            AIRateLimitError: レート制限超過（リトライ上限到達後）。
        """
        self._ensure_client()

        model_name = request.model_name or self._config.gemini_model_name
        system_instruction = self._build_system_instruction(
            request.mode, include_explanation=request.include_explanation
        )
        contents = self._build_contents(request)

        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
        )

        response = await self._call_with_retry(model_name, contents, config)

        return self._parse_response(request, response)

    async def list_available_models(self) -> list[ModelInfo]:
        """API 経由で利用可能なモデル一覧を取得する。

        ``generateContent`` をサポートするモデルのみを返す。

        Returns:
            モデル情報のリスト（model_id, display_name）。

        Raises:
            AIKeyMissingError: API キーが未設定の場合。
            AIAPIError: API 通信エラー。
        """
        self._ensure_client()
        assert self._client is not None  # for type checker

        try:
            models: list[ModelInfo] = []
            async for model in await self._client.aio.models.list():
                # generateContent をサポートするモデルのみ収集
                actions = model.supported_actions or []
                if "generateContent" not in actions:
                    continue
                models.append(
                    ModelInfo(
                        model_id=model.name or "",
                        display_name=model.display_name or model.name or "",
                    )
                )
            return models
        except genai_errors.APIError as exc:
            raise AIAPIError(
                str(exc), status_code=getattr(exc, "code", None)
            ) from exc

    def update_config(self, config: AppConfig) -> None:
        """アプリケーション設定を更新する。

        設定ダイアログでモデル名・プロンプト等が変更された際に
        Presenter から呼び出される。
        """
        self._config = config

    # --- Phase 7 スタブ ---

    async def create_cache(self, full_text: str) -> CacheStatus:
        """Phase 7 で本実装に差し替える。"""
        return CacheStatus(
            is_active=True,
            ttl_seconds=3600,
            token_count=len(full_text.split()),
        )

    async def get_cache_status(self) -> CacheStatus:
        """Phase 7 で本実装に差し替える。"""
        return CacheStatus(is_active=False)

    async def invalidate_cache(self) -> None:
        """Phase 7 で本実装に差し替える。"""

    async def count_tokens(self, text: str) -> int:
        """Phase 7 で本実装に差し替える。"""
        return len(text.split())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_client(self) -> None:
        """クライアントが初期化済みであることを確認する。"""
        if self._client is None:
            raise AIKeyMissingError("API キーが設定されていません")

    def _build_system_instruction(
        self, mode: AnalysisMode, *, include_explanation: bool = False
    ) -> str:
        """モードに応じたシステムプロンプトを構築する。

        テンプレート内の ``{output_language}`` を実際の出力言語で置換する。
        翻訳モードかつ ``include_explanation=True`` の場合は、解説要求の
        追記（``DEFAULT_EXPLANATION_ADDENDUM``）をプロンプト末尾に付与する。
        """
        if mode == AnalysisMode.TRANSLATION:
            template = self._config.system_prompt_translation
        else:
            template = _CUSTOM_PROMPT_SYSTEM_TEMPLATE
        instruction = template.format(output_language=self._config.output_language)
        if mode == AnalysisMode.TRANSLATION and include_explanation:
            instruction += DEFAULT_EXPLANATION_ADDENDUM
        return instruction

    @staticmethod
    def _build_contents(
        request: AnalysisRequest,
    ) -> list[genai_types.Part | str]:
        """リクエストから API に送る contents リストを組み立てる。

        テキストを先頭に置き、画像がある場合は Part.from_bytes で追加する。
        カスタムプロンプトモードではプロンプト文を先頭に付与する。
        """
        parts: list[genai_types.Part | str] = []

        # カスタムプロンプトモードの場合、ユーザープロンプトを先頭に配置
        if (
            request.mode == AnalysisMode.CUSTOM_PROMPT
            and request.custom_prompt
        ):
            parts.append(request.custom_prompt)

        # 対象テキスト
        parts.append(request.text)

        # マルチモーダル画像
        for image_bytes in request.images:
            parts.append(
                genai_types.Part.from_bytes(
                    data=image_bytes, mime_type="image/png"
                )
            )

        return parts

    async def _call_with_retry(
        self,
        model_name: str,
        contents: list[Any],
        config: genai_types.GenerateContentConfig,
    ) -> genai_types.GenerateContentResponse:
        """指数バックオフリトライ付きで API を呼び出す。

        429 / 5xx ステータスを最大 ``_MAX_RETRIES`` 回リトライする。
        リトライ上限超過後は ``AIRateLimitError`` (429) または
        ``AIAPIError`` (その他) を送出する。
        """
        assert self._client is not None  # for type checker

        last_exception: genai_errors.APIError | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = (
                    await self._client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                )
                return response
            except genai_errors.APIError as exc:
                last_exception = exc
                status_code = getattr(exc, "code", None)

                if status_code not in _RETRYABLE_STATUS_CODES:
                    # リトライ対象外のエラーは即座に変換して送出
                    break

                # リトライ待機（最終試行では待たない）
                if attempt < _MAX_RETRIES - 1:
                    wait = _INITIAL_BACKOFF_S * (2 ** attempt)
                    logger.warning(
                        "Gemini API エラー (code=%s), %s秒後にリトライ (%d/%d)",
                        status_code,
                        wait,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)

        # リトライ上限到達 — 例外を変換して送出
        assert last_exception is not None
        status_code = getattr(last_exception, "code", None)
        msg = str(last_exception)

        if status_code == 429:
            raise AIRateLimitError(msg) from last_exception
        raise AIAPIError(msg, status_code=status_code) from last_exception

    @staticmethod
    def _parse_response(
        request: AnalysisRequest,
        response: genai_types.GenerateContentResponse,
    ) -> AnalysisResult:
        """API レスポンスを AnalysisResult に変換する。

        翻訳モードかつ ``include_explanation=True`` の場合、
        レスポンス内の ``---`` 区切り線で翻訳と解説を分離する。
        区切りが見つからない場合は全体を翻訳テキストとして扱う。
        """
        raw_text = response.text or ""

        if request.mode == AnalysisMode.TRANSLATION:
            translated_text = raw_text
            explanation = None
            if request.include_explanation and "---" in raw_text:
                parts = raw_text.split("---", 1)
                translated_text = parts[0].strip()
                explanation = parts[1].strip() if len(parts) > 1 else None
            return AnalysisResult(
                translated_text=translated_text,
                explanation=explanation,
                raw_response=raw_text,
            )
        # カスタムプロンプトモード
        return AnalysisResult(raw_response=raw_text)
