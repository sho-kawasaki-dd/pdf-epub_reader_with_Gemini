from __future__ import annotations

from pdf_epub_reader.dto import ModelInfo

from desktop_capture.adapters.ai_gateway import DesktopCaptureGeminiGateway
from desktop_capture.config import DesktopCaptureConfig


class FakeAIModel:
    def __init__(self) -> None:
        self.calls = []

    async def analyze(self, request):
        self.calls.append(request)
        return "result"

    async def list_available_models(self):
        self.calls.append("list_available_models")
        return [ModelInfo(model_id="models/gemini-test", display_name="Gemini Test")]


async def test_ai_gateway_forwards_analyze_requests() -> None:
    ai_model = FakeAIModel()
    gateway = DesktopCaptureGeminiGateway(ai_model)  # type: ignore[arg-type]

    result = await gateway.analyze("request")

    assert result == "result"
    assert ai_model.calls == ["request"]


async def test_ai_gateway_forwards_model_listing_requests() -> None:
    ai_model = FakeAIModel()
    gateway = DesktopCaptureGeminiGateway(ai_model)  # type: ignore[arg-type]

    result = await gateway.list_available_models()

    assert result == [
        ModelInfo(model_id="models/gemini-test", display_name="Gemini Test")
    ]
    assert ai_model.calls == ["list_available_models"]


def test_ai_gateway_from_config_bridges_desktop_capture_settings(monkeypatch) -> None:
    captured = {}

    class FakeModel:
        def __init__(self, api_key=None, config=None) -> None:
            captured["api_key"] = api_key
            captured["config"] = config

    monkeypatch.setattr("desktop_capture.adapters.ai_gateway.AIModel", FakeModel)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")

    gateway = DesktopCaptureGeminiGateway.from_config(
        DesktopCaptureConfig(
            gemini_model_name="gemini-2.5-flash",
            output_language="English",
            system_prompt="Prompt for {output_language}",
        )
    )

    assert isinstance(gateway, DesktopCaptureGeminiGateway)
    assert captured["api_key"] == "secret-key"
    assert captured["config"].gemini_model_name == "gemini-2.5-flash"
    assert captured["config"].output_language == "English"
    assert captured["config"].system_prompt_translation == "Prompt for {output_language}"