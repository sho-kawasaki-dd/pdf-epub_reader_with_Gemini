"""AIModel のユニットテスト。

google.genai SDK を mock.patch で差し替え、AIModel の各メソッドが
正しく SDK を呼び出し、例外を適切にラップすることを検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pdf_epub_reader.dto import AnalysisMode, AnalysisRequest, CacheStatus, ModelInfo
from pdf_epub_reader.models.ai_model import (
    AIModel,
    _MAX_RETRIES,
    _STATIC_SYSTEM_INSTRUCTION,
)
from pdf_epub_reader.utils.config import AppConfig, DEFAULT_TRANSLATION_PROMPT, DEFAULT_EXPLANATION_ADDENDUM
from pdf_epub_reader.utils.exceptions import (
    AICacheError,
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
        """翻訳モードで static system_instruction と contents の言語・タスク指示が使われること。"""
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
        # system_instruction は静的ルールのみ
        config = call_kwargs.kwargs["config"]
        assert config.system_instruction == _STATIC_SYSTEM_INSTRUCTION
        # 出力言語と翻訳タスクは contents[0] のプロンプトヘッダーに含まれる
        contents = call_kwargs.kwargs["contents"]
        assert "日本語" in contents[0]
        # 選択テキストは <selection> タグで囲まれる
        assert "Hello world" in contents[1]
        assert "<selection>" in contents[1]
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
        """カスタムプロンプトモードで static system_instruction と contents のユーザータスクが使われること。"""
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
        # system_instruction は静的ルールのみ
        assert config.system_instruction == _STATIC_SYSTEM_INSTRUCTION
        # 出力言語とユーザータスクは contents[0] に含まれる
        contents = call_kwargs.kwargs["contents"]
        assert "English" in contents[0]
        assert "USER_TASK" in contents[0]
        assert "Summarize" in contents[0]
        assert result.raw_response == "answer"

    @pytest.mark.asyncio
    async def test_custom_prompt_included_in_contents(self) -> None:
        """カスタムプロンプトが contents[0] のプロンプトヘッダー内に含まれ、選択テキストが contents[1] に入ること。"""
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
        # contents[0]: language enforcement + USER_TASK section
        assert "USER_TASK" in contents[0]
        assert "Summarize this" in contents[0]
        # contents[1]: selection text（<selection> タグで囲まれる）
        assert "Some text" in contents[1]
        assert "<selection>" in contents[1]


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
        # プロンプトヘッダー + テキスト + 2 つの画像パート
        assert len(contents) == 4
        assert "Math formula" in contents[1]
        assert "<selection>" in contents[1]


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

    @pytest.mark.asyncio
    async def test_config_is_replaced(self) -> None:
        """update_config で内部設定が置き換わること。"""
        model = AIModel(api_key=None)
        old = model._config
        new_config = AppConfig(output_language="English")
        await model.update_config(new_config)
        assert model._config is new_config
        assert model._config is not old

    @pytest.mark.asyncio
    async def test_updated_config_affects_contents_language(self) -> None:
        """update_config 後に contents[0] のプロンプトヘッダーが新しい output_language を使うこと。"""
        model = _build_model(output_language="日本語")
        model._client.aio.models.generate_content = AsyncMock(
            return_value=_make_mock_response("ok")
        )

        # config を English に切り替え
        await model.update_config(AppConfig(output_language="English"))

        request = AnalysisRequest(
            text="Hello", mode=AnalysisMode.TRANSLATION
        )
        await model.analyze(request)

        call_kwargs = model._client.aio.models.generate_content.call_args
        contents = call_kwargs.kwargs["contents"]
        # 出力言語は system_instruction ではなく contents[0] に含まれる
        assert "English" in contents[0]
        assert "日本語" not in contents[0]

    @pytest.mark.asyncio
    async def test_update_config_language_change_invalidates_cache(self) -> None:
        """output_language 変更時にキャッシュが無効化されること。"""
        model = _build_model(output_language="日本語")
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-test"
        model._client.aio.caches.delete = AsyncMock()

        await model.update_config(AppConfig(output_language="English"))

        model._client.aio.caches.delete.assert_awaited_once()
        assert model._cache_name is None

    @pytest.mark.asyncio
    async def test_update_config_same_language_does_not_invalidate_cache(self) -> None:
        """output_language が変わらない場合はキャッシュを維持すること。"""
        model = _build_model(output_language="日本語")
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-test"
        model._client.aio.caches.delete = AsyncMock()

        await model.update_config(AppConfig(output_language="日本語"))

        model._client.aio.caches.delete.assert_not_awaited()
        assert model._cache_name == "caches/test-123"


class TestExplanationMode:
    """解説付き翻訳モードのシステム指示とレスポンスパースを検証する。"""

    @pytest.mark.asyncio
    async def test_explanation_mode_adds_addendum_to_contents(
        self,
    ) -> None:
        """include_explanation=True のとき、addendum が contents[0] のプロンプトヘッダーに含まれること。"""
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
        contents = call_kwargs.kwargs["contents"]
        # addendum は system_instruction ではなく contents[0] に含まれる
        assert DEFAULT_EXPLANATION_ADDENDUM in contents[0]

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


# ======================================================================
# Phase 7: Context Caching テスト群
# ======================================================================


def _make_mock_cache(**overrides) -> MagicMock:
    """SDK が返すキャッシュオブジェクトの Mock を作る。"""
    cache = MagicMock()
    cache.name = overrides.get("name", "caches/test-cache-123")
    cache.model = overrides.get("model", "models/gemini-test")
    cache.display_name = overrides.get("display_name", "pdf-reader: test.pdf")
    cache.expire_time = overrides.get("expire_time", None)
    usage = MagicMock()
    usage.total_token_count = overrides.get("total_token_count", 5000)
    cache.usage_metadata = usage
    return cache


class TestCountTokens:
    """count_tokens() の動作を検証する。"""

    @pytest.mark.asyncio
    async def test_count_tokens_returns_total(self) -> None:
        """正常時にトークン数が返ること。"""
        model = _build_model()
        result_mock = MagicMock()
        result_mock.total_tokens = 42
        model._client.aio.models.count_tokens = AsyncMock(
            return_value=result_mock
        )

        count = await model.count_tokens("Hello world")

        assert count == 42
        model._client.aio.models.count_tokens.assert_awaited_once()
        call_kw = model._client.aio.models.count_tokens.call_args
        assert call_kw.kwargs["contents"] == "Hello world"

    @pytest.mark.asyncio
    async def test_count_tokens_with_model_name(self) -> None:
        """model_name を指定するとそのモデルが使われること。"""
        model = _build_model()
        result_mock = MagicMock()
        result_mock.total_tokens = 10
        model._client.aio.models.count_tokens = AsyncMock(
            return_value=result_mock
        )

        await model.count_tokens("text", model_name="custom-model")

        call_kw = model._client.aio.models.count_tokens.call_args
        assert call_kw.kwargs["model"] == "custom-model"

    @pytest.mark.asyncio
    async def test_count_tokens_api_error_wraps(self) -> None:
        """API エラーが AIAPIError にラップされること。"""
        model = _build_model()
        exc = _make_api_error(code=400, message="Bad Request")
        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.count_tokens = AsyncMock(
                side_effect=exc
            )
            with pytest.raises(AIAPIError):
                await model.count_tokens("text")


class TestCreateCache:
    """create_cache() の動作を検証する。"""

    @pytest.mark.asyncio
    async def test_create_cache_success(self) -> None:
        """正常時に CacheStatus(is_active=True) が返り、内部状態が設定されること。"""
        model = _build_model()
        mock_cache = _make_mock_cache()
        model._client.aio.caches.create = AsyncMock(
            return_value=mock_cache
        )

        status = await model.create_cache(
            "full text", display_name="pdf-reader: test.pdf"
        )

        assert status.is_active is True
        assert status.cache_name == "caches/test-cache-123"
        assert status.display_name == "pdf-reader: test.pdf"
        assert status.model_name == "models/gemini-test"
        assert status.token_count == 5000
        assert model._cache_name == "caches/test-cache-123"
        assert model._cache_model == "models/gemini-test"

    @pytest.mark.asyncio
    async def test_create_cache_passes_display_name_and_ttl(self) -> None:
        """display_name と TTL が SDK に渡されること。"""
        model = _build_model(cache_ttl_minutes=30)
        mock_cache = _make_mock_cache()
        model._client.aio.caches.create = AsyncMock(
            return_value=mock_cache
        )

        await model.create_cache(
            "text",
            model_name="custom-model",
            display_name="pdf-reader: doc.pdf",
        )

        call_kw = model._client.aio.caches.create.call_args
        assert call_kw.kwargs["model"] == "custom-model"
        cfg = call_kw.kwargs["config"]
        assert cfg.display_name == "pdf-reader: doc.pdf"
        assert cfg.ttl == "1800s"

    @pytest.mark.asyncio
    async def test_create_cache_passes_static_system_instruction(self) -> None:
        """create_cache() が静的 system_instruction をキャッシュ設定に含めること。"""
        model = _build_model()
        mock_cache = _make_mock_cache()
        model._client.aio.caches.create = AsyncMock(return_value=mock_cache)

        await model.create_cache("full article text")

        call_kw = model._client.aio.caches.create.call_args
        cfg = call_kw.kwargs["config"]
        assert cfg.system_instruction == _STATIC_SYSTEM_INSTRUCTION

    @pytest.mark.asyncio
    async def test_create_cache_error_raises_cache_error(self) -> None:
        """SDK エラーが AICacheError にラップされること。"""
        model = _build_model()
        model._client.aio.caches.create = AsyncMock(
            side_effect=Exception("Token count too low")
        )

        with pytest.raises(AICacheError, match="Token count too low"):
            await model.create_cache("short text")


class TestGetCacheStatus:
    """get_cache_status() の動作を検証する。"""

    @pytest.mark.asyncio
    async def test_no_cache_returns_inactive(self) -> None:
        """キャッシュ未作成時は is_active=False が返ること。"""
        model = _build_model()
        status = await model.get_cache_status()
        assert status.is_active is False

    @pytest.mark.asyncio
    async def test_active_cache_returns_status(self) -> None:
        """キャッシュ有効時に最新状態が返ること。"""
        from datetime import datetime, timedelta, timezone
        model = _build_model()
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-test"

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_cache = _make_mock_cache(expire_time=future)
        model._client.aio.caches.get = AsyncMock(return_value=mock_cache)

        status = await model.get_cache_status()

        assert status.is_active is True
        assert status.display_name == "pdf-reader: test.pdf"
        assert status.token_count == 5000

    @pytest.mark.asyncio
    async def test_expired_cache_clears_state(self) -> None:
        """expire 済みキャッシュは内部状態がクリアされること。"""
        from datetime import datetime, timedelta, timezone
        model = _build_model()
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-test"

        past = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_cache = _make_mock_cache(expire_time=past)
        model._client.aio.caches.get = AsyncMock(return_value=mock_cache)

        status = await model.get_cache_status()

        assert status.is_active is False
        assert model._cache_name is None
        assert model._cache_model is None

    @pytest.mark.asyncio
    async def test_get_cache_error_clears_state(self) -> None:
        """API エラー時に内部状態がクリアされ is_active=False が返ること。"""
        model = _build_model()
        model._cache_name = "caches/deleted"
        model._cache_model = "models/gemini-test"
        model._client.aio.caches.get = AsyncMock(
            side_effect=Exception("Not found")
        )

        status = await model.get_cache_status()

        assert status.is_active is False
        assert model._cache_name is None


class TestInvalidateCache:
    """invalidate_cache() の動作を検証する。"""

    @pytest.mark.asyncio
    async def test_invalidate_calls_delete(self) -> None:
        """キャッシュ有効時に delete が呼ばれ内部状態がクリアされること。"""
        model = _build_model()
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-test"
        model._client.aio.caches.delete = AsyncMock()

        await model.invalidate_cache()

        model._client.aio.caches.delete.assert_awaited_once()
        assert model._cache_name is None
        assert model._cache_model is None

    @pytest.mark.asyncio
    async def test_invalidate_no_cache_is_noop(self) -> None:
        """キャッシュ未作成時は何も起きないこと。"""
        model = _build_model()
        await model.invalidate_cache()
        # 例外なしで完了

    @pytest.mark.asyncio
    async def test_invalidate_already_deleted_logs_only(self) -> None:
        """既に削除済みの場合は例外なしでログのみ出力すること。"""
        model = _build_model()
        model._cache_name = "caches/already-deleted"
        model._cache_model = "models/gemini-test"
        model._client.aio.caches.delete = AsyncMock(
            side_effect=Exception("Not found")
        )

        await model.invalidate_cache()  # 例外は送出されない
        assert model._cache_name is None

    @pytest.mark.asyncio
    async def test_delete_cache_by_name_keeps_other_internal_state(self) -> None:
        """別名キャッシュ削除では現在キャッシュの内部状態を壊さないこと。"""
        model = _build_model()
        model._cache_name = "caches/current"
        model._cache_model = "models/gemini-test"
        model._client.aio.caches.delete = AsyncMock()

        await model.delete_cache("caches/other")

        model._client.aio.caches.delete.assert_awaited_once_with(
            name="caches/other"
        )
        assert model._cache_name == "caches/current"
        assert model._cache_model == "models/gemini-test"

    @pytest.mark.asyncio
    async def test_delete_cache_by_name_clears_matching_internal_state(self) -> None:
        """現在キャッシュと同名を削除した場合は内部状態もクリアされること。"""
        model = _build_model()
        model._cache_name = "caches/current"
        model._cache_model = "models/gemini-test"
        model._client.aio.caches.delete = AsyncMock()

        await model.delete_cache("caches/current")

        model._client.aio.caches.delete.assert_awaited_once_with(
            name="caches/current"
        )
        assert model._cache_name is None
        assert model._cache_model is None


class TestAnalyzeWithCache:
    """analyze() のキャッシュ統合ロジックを検証する。"""

    @pytest.mark.asyncio
    async def test_analyze_with_active_cache_sends_cached_content(self) -> None:
        """キャッシュ active かつモデル一致時に cached_content が付与され system_instruction は含まれないこと。"""
        model = _build_model(gemini_model_name="models/gemini-test")
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-test"

        mock_resp = _make_mock_response("cached result")
        mock_resp.usage_metadata = None
        model._client.aio.models.generate_content = AsyncMock(
            return_value=mock_resp
        )

        request = AnalysisRequest(
            text="Hello", mode=AnalysisMode.TRANSLATION
        )
        result = await model.analyze(request)

        assert result.translated_text == "cached result"
        call_kw = model._client.aio.models.generate_content.call_args
        config = call_kw.kwargs["config"]
        assert config.cached_content == "caches/test-123"
        # Gemini API はキャッシュ付きリクエストで system_instruction を禁じる
        assert config.system_instruction is None

    @pytest.mark.asyncio
    async def test_analyze_model_mismatch_no_cache(self) -> None:
        """キャッシュのモデルとリクエストモデルが不一致なら cached_content=None。"""
        model = _build_model(gemini_model_name="models/gemini-test")
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-other"

        mock_resp = _make_mock_response("no cache")
        mock_resp.usage_metadata = None
        model._client.aio.models.generate_content = AsyncMock(
            return_value=mock_resp
        )

        request = AnalysisRequest(
            text="Hello", mode=AnalysisMode.TRANSLATION
        )
        await model.analyze(request)

        call_kw = model._client.aio.models.generate_content.call_args
        config = call_kw.kwargs["config"]
        assert config.cached_content is None

    @pytest.mark.asyncio
    async def test_analyze_cache_failure_fallback(self) -> None:
        """キャッシュ付きリクエスト失敗時にキャッシュなしでリトライすること。"""
        model = _build_model(gemini_model_name="models/gemini-test")
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-test"

        exc = _make_api_error(code=400, message="Cache expired")
        mock_resp = _make_mock_response("fallback result")
        mock_resp.usage_metadata = None

        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.models.generate_content = AsyncMock(
                side_effect=[exc, mock_resp]
            )

            request = AnalysisRequest(
                text="Hello", mode=AnalysisMode.TRANSLATION
            )
            result = await model.analyze(request)

        assert result.translated_text == "fallback result"
        # キャッシュ状態がクリアされている
        assert model._cache_name is None
        assert model._cache_model is None

    @pytest.mark.asyncio
    async def test_analyze_cache_rate_limit_not_retried(self) -> None:
        """キャッシュ付き 429 エラーはフォールバックせず AIRateLimitError になること。"""
        model = _build_model(gemini_model_name="models/gemini-test")
        model._cache_name = "caches/test-123"
        model._cache_model = "models/gemini-test"

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
            ):
                request = AnalysisRequest(
                    text="Hello", mode=AnalysisMode.TRANSLATION
                )
                with pytest.raises(AIRateLimitError):
                    await model.analyze(request)


class TestUpdateCacheTtl:
    """update_cache_ttl() の動作を検証する。"""

    @pytest.mark.asyncio
    async def test_update_ttl_success(self) -> None:
        """TTL 更新成功時に CacheStatus が返ること。"""
        model = _build_model()
        model._cache_name = "caches/test-123"
        mock_cache = _make_mock_cache()
        model._client.aio.caches.update = AsyncMock(
            return_value=mock_cache
        )

        status = await model.update_cache_ttl(120)

        assert status.is_active is True
        assert status.ttl_seconds == 7200
        assert status.display_name == "pdf-reader: test.pdf"
        call_kw = model._client.aio.caches.update.call_args
        assert call_kw.kwargs["config"].ttl == "7200s"

    @pytest.mark.asyncio
    async def test_update_ttl_no_cache_raises(self) -> None:
        """キャッシュ未作成時に AICacheError が送出されること。"""
        model = _build_model()
        with pytest.raises(AICacheError):
            await model.update_cache_ttl(60)


class TestListCaches:
    """list_caches() の動作を検証する。"""

    @pytest.mark.asyncio
    async def test_list_caches_filters_by_prefix(self) -> None:
        """pdf-reader: プレフィックス付きキャッシュのみ返ること。"""
        model = _build_model()

        cache_app = _make_mock_cache(
            name="caches/app-1",
            display_name="pdf-reader: test.pdf",
        )
        cache_other = _make_mock_cache(
            name="caches/other-1",
            display_name="some-other-app",
        )

        async def _fake_list():
            for c in [cache_app, cache_other]:
                yield c

        model._client.aio.caches.list = AsyncMock(
            return_value=_fake_list()
        )

        result = await model.list_caches()

        assert len(result) == 1
        assert result[0].cache_name == "caches/app-1"
        assert result[0].display_name == "pdf-reader: test.pdf"

    @pytest.mark.asyncio
    async def test_list_caches_empty(self) -> None:
        """キャッシュが無い場合は空リストが返ること。"""
        model = _build_model()

        async def _fake_list():
            return
            yield  # async generator

        model._client.aio.caches.list = AsyncMock(
            return_value=_fake_list()
        )

        result = await model.list_caches()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_caches_api_error_wraps(self) -> None:
        """API エラーが AIAPIError にラップされること。"""
        model = _build_model()
        exc = _make_api_error(code=500, message="Server error")
        with patch(
            "pdf_epub_reader.models.ai_model.genai_errors.APIError",
            type(exc),
        ):
            model._client.aio.caches.list = AsyncMock(side_effect=exc)
            with pytest.raises(AIAPIError):
                await model.list_caches()


class TestCreateCacheUnsupportedModel:
    """Phase 7 Bugfix: キャッシュ非対応モデルのエラーメッセージ変換を検証する。"""

    @pytest.mark.asyncio
    async def test_unsupported_model_error_converted(self) -> None:
        """'not supported for createCachedContent' エラーが専用メッセージに変換されること。"""
        model = _build_model()
        model._client.aio.caches.create = AsyncMock(
            side_effect=Exception(
                "models/gemini-flash is not supported for createCachedContent"
            )
        )

        with pytest.raises(AICacheError, match="コンテキストキャッシュをサポートしていません"):
            await model.create_cache("full text", model_name="models/gemini-flash")

    @pytest.mark.asyncio
    async def test_other_cache_error_preserved(self) -> None:
        """その他のキャッシュ作成エラーは元のメッセージが維持されること。"""
        model = _build_model()
        model._client.aio.caches.create = AsyncMock(
            side_effect=Exception("Token count too low")
        )

        with pytest.raises(AICacheError, match="Token count too low"):
            await model.create_cache("short text")


class TestCrossModeCacheReuse:
    """1 つのキャッシュが全 3 アクションモードで再利用できることを検証する (Phase 1)。"""

    def _setup_model_with_cache(self) -> tuple[AIModel, AsyncMock]:
        model = _build_model(gemini_model_name="models/gemini-test")
        model._cache_name = "caches/article-123"
        model._cache_model = "models/gemini-test"
        mock_gen = AsyncMock(return_value=_make_mock_response("result"))
        mock_gen.return_value.usage_metadata = None
        model._client.aio.models.generate_content = mock_gen
        return model, mock_gen

    @pytest.mark.asyncio
    async def test_translation_uses_same_cache(self) -> None:
        """翻訳モードでキャッシュが使われ system_instruction が送信されないこと。"""
        model, mock_gen = self._setup_model_with_cache()
        request = AnalysisRequest(text="Hello", mode=AnalysisMode.TRANSLATION)
        await model.analyze(request)

        config = mock_gen.call_args.kwargs["config"]
        assert config.cached_content == "caches/article-123"
        assert config.system_instruction is None

    @pytest.mark.asyncio
    async def test_translation_with_explanation_uses_same_cache(self) -> None:
        """解説付き翻訳モードで同一キャッシュが使われ、addendum が contents に含まれること。"""
        model, mock_gen = self._setup_model_with_cache()
        request = AnalysisRequest(
            text="Hello",
            mode=AnalysisMode.TRANSLATION,
            include_explanation=True,
        )
        await model.analyze(request)

        config = mock_gen.call_args.kwargs["config"]
        assert config.cached_content == "caches/article-123"
        assert config.system_instruction is None
        contents = mock_gen.call_args.kwargs["contents"]
        assert DEFAULT_EXPLANATION_ADDENDUM in contents[0]

    @pytest.mark.asyncio
    async def test_custom_prompt_uses_same_cache(self) -> None:
        """カスタムプロンプトモードで同一キャッシュが使われ、system_instruction が送信されないこと。"""
        model, mock_gen = self._setup_model_with_cache()
        request = AnalysisRequest(
            text="Hello",
            mode=AnalysisMode.CUSTOM_PROMPT,
            custom_prompt="Explain the key concepts.",
        )
        await model.analyze(request)

        config = mock_gen.call_args.kwargs["config"]
        assert config.cached_content == "caches/article-123"
        assert config.system_instruction is None
        contents = mock_gen.call_args.kwargs["contents"]
        assert "USER_TASK" in contents[0]
        assert "Explain the key concepts." in contents[0]

    @pytest.mark.asyncio
    async def test_all_modes_use_same_cache_handle(self) -> None:
        """3 モード連続呼び出しで全て同一キャッシュ名が使われること。"""
        model, mock_gen = self._setup_model_with_cache()

        for mode, extra in [
            (AnalysisMode.TRANSLATION, {}),
            (AnalysisMode.TRANSLATION, {"include_explanation": True}),
            (AnalysisMode.CUSTOM_PROMPT, {"custom_prompt": "Summarize"}),
        ]:
            mock_gen.return_value = _make_mock_response("ok")
            mock_gen.return_value.usage_metadata = None
            await model.analyze(AnalysisRequest(text="text", mode=mode, **extra))
            cfg = mock_gen.call_args.kwargs["config"]
            assert cfg.cached_content == "caches/article-123", f"cache not used for mode={mode}"
            assert cfg.system_instruction is None, f"system_instruction leaked for mode={mode}"
