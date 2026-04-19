from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

from browser_api.adapters.ai_gateway import GemReadAIGateway
from browser_api.application.dto import (
    CacheCreateCommand,
    CacheDeleteResult,
    CacheStatusResult,
    AnalyzeUsageMetrics,
    AnalyzeTranslateCommand,
    AnalyzeTranslateResult,
    ModelCatalogResult,
    TokenCountCommand,
    TokenCountResult,
)
from browser_api.application.errors import (
    InvalidImagePayloadError,
    MissingModelError,
    UnsupportedCacheModelError,
)
from pdf_epub_reader.dto import AnalysisMode, AnalysisRequest, CacheStatus, ModelInfo
from pdf_epub_reader.utils.config import AppConfig
from pdf_epub_reader.utils.exceptions import AICacheError, AIAPIError, AIKeyMissingError

logger = logging.getLogger(__name__)
_IMAGE_ONLY_PLACEHOLDER = "[image-only selection]"


@dataclass(slots=True)
class AnalyzeService:
    """Coordinate browser_api analyze flows without leaking HTTP or legacy model details.

    router は request/response 変換だけに留め、model 解決、画像 decode、mock fallback といった
    browser-extension 固有の振る舞いはこの service に集約する。

    Prompt-body mapping strategy
    ----------------------------
    ブラウザ拡張の公開アクションモード（``translation`` /
    ``translation_with_explanation`` / ``custom_prompt``）は外部コントラクトとして
    そのまま存続する。``_build_ai_request()`` がそれらを ``AnalysisRequest`` に
    マッピングし、AIModel の ``_build_contents()`` がモード別タスク記述と
    ``output_language`` をリクエスト本文の先頭プロンプトヘッダーに変換する。
    モード固有のシステム指示は一切壁の外に出ないため、アーティクルキャッシュは
    モード切替・言語変更時に再作成不要である。
    """

    ai_gateway: GemReadAIGateway
    config: AppConfig

    async def analyze_translate(
        self,
        command: AnalyzeTranslateCommand,
    ) -> AnalyzeTranslateResult:
        """Run a translation-like action and normalize the result for the browser extension."""

        resolved_model_name = self._resolve_model_name(command.model_name)
        image_bytes = self._decode_image_payloads(command.images)
        ai_request = self._build_ai_request(
            command=command,
            resolved_model_name=resolved_model_name,
            image_bytes=image_bytes,
        )

        try:
            result = await self.ai_gateway.analyze(ai_request)
            return AnalyzeTranslateResult(
                mode=command.mode,
                translated_text=result.translated_text or result.raw_response,
                explanation=result.explanation,
                raw_response=result.raw_response,
                used_mock=False,
                image_count=len(image_bytes),
                availability="live",
                selection_metadata=command.selection_metadata,
                usage=self._to_usage_metrics(result.usage),
            )
        except AIKeyMissingError:
            # API key 未設定でも extension 側の結線確認は進めたいので、mock で degraded success を返す。
            logger.info(
                "GEMINI_API_KEY is not configured; returning mock response for browser API validation"
            )
            return self._build_mock_response(command, len(image_bytes))

    async def list_models(self) -> ModelCatalogResult:
        """Return live model data when possible, otherwise fall back to configured model names."""

        try:
            models = await self.ai_gateway.list_available_models()
            return ModelCatalogResult(
                models=models,
                source="live",
                availability="live",
            )
        except AIKeyMissingError:
            # popup はモデル一覧取得失敗だけで全体を unusable にしないため、設定値から候補を組み立てる。
            logger.info(
                "GEMINI_API_KEY is not configured; returning configured model fallback"
            )
            return ModelCatalogResult(
                models=self._build_config_fallback_models(),
                source="config_fallback",
                availability="degraded",
                detail="GEMINI_API_KEY is not configured. Returning configured models only.",
                degraded_reason="mock-response",
            )
        except AIAPIError as exc:
            logger.warning("Failed to fetch live Gemini model list: %s", exc.message)
            return ModelCatalogResult(
                models=self._build_config_fallback_models(),
                source="config_fallback",
                availability="degraded",
                detail=(
                    "Failed to fetch live Gemini model list. Returning configured models only. "
                    f"Upstream message: {exc.message}"
                ),
                degraded_reason="config-fallback",
            )

    async def count_tokens(
        self,
        command: TokenCountCommand,
    ) -> TokenCountResult:
        """Count tokens for a candidate text payload using the resolved Gemini model."""

        resolved_model_name = self._resolve_model_name(command.model_name)
        token_count = await self.ai_gateway.count_tokens(
            command.text,
            model_name=resolved_model_name,
        )
        return TokenCountResult(
            token_count=token_count,
            model_name=resolved_model_name,
        )

    async def create_cache(
        self,
        command: CacheCreateCommand,
    ) -> CacheStatusResult:
        """Create a context cache using the resolved Gemini model and normalize the result."""

        resolved_model_name = self._resolve_model_name(command.model_name)
        try:
            status = await self.ai_gateway.create_cache(
                command.full_text,
                model_name=resolved_model_name,
                display_name=command.display_name,
            )
        except AICacheError as exc:
            if self._is_unsupported_cache_model_error(exc):
                raise UnsupportedCacheModelError(str(exc)) from exc
            raise

        return self._to_cache_status_result(status)

    async def get_cache_status(self) -> CacheStatusResult:
        """Return the currently active cache status from the AI gateway."""

        status = await self.ai_gateway.get_cache_status()
        return self._to_cache_status_result(status)

    async def delete_cache(self, cache_name: str) -> CacheDeleteResult:
        """Delete a named cache and return a stable acknowledgement payload."""

        await self.ai_gateway.delete_cache(cache_name)
        return CacheDeleteResult(cache_name=cache_name)

    @staticmethod
    def _to_usage_metrics(usage) -> AnalyzeUsageMetrics | None:
        if usage is None:
            return None

        return AnalyzeUsageMetrics(
            prompt_token_count=usage.prompt_token_count,
            cached_content_token_count=usage.cached_content_token_count,
            candidates_token_count=usage.candidates_token_count,
            total_token_count=usage.total_token_count,
        )

    def _build_ai_request(
        self,
        *,
        command: AnalyzeTranslateCommand,
        resolved_model_name: str,
        image_bytes: list[bytes],
    ) -> AnalysisRequest:
        """Map browser_api actions onto the legacy AnalysisRequest contract.

        ``custom_prompt`` → ``AnalysisMode.CUSTOM_PROMPT`` + ``custom_prompt`` フィールドに
        マッピングする。
        ``translation`` → ``AnalysisMode.TRANSLATION``（``include_explanation=False``）。
        ``translation_with_explanation`` → ``AnalysisMode.TRANSLATION``（``include_explanation=True``）。

        モード固有の ``system_instruction`` は一切生成しない。アクションモードの
        指示と ``output_language`` は AIModel の ``_build_contents()`` がリクエスト
        本文の先頭プロンプトヘッダーに変換するため、キャッシュキーに影響しない。
        """

        if command.mode == "custom_prompt":
            return AnalysisRequest(
                text=command.text,
                mode=AnalysisMode.CUSTOM_PROMPT,
                custom_prompt=command.custom_prompt,
                images=image_bytes,
                model_name=resolved_model_name,
            )

        return AnalysisRequest(
            text=command.text,
            mode=AnalysisMode.TRANSLATION,
            include_explanation=command.mode == "translation_with_explanation",
            images=image_bytes,
            model_name=resolved_model_name,
        )

    def _resolve_model_name(self, requested_model_name: str | None) -> str:
        """Prefer per-request model overrides, then fall back to configured defaults."""

        model_name = (requested_model_name or self.config.gemini_model_name).strip()
        if not model_name:
            raise MissingModelError(
                "model_name is required. Configure a Gemini model before calling the browser API."
            )
        return model_name

    def _decode_image_payloads(self, images: list[str]) -> list[bytes]:
        """Decode data URL or raw base64 image payloads before they reach the AI gateway."""

        decoded_images: list[bytes] = []
        for image in images:
            # browser-extension は data URL を送るので、metadata prefix を剥がしてから decode する。
            payload = image.split(",", 1)[1] if image.startswith("data:") else image
            try:
                decoded_images.append(base64.b64decode(payload))
            except ValueError as exc:
                raise InvalidImagePayloadError("Invalid image payload.") from exc
        return decoded_images

    def _build_config_fallback_models(self) -> list[ModelInfo]:
        """Collapse configured model names into a stable deduplicated fallback list."""

        names: list[str] = []
        for candidate in [self.config.gemini_model_name, *self.config.selected_models]:
            normalized = candidate.strip()
            if normalized and normalized not in names:
                names.append(normalized)

        return [
            ModelInfo(model_id=name, display_name=name)
            for name in names
        ]

    def _build_mock_response(
        self,
        command: AnalyzeTranslateCommand,
        image_count: int,
    ) -> AnalyzeTranslateResult:
        """Return a deterministic mock payload so UI and transport can be validated without Gemini credentials."""

        display_text = command.text.strip() or _IMAGE_ONLY_PLACEHOLDER

        if command.mode == "custom_prompt":
            translated_text = f"[mock: custom_prompt] {display_text}"
            raw_response = (
                f"{translated_text}\n\n---\n\nPrompt: {command.custom_prompt or '(empty)'}"
            )
            explanation = None
        else:
            prefix = (
                "[mock: explanation]"
                if command.mode == "translation_with_explanation"
                else "[mock: translation]"
            )
            translated_text = f"{prefix} {display_text}"
            explanation = None
            raw_response = translated_text
            if command.mode == "translation_with_explanation":
                explanation = (
                    "Mock explanation: FastAPI is reachable, screenshot payload was accepted, "
                    "and the extension flow can continue."
                )
                raw_response = f"{translated_text}\n\n---\n\n{explanation}"

        return AnalyzeTranslateResult(
            mode=command.mode,
            translated_text=translated_text,
            explanation=explanation,
            raw_response=raw_response,
            used_mock=True,
            image_count=image_count,
            availability="mock",
            degraded_reason="mock-response",
            selection_metadata=command.selection_metadata,
        )

    @staticmethod
    def _to_cache_status_result(status: CacheStatus) -> CacheStatusResult:
        return CacheStatusResult(
            is_active=status.is_active,
            ttl_seconds=status.ttl_seconds,
            token_count=status.token_count,
            cache_name=status.cache_name,
            display_name=status.display_name,
            model_name=status.model_name,
            expire_time=status.expire_time,
        )

    @staticmethod
    def _is_unsupported_cache_model_error(error: AICacheError) -> bool:
        normalized = str(error).lower()
        return (
            "サポートしていません" in str(error)
            or "not support" in normalized
            or "not supported for createcachedcontent" in normalized
        )