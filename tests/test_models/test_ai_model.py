"""AIModel のユニットテスト。

google.genai SDK を mock.patch で差し替え、AIModel の各メソッドが
正しく SDK を呼び出し、例外を適切にラップすることを検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pdf_epub_reader.dto import AnalysisMode, AnalysisRequest, ModelInfo
from pdf_epub_reader.models.ai_model import (
    AIModel,
    _CUSTOM_PROMPT_SYSTEM_TEMPLATE,
    _MAX_RETRIES,
)
from pdf_epub_reader.utils.config import AppConfig, DEFAULT_TRANSLATION_PROMPT, DEFAULT_EXPLANATION_ADDENDUM
from pdf_epub_reader.utils.exceptions import (
    AIAPIError,
    AIKeyMissingError,
    AIRateLimitError,
)


# ---------------------------------------------------------------------------
# ヘルパー: google.genai の mock を組み立てるファクトリ
# ---------------------------------------------------------------------------


def _make_mock_response(text: str = "Mock AI response") -> MagicMock:
    """generate_content が返すレスポンスオブジェクトの Mock。"""
    resp = MagicMock()
    resp.text = text
    return resp


def _make_api_error(code: int = 400, message: str = "Bad Request") -> Exception:
    """genai.errors.APIError 互換の例外を作るヘルパー。

    テスト内で実際の google.genai をインポートせずに済むよう、
    code 属性を持つ汎用 Exception を返す。
    """
    exc = Exception(message)
    exc.code = code
    return exc


def _build_model(api_key: str = "test-key", **config_kw) -> AIModel:
    """AIModel を生成するショートカット。genai.Client をモック化する。"""
    config = AppConfig(**config_kw)
    with patch("pdf_epub_reader.models.ai_model.genai") as mock_genai:
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        model = AIModel(api_key=api_key, config=config)
    # テスト側で client の振る舞いを制御できるようにする
    model._client = mock_client
    return model


# ======================================================================
# テストクラス群
# ======================================================================


class TestConstructor:
    """AIModel コンストラクタの振る舞いを検証する。"""

    def test_api_key_none_creates_no_client(self) -> None:
        """API キー未設定ではクライアントが None であること。"""
        model = AIModel(api_key=None)
        assert model._client is None

    def test_api_key_empty_string_creates_no_client(self) -> None:
        """空文字列もキー未設定とみなされること。"""
        model = AIModel(api_key="")
        assert model._client is None

    def test_api_key_provided_creates_client(self) -> None:
        """キーが設定されるとクライアントが生成されること。"""
        with patch("pdf_epub_reader.models.ai_model.genai") as mock_genai:
            model = AIModel(api_key="real-key")
        mock_genai.Client.assert_called_once_with(api_key="real-key")
        assert model._client is not None


class TestAnalyzeTranslation:
    """analyze() の翻訳モード動作を検証する。"""

    @pytest.mark.asyncio
    async def test_translation_calls_api_with_system_instruction(self) -> None:
        """翻訳モードで system_prompt_translation が使われること。"""
        model = _build_model()
        mock_response = _make_mock_response("翻訳結果")
        model._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        request = AnalysisRequest(
            text="Hello world",
            mode=AnalysisMode.TRANSLATION,
        )
        result = await model.analyze(request)

        # API が呼ばれた
        model._client.aio.models.generate_content.assert_awaited_once()
        call_kwargs = model._client.aio.models.generate_content.call_args
        # model_name がデフォルト
        assert call_kwargs.kwargs["model"] == AppConfig().gemini_model_name
        # system_instruction にデフォルト翻訳プロンプトが使われている
        config = call_kwargs.kwargs["config"]
        expected_instruction = DEFAULT_TRANSLATION_PROMPT.format(
            output_language="日本語"
        )
        assert config.system_instruction == expected_instruction
        # 結果
        assert result.translated_text == "翻訳結果"

    @pytest.mark.asyncio
    async def test_translation_result_has_no_explanation(self) -> None:
        """翻訳モードでは explanation が None であること。"""
        model = _build_model()
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("text")
        )

        request = AnalysisRequest(
            text="Hello",
            mode=AnalysisMode.TRANSLATION,
        )
        result = await model.analyze(request)
        assert result.explanation is None


class TestAnalyzeCustomPrompt:
    """analyze() のカスタムプロンプトモード動作を検証する。"""

    @pytest.mark.asyncio
    async def test_custom_prompt_uses_correct_system_instruction(self) -> None:
        """カスタムプロンプトモードで専用のシステム指示が使われること。"""
        model = _build_model(output_language="English")
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("answer")
        )

        request = AnalysisRequest(
            text="Explain this",
            mode=AnalysisMode.CUSTOM_PROMPT,
            custom_prompt="Summarize",
        )
        result = await model.analyze(request)

        call_kwargs = model._client.aio.models.generate_content.call_args
        config = call_kwargs.kwargs["config"]
        expected = _CUSTOM_PROMPT_SYSTEM_TEMPLATE.format(
            output_language="English"
        )
        assert config.system_instruction == expected
        assert result.raw_response == "answer"

    @pytest.mark.asyncio
    async def test_custom_prompt_included_in_contents(self) -> None:
        """カスタムプロンプトが contents の先頭に入ること。"""
        model = _build_model()
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("ok")
        )

        request = AnalysisRequest(
            text="Some text",
            mode=AnalysisMode.CUSTOM_PROMPT,
            custom_prompt="Summarize this",
        )
        await model.analyze(request)

        call_kwargs = model._client.aio.models.generate_content.call_args
        contents = call_kwargs.kwargs["contents"]
        assert contents[0] == "Summarize this"
        assert contents[1] == "Some text"


class TestAnalyzeMultimodal:
    """マルチモーダル（画像付き）解析を検証する。"""

    @pytest.mark.asyncio
    async def test_images_sent_as_parts(self) -> None:
        """images が Part.from_bytes で contents に追加されること。"""
        model = _build_model()
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("result")
        )

        request = AnalysisRequest(
            text="Math formula",
            mode=AnalysisMode.TRANSLATION,
            images=[b"png-data-1", b"png-data-2"],
        )
        await model.analyze(request)

        call_kwargs = model._client.aio.models.generate_content.call_args
        contents = call_kwargs.kwargs["contents"]
        # テキスト + 2 つの画像パート
        assert len(contents) == 3
        assert contents[0] == "Math formula"


class TestAnalyzeModelSpecification:
    """リクエスト単位のモデル指定を検証する。"""

    @pytest.mark.asyncio
    async def test_request_model_name_overrides_default(self) -> None:
        """request.model_name がデフォルトモデルより優先されること。"""
        model = _build_model()
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("ok")
        )

        request = AnalysisRequest(
            text="Hello",
            mode=AnalysisMode.TRANSLATION,
            model_name="gemini-2.0-flash",
        )
        await model.analyze(request)

        call_kwargs = model._client.aio.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemini-2.0-flash"

    @pytest.mark.asyncio
    async def test_none_model_name_uses_config_default(self) -> None:
        """model_name が None ならば config のデフォルトが使われること。"""
        model = _build_model(gemini_model_name="custom-model")
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("ok")
        )

        request = AnalysisRequest(
            text="Hello",
            mode=AnalysisMode.TRANSLATION,
            model_name=None,
        )
        await model.analyze(request)

        call_kwargs = model._client.aio.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "custom-model"


class TestKeyMissing:
    """API キー未設定時の動作を検証する。"""

    @pytest.mark.asyncio
    async def test_analyze_raises_key_missing(self) -> None:
        """キー未設定で analyze() を呼ぶと AIKeyMissingError になること。"""
        model = AIModel(api_key=None)
        request = AnalysisRequest(
            text="Hello", mode=AnalysisMode.TRANSLATION
        )
        with pytest.raises(AIKeyMissingError):
            await model.analyze(request)

    @pytest.mark.asyncio
    async def test_list_models_raises_key_missing(self) -> None:
        """キー未設定で list_available_models() を呼ぶと AIKeyMissingError になること。"""
        model = AIModel(api_key=None)
        with pytest.raises(AIKeyMissingError):
            await model.list_available_models()


class TestAPIError:
    """非リトライ対象の API エラーを検証する。"""

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self) -> None:
        """400 等のリトライ不可エラーは即座に AIAPIError になること。"""
        model = _build_model()
        exc = _make_api_error(code=400, message="Invalid request")
        # genai.errors.APIError のサブクラスとして認識させる
        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.generate_content = AsyncMock(
                side_effect=exc
            )

            request = AnalysisRequest(
                text="test", mode=AnalysisMode.TRANSLATION
            )
            with pytest.raises(AIAPIError) as exc_info:
                await model.analyze(request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_non_retryable_error_no_retry(self) -> None:
        """リトライ不可エラーでは API が 1 回だけ呼ばれること。"""
        model = _build_model()
        exc = _make_api_error(code=403, message="Forbidden")
        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.generate_content = AsyncMock(
                side_effect=exc
            )

            request = AnalysisRequest(
                text="test", mode=AnalysisMode.TRANSLATION
            )
            with pytest.raises(AIAPIError):
                await model.analyze(request)
            assert (
                model._client.aio.models.generate_content.await_count == 1
            )


class TestRetryLogic:
    """指数バックオフリトライの動作を検証する。"""

    @pytest.mark.asyncio
    async def test_retry_on_429_then_success(self) -> None:
        """429 でリトライし、2 回目で成功すること。"""
        model = _build_model()
        exc = _make_api_error(code=429, message="Rate limited")

        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.generate_content = AsyncMock(
                side_effect=[exc, _make_mock_response("success")]
            )

            with patch("pdf_epub_reader.models.ai_model.asyncio.sleep", new_callable=AsyncMock):
                request = AnalysisRequest(
                    text="test", mode=AnalysisMode.TRANSLATION
                )
                result = await model.analyze(request)

        assert result.translated_text == "success"
        assert model._client.aio.models.generate_content.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_500_then_success(self) -> None:
        """500 でリトライし、2 回目で成功すること。"""
        model = _build_model()
        exc = _make_api_error(code=500, message="Internal Server Error")

        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.generate_content = AsyncMock(
                side_effect=[exc, _make_mock_response("recovered")]
            )

            with patch("pdf_epub_reader.models.ai_model.asyncio.sleep", new_callable=AsyncMock):
                request = AnalysisRequest(
                    text="test", mode=AnalysisMode.TRANSLATION
                )
                result = await model.analyze(request)

        assert result.translated_text == "recovered"

    @pytest.mark.asyncio
    async def test_retry_limit_exceeded_raises_rate_limit(self) -> None:
        """429 が MAX_RETRIES 回続くと AIRateLimitError になること。"""
        model = _build_model()
        exc = _make_api_error(code=429, message="Rate limited")

        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.generate_content = AsyncMock(
                side_effect=[exc] * _MAX_RETRIES
            )

            with patch("pdf_epub_reader.models.ai_model.asyncio.sleep", new_callable=AsyncMock):
                request = AnalysisRequest(
                    text="test", mode=AnalysisMode.TRANSLATION
                )
                with pytest.raises(AIRateLimitError):
                    await model.analyze(request)

        assert (
            model._client.aio.models.generate_content.await_count
            == _MAX_RETRIES
        )

    @pytest.mark.asyncio
    async def test_retry_limit_exceeded_raises_api_error_for_5xx(self) -> None:
        """5xx が MAX_RETRIES 回続くと AIAPIError になること。"""
        model = _build_model()
        exc = _make_api_error(code=503, message="Service Unavailable")

        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.generate_content = AsyncMock(
                side_effect=[exc] * _MAX_RETRIES
            )

            with patch("pdf_epub_reader.models.ai_model.asyncio.sleep", new_callable=AsyncMock):
                request = AnalysisRequest(
                    text="test", mode=AnalysisMode.TRANSLATION
                )
                with pytest.raises(AIAPIError):
                    await model.analyze(request)

    @pytest.mark.asyncio
    async def test_backoff_sleep_times(self) -> None:
        """リトライ時の sleep 時間が指数的に増加すること。"""
        model = _build_model()
        exc = _make_api_error(code=429, message="Rate limited")

        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.generate_content = AsyncMock(
                side_effect=[exc] * _MAX_RETRIES
            )

            with patch(
                "pdf_epub_reader.models.ai_model.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep:
                request = AnalysisRequest(
                    text="test", mode=AnalysisMode.TRANSLATION
                )
                with pytest.raises(AIRateLimitError):
                    await model.analyze(request)

            # MAX_RETRIES=3: sleep(1.0), sleep(2.0) の 2 回
            # 最終試行後は sleep しない
            assert mock_sleep.await_count == _MAX_RETRIES - 1
            mock_sleep.assert_any_await(1.0)
            mock_sleep.assert_any_await(2.0)


class TestListAvailableModels:
    """list_available_models() の動作を検証する。"""

    @pytest.mark.asyncio
    async def test_returns_generate_content_models_only(self) -> None:
        """generateContent をサポートするモデルのみが返ること。"""
        model = _build_model()

        # 2 つのモデル: 1 つは generateContent 対応、1 つは非対応
        mock_model_ok = MagicMock()
        mock_model_ok.name = "models/gemini-pro"
        mock_model_ok.display_name = "Gemini Pro"
        mock_model_ok.supported_actions = ["generateContent", "countTokens"]

        mock_model_no = MagicMock()
        mock_model_no.name = "models/embedding-001"
        mock_model_no.display_name = "Embedding"
        mock_model_no.supported_actions = ["embedContent"]

        async def _fake_list():
            for m in [mock_model_ok, mock_model_no]:
                yield m

        # aio.models.list() が async iterator を返すようにする
        model._client.aio.models.list = AsyncMock(
            return_value=_fake_list()
        )

        result = await model.list_available_models()

        assert len(result) == 1
        assert result[0] == ModelInfo(
            model_id="models/gemini-pro", display_name="Gemini Pro"
        )

    @pytest.mark.asyncio
    async def test_list_models_api_error_wraps(self) -> None:
        """API エラーが AIAPIError にラップされること。"""
        model = _build_model()

        exc = _make_api_error(code=401, message="Unauthorized")
        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.list = AsyncMock(side_effect=exc)

            with pytest.raises(AIAPIError):
                await model.list_available_models()


class TestUpdateConfig:
    """update_config() の動作を検証する。"""

    def test_config_is_replaced(self) -> None:
        """update_config で内部設定が置き換わること。"""
        model = AIModel(api_key=None)
        old = model._config
        new_config = AppConfig(output_language="English")
        model.update_config(new_config)
        assert model._config is new_config
        assert model._config is not old

    @pytest.mark.asyncio
    async def test_updated_config_affects_system_instruction(self) -> None:
        """update_config 後に翻訳プロンプトが新しい output_language を使うこと。"""
        model = _build_model(output_language="日本語")
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("ok")
        )

        # config を English に切り替え
        model.update_config(AppConfig(output_language="English"))

        request = AnalysisRequest(
            text="Hello", mode=AnalysisMode.TRANSLATION
        )
        await model.analyze(request)

        call_kwargs = model._client.aio.models.generate_content.call_args
        config = call_kwargs.kwargs["config"]
        assert "English" in config.system_instruction


class TestExplanationMode:
    """解説付き翻訳モードのシステム指示とレスポンスパースを検証する。"""

    @pytest.mark.asyncio
    async def test_explanation_mode_adds_addendum_to_system_instruction(
        self,
    ) -> None:
        """include_explanation=True のとき、システム指示に addendum が追記されること。"""
        model = _build_model()
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("翻訳\n---\n解説")
        )

        request = AnalysisRequest(
            text="Hello",
            mode=AnalysisMode.TRANSLATION,
            include_explanation=True,
        )
        await model.analyze(request)

        call_kwargs = model._client.aio.models.generate_content.call_args
        config = call_kwargs.kwargs["config"]
        assert DEFAULT_EXPLANATION_ADDENDUM in config.system_instruction

    @pytest.mark.asyncio
    async def test_parse_response_splits_on_separator(self) -> None:
        """レスポンスが --- で正しく translated_text と explanation に分割されること。"""
        model = _build_model()
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("翻訳テキスト\n---\n用語解説部分")
        )

        request = AnalysisRequest(
            text="Hello",
            mode=AnalysisMode.TRANSLATION,
            include_explanation=True,
        )
        result = await model.analyze(request)

        assert result.translated_text == "翻訳テキスト"
        assert result.explanation == "用語解説部分"

    @pytest.mark.asyncio
    async def test_parse_response_no_separator_graceful(self) -> None:
        """--- 区切りが無い場合、全体を translated_text とし explanation=None になること。"""
        model = _build_model()
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("翻訳のみの結果")
        )

        request = AnalysisRequest(
            text="Hello",
            mode=AnalysisMode.TRANSLATION,
            include_explanation=True,
        )
        result = await model.analyze(request)

        assert result.translated_text == "翻訳のみの結果"
        assert result.explanation is None
