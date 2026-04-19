"""AI 解析 Model — google-genai SDK を用いた Gemini API 連携。

Presenter からは ``await ai_model.analyze(request)`` の形で呼び出される。
API キー未設定でもインスタンス化は可能だが、API 呼び出し時に
``AIKeyMissingError`` を送出する（ドキュメント閲覧専用利用を妨げない）。

Context Caching は google-genai SDK の Explicit Caching API で実装。
キャッシュが active かつモデル一致時に ``analyze()`` で ``cached_content``
パラメータを自動付与し、失敗時はキャッシュなしでフォールバックする。
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
    AnalysisUsage,
    CacheStatus,
    ModelInfo,
)
from pdf_epub_reader.utils.config import AppConfig, DEFAULT_EXPLANATION_ADDENDUM
from pdf_epub_reader.utils.exceptions import (
    AICacheError,
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
        # Phase 7: キャッシュの内部状態
        # 作成済みキャッシュの名前 (SDK の resource name) とモデル名を保持し、
        # analyze() でキャッシュ統合を判定する。
        self._cache_name: str | None = None
        self._cache_model: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """テキスト（+画像）を Gemini API に送信し解析結果を返す。

        キャッシュが active かつリクエストのモデルと一致する場合、
        ``cached_content`` パラメータを自動付与する。キャッシュ付き
        リクエストが非レートリミットエラーで失敗した場合はキャッシュを
        内部クリアし、キャッシュなしで 1 回リトライする。

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

        # キャッシュ統合: active かつモデル一致時に cached_content を付与
        use_cache = (
            self._cache_name is not None
            and self._cache_model == model_name
        )

        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            cached_content=self._cache_name if use_cache else None,
        )

        if use_cache:
            try:
                response = await self._call_with_retry(
                    model_name, contents, config
                )
            except AIRateLimitError:
                raise
            except AIAPIError as exc:
                # キャッシュ付きリクエスト失敗 → キャッシュを内部クリアし
                # キャッシュなしで 1 回リトライ
                logger.warning(
                    "キャッシュ付きリクエスト失敗、キャッシュなしでリトライ: "
                    "status_code=%s cache_name=%s cache_model=%s request_model=%s message=%s",
                    exc.status_code,
                    self._cache_name,
                    self._cache_model,
                    model_name,
                    exc.message,
                )
                self._cache_name = None
                self._cache_model = None
                config = genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                )
                response = await self._call_with_retry(
                    model_name, contents, config
                )
        else:
            response = await self._call_with_retry(
                model_name, contents, config
            )

        # usage_metadata ログ出力
        self._log_usage_metadata(response)

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

    async def update_config(self, config: AppConfig) -> None:
        """アプリケーション設定を更新する。

        設定ダイアログでモデル名・プロンプト等が変更された際に
        Presenter から呼び出される。
        """
        self._config = config

    # --- Phase 7: Context Caching 本実装 ---

    async def count_tokens(
        self, text: str, *, model_name: str | None = None
    ) -> int:
        """テキストのトークン数を Gemini API で計測する。

        Args:
            text: 計測対象のテキスト。
            model_name: 使用するモデル名。None ならデフォルトモデルを使用。

        Returns:
            トークン数。

        Raises:
            AIKeyMissingError: API キーが未設定の場合。
            AIAPIError: API 通信エラー。
        """
        self._ensure_client()
        assert self._client is not None

        resolved_model = model_name or self._config.gemini_model_name
        try:
            result = await self._client.aio.models.count_tokens(
                model=resolved_model, contents=text
            )
            return result.total_tokens
        except genai_errors.APIError as exc:
            raise AIAPIError(
                str(exc), status_code=getattr(exc, "code", None)
            ) from exc

    async def create_cache(
        self,
        full_text: str,
        *,
        model_name: str | None = None,
        display_name: str | None = None,
    ) -> CacheStatus:
        """ドキュメント全文テキストの Context Cache を作成する。

        system_instruction はキャッシュに含めない（翻訳/カスタムプロンプトで
        システム指示が異なるため、リクエスト時に個別指定する）。

        Args:
            full_text: キャッシュ対象の全文テキスト。
            model_name: キャッシュ紐付きモデル名。None ならデフォルトモデル。
            display_name: キャッシュの表示名。Presenter がファイル名を渡す。

        Returns:
            作成されたキャッシュの状態。

        Raises:
            AIKeyMissingError: API キーが未設定の場合。
            AICacheError: キャッシュ作成に失敗した場合。
        """
        self._ensure_client()
        assert self._client is not None

        resolved_model = model_name or self._config.gemini_model_name
        ttl = f"{self._config.cache_ttl_minutes * 60}s"

        try:
            cache = await self._client.aio.caches.create(
                model=resolved_model,
                config=genai_types.CreateCachedContentConfig(
                    contents=[full_text],
                    display_name=display_name,
                    ttl=ttl,
                ),
            )
            self._cache_name = cache.name
            self._cache_model = cache.model
            return CacheStatus(
                is_active=True,
                ttl_seconds=self._config.cache_ttl_minutes * 60,
                token_count=getattr(
                    cache.usage_metadata, "total_token_count", None
                ) if cache.usage_metadata else None,
                cache_name=cache.name,
                display_name=cache.display_name,
                model_name=cache.model,
                expire_time=(
                    cache.expire_time.isoformat()
                    if cache.expire_time
                    else None
                ),
            )
        except Exception as exc:
            msg = str(exc)
            if "not supported for createCachedContent" in msg:
                raise AICacheError(
                    f"このモデルはコンテキストキャッシュをサポートしていません: {resolved_model}"
                ) from exc
            raise AICacheError(msg) from exc

    async def get_cache_status(self) -> CacheStatus:
        """現在のキャッシュ状態を取得する。

        内部に保持しているキャッシュ名で最新情報を API から取得し、
        expire 済みの場合は内部状態をクリアして ``is_active=False`` を返す。

        Returns:
            キャッシュの最新状態。

        Raises:
            AIKeyMissingError: API キーが未設定の場合。
        """
        if self._cache_name is None:
            return CacheStatus(is_active=False)

        self._ensure_client()
        assert self._client is not None

        try:
            cache = await self._client.aio.caches.get(
                name=self._cache_name
            )
            # expire 済みチェック
            if cache.expire_time:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                if cache.expire_time <= now:
                    self._cache_name = None
                    self._cache_model = None
                    return CacheStatus(is_active=False)

            ttl_seconds = None
            if cache.expire_time:
                from datetime import datetime, timezone
                remaining = (
                    cache.expire_time - datetime.now(timezone.utc)
                ).total_seconds()
                ttl_seconds = max(0, int(remaining))

            return CacheStatus(
                is_active=True,
                ttl_seconds=ttl_seconds,
                token_count=getattr(
                    cache.usage_metadata, "total_token_count", None
                ) if cache.usage_metadata else None,
                cache_name=cache.name,
                display_name=cache.display_name,
                model_name=cache.model,
                expire_time=(
                    cache.expire_time.isoformat()
                    if cache.expire_time
                    else None
                ),
            )
        except Exception:
            # キャッシュ取得失敗（既に削除済み等）→ 内部状態クリア
            self._cache_name = None
            self._cache_model = None
            return CacheStatus(is_active=False)

    async def invalidate_cache(self) -> None:
        """現在のキャッシュを削除する。

        既に削除済みの場合はログのみ出力し、例外は送出しない。
        """
        if self._cache_name is None:
            return

        await self.delete_cache(self._cache_name)

    async def delete_cache(self, cache_name: str) -> None:
        """名前指定でキャッシュを削除する。

        現在アクティブなキャッシュと同じ名前を削除した場合は、
        内部に保持しているキャッシュ状態も合わせてクリアする。
        一覧テーブルから任意のキャッシュを削除する用途を想定する。
        """
        if not cache_name:
            return

        if self._client is not None:
            try:
                await self._client.aio.caches.delete(
                    name=cache_name
                )
            except Exception as exc:
                logger.warning("キャッシュ削除失敗（既に削除済みの可能性）: %s", exc)

        if self._cache_name == cache_name:
            self._cache_name = None
            self._cache_model = None

    async def update_cache_ttl(self, ttl_minutes: int) -> CacheStatus:
        """現在のキャッシュの TTL を更新する。

        Args:
            ttl_minutes: 新しい TTL（分）。

        Returns:
            更新後のキャッシュのステータス。

        Raises:
            AICacheError: キャッシュが存在しない、または更新に失敗した場合。
        """
        if self._cache_name is None:
            raise AICacheError("アクティブなキャッシュがありません")

        self._ensure_client()
        assert self._client is not None

        ttl = f"{ttl_minutes * 60}s"
        try:
            cache = await self._client.aio.caches.update(
                name=self._cache_name,
                config=genai_types.UpdateCachedContentConfig(ttl=ttl),
            )
            return CacheStatus(
                is_active=True,
                ttl_seconds=ttl_minutes * 60,
                token_count=getattr(
                    cache.usage_metadata, "total_token_count", None
                ) if cache.usage_metadata else None,
                cache_name=cache.name,
                display_name=cache.display_name,
                model_name=cache.model,
                expire_time=(
                    cache.expire_time.isoformat()
                    if cache.expire_time
                    else None
                ),
            )
        except Exception as exc:
            raise AICacheError(str(exc)) from exc

    async def list_caches(self) -> list[CacheStatus]:
        """アプリ用キャッシュ一覧を取得する。

        ``display_name`` が ``"pdf-reader:"`` で始まるキャッシュのみフィルタし、
        ``CacheStatus`` DTO のリストで返す。

        Returns:
            アプリ用キャッシュの一覧。

        Raises:
            AIKeyMissingError: API キーが未設定の場合。
            AIAPIError: API 通信エラー。
        """
        self._ensure_client()
        assert self._client is not None

        try:
            result: list[CacheStatus] = []
            async for cache in await self._client.aio.caches.list():
                dn = cache.display_name or ""
                if not dn.startswith("pdf-reader:"):
                    continue
                result.append(CacheStatus(
                    is_active=True,
                    ttl_seconds=None,
                    token_count=getattr(
                        cache.usage_metadata, "total_token_count", None
                    ) if cache.usage_metadata else None,
                    cache_name=cache.name,
                    display_name=cache.display_name,
                    model_name=cache.model,
                    expire_time=(
                        cache.expire_time.isoformat()
                        if cache.expire_time
                        else None
                    ),
                ))
            return result
        except genai_errors.APIError as exc:
            raise AIAPIError(
                str(exc), status_code=getattr(exc, "code", None)
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_client(self) -> None:
        """クライアントが初期化済みであることを確認する。"""
        if self._client is None:
            raise AIKeyMissingError("API キーが設定されていません")

    @staticmethod
    def _log_usage_metadata(
        response: genai_types.GenerateContentResponse,
    ) -> None:
        """レスポンスの usage_metadata をログ出力する。

        キャッシュヒットの確認に使用。``cached_content_token_count`` が
        0 より大きければキャッシュが効いていることが分かる。
        """
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return
        logger.info(
            "usage_metadata: prompt_tokens=%s, cached_tokens=%s, candidates_tokens=%s",
            getattr(meta, "prompt_token_count", None),
            getattr(meta, "cached_content_token_count", None),
            getattr(meta, "candidates_token_count", None),
        )

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
        usage = AIModel._extract_usage_metadata(response)

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
                usage=usage,
            )
        # カスタムプロンプトモード
        return AnalysisResult(raw_response=raw_text, usage=usage)

    @staticmethod
    def _extract_usage_metadata(
        response: genai_types.GenerateContentResponse,
    ) -> AnalysisUsage | None:
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return None

        return AnalysisUsage(
            prompt_token_count=getattr(meta, "prompt_token_count", None),
            cached_content_token_count=getattr(
                meta, "cached_content_token_count", None
            ),
            candidates_token_count=getattr(meta, "candidates_token_count", None),
            total_token_count=getattr(meta, "total_token_count", None),
        )
