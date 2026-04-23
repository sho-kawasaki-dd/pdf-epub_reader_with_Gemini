"""AI gateway adapter for desktop_capture."""

from __future__ import annotations

import os

from pdf_epub_reader.dto.ai_dto import AnalysisRequest, AnalysisResult
from pdf_epub_reader.models.ai_model import AIModel
from pdf_epub_reader.utils.config import AppConfig, ENV_GEMINI_API_KEY

from desktop_capture.config import DesktopCaptureConfig


class DesktopCaptureGeminiGateway:
    """Bridge desktop_capture use cases to the existing AIModel."""

    def __init__(self, ai_model: AIModel) -> None:
        self._ai_model = ai_model

    @classmethod
    def from_config(cls, config: DesktopCaptureConfig) -> DesktopCaptureGeminiGateway:
        ai_config = AppConfig(
            gemini_model_name=config.gemini_model_name,
            output_language=config.output_language,
            system_prompt_translation=config.system_prompt,
        )
        ai_model = AIModel(
            api_key=os.environ.get(ENV_GEMINI_API_KEY),
            config=ai_config,
        )
        return cls(ai_model)

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        return await self._ai_model.analyze(request)