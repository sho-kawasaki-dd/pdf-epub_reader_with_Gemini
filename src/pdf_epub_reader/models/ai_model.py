"""AI 解析 Model — google-genai SDK を用いた Gemini API 連携。

Presenter からは ``await ai_model.analyze(request)`` の形で呼び出される。
API キー未設定でもインスタンス化は可能だが、API 呼び出し時に
``AIKeyMissingError`` を送出する（ドキュメント閲覧専用利用を妨げない）。

Context Caching は google-genai SDK の Explicit Caching API で実装。
キャッシュが active かつモデル一致時に ``analyze()`` で ``cached_content``
パラメータを自動付与し、失敗時はキャッシュなしでフォールバックする。

Prompt-body strategy
--------------------
``system_instruction`` には完全に静的・言語非依存のルール（Markdown 出力・
LaTeX 数式・``\\ce{}`` 化学式）のみを含める。この指示は ``create_cache()``
でキャッシュ作成時に一度だけ埋め込まれる。

Gemini API はキャッシュ付き ``GenerateContent`` リクエストへの
``system_instruction`` 付与を禁じるため、``analyze()`` のキャッシュ使用時パスでは
``GenerateContentConfig`` に ``system_instruction`` を含めない。

アクションモードの違い（``translation`` / ``translation_with_explanation`` /
``custom_prompt``）および ``output_language`` はすべて ``_build_contents()``
が生成するリクエスト本文の先頭プロンプトヘッダーに埋め込まれる。これにより
キャッシュキーはアーティクル本文 + モデルのみとなり、モード切替・言語変更時に
キャッシュを再作成する必要がない。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
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

# キャッシュ作成時・非キャッシュリクエスト時に共通で使うフォーマット指示。
# 完全に静的・言語非依存なルールのみを含む。
# Gemini API はキャッシュ付きリクエストに system_instruction を含めることを禁じるため、
# この指示はキャッシュ作成時に一度だけ埋め込む。
_STATIC_SYSTEM_INSTRUCTION = (
    "Output the response in Markdown format.\n"
    "- Write mathematical expressions using LaTeX notation ($...$ or $$...$$).\n"
    "- Write chemical formulas using the LaTeX \\ce{} command."
)

_PLOTLY_JSON_REQUEST_INSTRUCTION = (
    "If the response contains data or formulas that can be visualized, "
    "output the Plotly figure specification as a JSON fenced code block "
    "(```json ... ```). Provide only the pure JSON; do not include Python "
    "execution code."
)

_PLOTLY_PYTHON_REQUEST_INSTRUCTION = (
    "When visualizing data, provide a self-contained Python script in a "
    "```python``` fenced code block. The script MUST strictly adhere to these "
    "rules:\n"
    "1. Allowed imports: only plotly, numpy, pandas, scipy, sympy, math, "
    "statistics, datetime, json.\n"
    "2. Define a Plotly figure object and assign it to a variable named exactly 'fig'.\n"
    "3. The script MUST end by writing the JSON representation of the figure to "
    "standard output exactly like this: print(fig.to_json())\n"
    "4. Generate synthetic data or embed data directly in the script. Do not "
    "reference local files, network resources, or any modules outside the allowed list."
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
        ``cached_content`` パラメータを自動付与する。Gemini API はキャッシュ付き
        リクエストへの ``system_instruction`` 付与を禁じるため、キャッシュ使用時
        パスでは ``GenerateContentConfig`` に ``system_instruction`` を含めない
        （キャッシュ作成時に埋め込み済みの静的指示が自動適用される）。

        アクションモードの違い（translation / translation_with_explanation /
        custom_prompt）と ``output_language`` は ``_build_contents()`` が生成する
        プロンプトヘッダーに埋め込まれるため、モード切替・言語変更はキャッシュを
        再作成しない。

        キャッシュ付きリクエストが非レートリミットエラーで失敗した場合はキャッシュを
        内部クリアし、``system_instruction`` を含む ``GenerateContentConfig`` で
        キャッシュなし 1 回リトライする。

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
        contents = self._build_contents(request)

        explicit_cache_name = request.cache_name.strip() if request.cache_name else None
        active_internal_cache_name = (
            self._cache_name
            if self._cache_name is not None and self._cache_model == model_name
            else None
        )
        cache_name = explicit_cache_name or active_internal_cache_name
        use_explicit_cache = explicit_cache_name is not None
        use_cache = cache_name is not None
        cache_request_attempted = use_cache
        cache_request_failed = False
        cache_fallback_reason: str | None = None

        if use_cache:
            # system_instruction はキャッシュ作成時に埋め込み済み。
            # Gemini API はキャッシュ付きリクエストに system_instruction を
            # 同時に指定することを禁じるため、config には含めない。
            config = genai_types.GenerateContentConfig(
                cached_content=cache_name,
            )
            try:
                response = await self._call_with_retry(
                    model_name, contents, config
                )
            except AIRateLimitError:
                raise
            except AIAPIError as exc:
                # キャッシュ付きリクエスト失敗 → キャッシュを内部クリアし
                # キャッシュなしで 1 回リトライ
                cache_request_failed = True
                cache_fallback_reason = self._normalize_cache_fallback_reason(exc)
                logger.warning(
                    "キャッシュ付きリクエスト失敗、キャッシュなしでリトライ: "
                    "status_code=%s cache_name=%s cache_model=%s request_model=%s message=%s",
                    exc.status_code,
                    cache_name,
                    self._cache_model,
                    model_name,
                    exc.message,
                )
                if not use_explicit_cache:
                    self._cache_name = None
                    self._cache_model = None
                config = genai_types.GenerateContentConfig(
                    system_instruction=self._build_system_instruction(),
                )
                response = await self._call_with_retry(
                    model_name, contents, config
                )
        else:
            config = genai_types.GenerateContentConfig(
                system_instruction=self._build_system_instruction(),
            )
            response = await self._call_with_retry(
                model_name, contents, config
            )

        # usage_metadata ログ出力
        self._log_usage_metadata(response)

        return self._parse_response(
            request,
            response,
            cache_request_attempted=cache_request_attempted,
            cache_request_failed=cache_request_failed,
            cache_fallback_reason=cache_fallback_reason,
        )

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

        ``output_language`` または ``system_prompt_translation`` が変わった場合は
        キャッシュを無効化する。``output_language`` は contents に埋め込まれるため
        キャッシュキー自体には影響しないが、変更後の言語設定を即座に反映させる
        ため旧キャッシュセッションをクリアする。
        """
        should_invalidate = (
            config.output_language != self._config.output_language
            or config.system_prompt_translation != self._config.system_prompt_translation
        )
        self._config = config
        if should_invalidate:
            await self.invalidate_cache()

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
            return result.total_tokens or 0
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

        静的なフォーマット指示（``_STATIC_SYSTEM_INSTRUCTION``）をキャッシュに
        一度だけ埋め込む。出力言語やモード固有のタスク指示は request の
        contents 側に含めるため、キャッシュは article body + model だけで
        キーイングされ、モード切替・言語変更時に再作成不要となる。

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
                    system_instruction=self._build_system_instruction(),
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
                expire_time=self._format_expire_time(cache.expire_time),
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
            normalized_expire_time = self._normalize_expire_time(cache.expire_time)
            if normalized_expire_time:
                now = datetime.now(timezone.utc)
                if normalized_expire_time <= now:
                    self._cache_name = None
                    self._cache_model = None
                    return CacheStatus(is_active=False)

            ttl_seconds = None
            if normalized_expire_time:
                remaining = (
                    normalized_expire_time - datetime.now(timezone.utc)
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
                expire_time=self._format_expire_time(cache.expire_time),
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
                expire_time=self._format_expire_time(cache.expire_time),
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
                    expire_time=self._format_expire_time(cache.expire_time),
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
    def _normalize_expire_time(expire_time: datetime | None) -> datetime | None:
        """Expire time を UTC aware datetime に正規化する。"""
        if expire_time is None:
            return None

        if expire_time.tzinfo is None or expire_time.utcoffset() is None:
            return expire_time.replace(tzinfo=timezone.utc)

        return expire_time.astimezone(timezone.utc)

    @classmethod
    def _format_expire_time(cls, expire_time: datetime | None) -> str | None:
        """Expire time を UTC offset 付き ISO 8601 文字列に整形する。"""
        normalized = cls._normalize_expire_time(expire_time)
        return normalized.isoformat() if normalized else None

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

    @staticmethod
    def _build_system_instruction() -> str:
        """完全に静的な言語非依存のフォーマット指示を返す。

        Markdown 出力・LaTeX 数式記法・化学式 ``\\ce{}`` ルールのみを含む。
        この指示は ``create_cache()`` でキャッシュ作成時に一度だけ埋め込まれ、
        キャッシュ付きリクエスト（``analyze()`` の ``use_cache=True`` パス）では
        ``GenerateContentConfig`` に含めてはならない。
        非キャッシュリクエストでは ``GenerateContentConfig`` に直接渡す。
        """
        return _STATIC_SYSTEM_INSTRUCTION

    def _build_contents(
        self,
        request: AnalysisRequest,
    ) -> list[genai_types.Part | str]:
        """リクエストから API に送る contents リストを組み立てる。

        先頭のプロンプトヘッダーに出力言語の明示とモード別タスク指示を含む
        プロンプトボディエンベロープを配置し、続いて選択テキスト・画像を追加する。

        - ``TRANSLATION`` (``include_explanation=False``): 翻訳タスクのみ
        - ``TRANSLATION`` (``include_explanation=True``): 翻訳タスク + ``---`` 区切り解説指示
        - ``CUSTOM_PROMPT``: 出力言語指示 + ``USER_CONTEXT`` + ``USER_TASK`` セクション
        """
        output_language = self._config.output_language
        parts: list[genai_types.Part | str] = []

        if request.mode == AnalysisMode.CUSTOM_PROMPT:
            user_task = request.custom_prompt or ""
            user_context = request.system_prompt
            prompt_header = (
                f"Respond in {output_language}.\n\n"
                + (
                    f"USER_CONTEXT:\n{user_context}\n\n"
                    if user_context
                    else ""
                )
                + f"USER_TASK:\n{user_task}\n\n"
                f"Apply the task only to the text enclosed in <selection> tags below."
            )
        else:
            translation_prompt = (
                request.system_prompt
                if request.system_prompt is not None
                else self._config.system_prompt_translation
            )
            translation_task = self._resolve_translation_prompt(
                translation_prompt,
                output_language=output_language,
            )
            if request.include_explanation:
                translation_task += DEFAULT_EXPLANATION_ADDENDUM
            prompt_header = (
                f"Respond in {output_language}.\n\n"
                f"{translation_task}\n\n"
                f"Translate only the text enclosed in <selection> tags below. "
                f"You may use the article context to inform terminology and style, "
                f"but your output must contain only the translation of the selected text."
            )

        if request.request_plotly_mode == "json":
            # Phase 1 互換の JSON-only 指示を追加する。
            prompt_header = (
                f"{prompt_header}\n\n{_PLOTLY_JSON_REQUEST_INSTRUCTION}"
            )
        elif request.request_plotly_mode == "python":
            # Phase 2 では Python スクリプト生成を要求し、runner 側は
            # 末尾の `print(fig.to_json())` 出力を stdout から拾う。
            prompt_header = (
                f"{prompt_header}\n\n{_PLOTLY_PYTHON_REQUEST_INSTRUCTION}"
            )

        # プロンプトヘッダー（言語指示 + タスク指示）
        parts.append(prompt_header)

        # 選択テキスト（キャッシュ内の記事全文と混同しないよう境界タグで囲む）
        parts.append(f"<selection>\n{request.text}\n</selection>")

        # マルチモーダル画像
        for image_bytes in request.images:
            parts.append(
                genai_types.Part.from_bytes(
                    data=image_bytes, mime_type="image/png"
                )
            )

        return parts

    @staticmethod
    def _resolve_translation_prompt(
        prompt: str,
        *,
        output_language: str,
    ) -> str:
        """Expand the supported output-language token without treating other braces as format syntax."""

        return prompt.replace("{output_language}", output_language)

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
        *,
        cache_request_attempted: bool = False,
        cache_request_failed: bool = False,
        cache_fallback_reason: str | None = None,
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
                cache_request_attempted=cache_request_attempted,
                cache_request_failed=cache_request_failed,
                cache_fallback_reason=cache_fallback_reason,
            )
        # カスタムプロンプトモード
        return AnalysisResult(
            raw_response=raw_text,
            usage=usage,
            cache_request_attempted=cache_request_attempted,
            cache_request_failed=cache_request_failed,
            cache_fallback_reason=cache_fallback_reason,
        )

    @staticmethod
    def _normalize_cache_fallback_reason(error: AIAPIError) -> str:
        status_code = error.status_code
        if status_code == 400:
            return "bad-request"
        if status_code == 403:
            return "permission-denied"
        if status_code == 404:
            return "not-found"
        if status_code is not None:
            return f"upstream-{status_code}"
        return "upstream-error"

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
