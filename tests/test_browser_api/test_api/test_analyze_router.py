from __future__ import annotations

from browser_api.application.dto import AnalyzeTranslateResult
from pdf_epub_reader.utils.exceptions import AIAPIError


# router が schema validation と HTTP error mapping を担うことを固定する suite。
def test_translate_returns_response_payload(api_client, stub_analyze_service) -> None:
    response = api_client.post(
        "/analyze/translate",
        json={
            "text": "Hello",
            "images": ["data:image/png;base64,QUJD"],
            "mode": "translation",
            "selection_metadata": {
                "url": "https://example.com",
                "page_title": "Example",
                "viewport_width": 1440,
                "viewport_height": 900,
                "device_pixel_ratio": 2,
                "rect": {
                    "left": 10,
                    "top": 20,
                    "width": 30,
                    "height": 40,
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["translated_text"] == "こんにちは"
    assert payload["availability"] == "live"
    assert payload["selection_metadata"]["url"] == "https://example.com"
    assert len(stub_analyze_service.calls) == 1
    command = stub_analyze_service.calls[0]
    assert command.text == "Hello"
    assert command.images == ["data:image/png;base64,QUJD"]
    assert command.selection_metadata["page_title"] == "Example"


def test_translate_accepts_custom_prompt_mode(api_client, stub_analyze_service) -> None:
    response = api_client.post(
        "/analyze/translate",
        json={
            "text": "Hello",
            "images": [],
            "mode": "custom_prompt",
            "custom_prompt": "Summarize this",
        },
    )

    assert response.status_code == 200
    command = stub_analyze_service.calls[0]
    assert command.mode == "custom_prompt"
    assert command.custom_prompt == "Summarize this"


def test_translate_accepts_image_only_requests(api_client, stub_analyze_service) -> None:
    response = api_client.post(
        "/analyze/translate",
        json={
            "text": "",
            "images": ["data:image/png;base64,QUJD"],
            "mode": "translation",
            "selection_metadata": {
                "items": [
                    {
                        "id": "selection-1",
                        "order": 0,
                        "source": "free-rectangle",
                        "text": "",
                        "include_image": True,
                        "image_index": 0,
                    }
                ]
            },
        },
    )

    assert response.status_code == 200
    command = stub_analyze_service.calls[0]
    assert command.text == ""
    assert command.images == ["data:image/png;base64,QUJD"]
    assert command.selection_metadata["items"][0]["source"] == "free-rectangle"


def test_translate_rejects_custom_prompt_mode_without_prompt(api_client) -> None:
    response = api_client.post(
        "/analyze/translate",
        json={
            "text": "Hello",
            "images": [],
            "mode": "custom_prompt",
        },
    )

    assert response.status_code == 422


def test_translate_returns_400_for_missing_model(api_client, stub_analyze_service) -> None:
    stub_analyze_service.error = ValueError("placeholder")
    from browser_api.application.errors import MissingModelError

    stub_analyze_service.error = MissingModelError("model_name is required")

    response = api_client.post(
        "/analyze/translate",
        json={
            "text": "Hello",
            "images": [],
            "mode": "translation",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "model_name is required"


def test_translate_maps_ai_errors_to_http_status(api_client, stub_analyze_service) -> None:
    stub_analyze_service.error = AIAPIError("Gemini upstream failed", status_code=503)

    response = api_client.post(
        "/analyze/translate",
        json={
            "text": "Hello",
            "images": [],
            "mode": "translation",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Gemini upstream failed"


def test_translate_rejects_empty_text(api_client, stub_analyze_service) -> None:
    stub_analyze_service.result = AnalyzeTranslateResult(
        mode="translation",
        translated_text="unused",
        explanation=None,
        raw_response="unused",
        used_mock=False,
        image_count=0,
        availability="live",
        degraded_reason=None,
        selection_metadata=None,
    )

    response = api_client.post(
        "/analyze/translate",
        json={
            "text": "",
            "images": [],
            "mode": "translation",
        },
    )

    assert response.status_code == 422


def test_translate_serializes_batch_metadata(api_client, stub_analyze_service) -> None:
    response = api_client.post(
        "/analyze/translate",
        json={
            "text": "1. First\n\n2. Second",
            "images": ["data:image/png;base64,QUJD"],
            "mode": "translation_with_explanation",
            "selection_metadata": {
                "url": "https://example.com",
                "page_title": "Example",
                "items": [
                    {
                        "id": "selection-1",
                        "order": 0,
                        "source": "text-selection",
                        "text": "First",
                        "include_image": False,
                        "image_index": None,
                    },
                    {
                        "id": "selection-2",
                        "order": 1,
                        "source": "free-rectangle",
                        "text": "Second",
                        "include_image": True,
                        "image_index": 0,
                    },
                ],
            },
        },
    )

    assert response.status_code == 200
    command = stub_analyze_service.calls[0]
    assert command.selection_metadata["items"][1]["image_index"] == 0
    assert command.selection_metadata["page_title"] == "Example"