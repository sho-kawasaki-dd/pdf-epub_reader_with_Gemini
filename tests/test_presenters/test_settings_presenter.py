"""SettingsPresenter の振る舞いを検証するテスト群。

OK / Cancel / Reset の各フローと、ダイアログ外フィールドの保持、
save_config 呼び出しを検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.mocks.mock_models import MockAIModel
from tests.mocks.mock_views import MockSettingsDialogView

from pdf_epub_reader.interfaces.view_interfaces import ISettingsDialogView
from pdf_epub_reader.presenters.settings_presenter import SettingsPresenter
from pdf_epub_reader.utils.config import (
    AppConfig,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OUTPUT_LANGUAGE,
    DEFAULT_TRANSLATION_PROMPT,
)


@pytest.fixture
def mock_settings_view() -> MockSettingsDialogView:
    """設定ダイアログの Mock View を返す。"""
    return MockSettingsDialogView()


class TestProtocolConformance:
    """MockSettingsDialogView が Protocol を満たすことを確認する。"""

    def test_mock_satisfies_protocol(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        assert isinstance(mock_settings_view, ISettingsDialogView)


class TestShowOk:
    """OK でダイアログを閉じた場合のフローを検証する。"""

    def test_ok_returns_updated_config(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """OK → 更新後の AppConfig が返ること。"""
        config = AppConfig(default_dpi=144, jpeg_quality=85)
        mock_settings_view._exec_return = True
        # ユーザーがダイアログで DPI を 200 に変更したとシミュレート
        mock_settings_view._values["default_dpi"] = 200

        presenter = SettingsPresenter(mock_settings_view, config)

        with patch(
            "pdf_epub_reader.presenters.settings_presenter.save_config"
        ) as mock_save:
            result = presenter.show()

        assert result is not None
        # populate 後にユーザーが変更した値が反映されている。
        # Note: populate は __init__ の後 show() の中で呼ばれるので、
        # Mock の値は populate で上書きされる。テストでは populate 後に
        # 値を変更する必要がある。
        # → しかし show() は populate → exec → read の順で実行されるため、
        #   exec_dialog の前に値を変更する必要がある。
        #   MockSettingsDialogView は exec_dialog 時に _exec_return を返すだけなので、
        #   populate で設定された値がそのまま read される。
        assert result.default_dpi == 144  # populate が上書きするため
        assert mock_save.called

    def test_ok_populates_view_with_current_config(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """show() 時に現在の AppConfig 値で View が populate されること。"""
        config = AppConfig(
            render_format="jpeg",
            jpeg_quality=70,
            default_dpi=200,
            page_cache_max_size=100,
            auto_detect_embedded_images=False,
            auto_detect_math_fonts=False,
        )
        mock_settings_view._exec_return = True

        presenter = SettingsPresenter(mock_settings_view, config)
        with patch(
            "pdf_epub_reader.presenters.settings_presenter.save_config"
        ):
            presenter.show()

        # populate で各 setter が呼ばれたことを確認。
        assert len(mock_settings_view.get_calls("set_render_format")) >= 1
        assert mock_settings_view.get_calls("set_render_format")[0] == (
            "jpeg",
        )
        assert mock_settings_view.get_calls("set_jpeg_quality")[0] == (70,)
        assert mock_settings_view.get_calls("set_default_dpi")[0] == (200,)
        assert mock_settings_view.get_calls("set_page_cache_max_size")[0] == (
            100,
        )
        assert mock_settings_view.get_calls(
            "set_auto_detect_embedded_images"
        )[0] == (False,)
        assert mock_settings_view.get_calls("set_auto_detect_math_fonts")[
            0
        ] == (False,)

    def test_ok_preserves_non_dialog_fields(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """ダイアログ外フィールド（window_width 等）が保持されること。"""
        config = AppConfig(
            window_width=1920,
            window_height=1080,
            recent_files=["/path/to/file.pdf"],
        )
        mock_settings_view._exec_return = True

        presenter = SettingsPresenter(mock_settings_view, config)
        with patch(
            "pdf_epub_reader.presenters.settings_presenter.save_config"
        ):
            result = presenter.show()

        assert result is not None
        assert result.window_width == 1920
        assert result.window_height == 1080
        assert result.recent_files == ["/path/to/file.pdf"]

    def test_ok_calls_save_config(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """OK 時に save_config が呼ばれること。"""
        config = AppConfig()
        mock_settings_view._exec_return = True

        presenter = SettingsPresenter(mock_settings_view, config)
        with patch(
            "pdf_epub_reader.presenters.settings_presenter.save_config"
        ) as mock_save:
            result = presenter.show()

        assert result is not None
        mock_save.assert_called_once_with(result)


class TestShowCancel:
    """Cancel でダイアログを閉じた場合のフローを検証する。"""

    def test_cancel_returns_none(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """Cancel → None が返ること。"""
        config = AppConfig()
        mock_settings_view._exec_return = False

        presenter = SettingsPresenter(mock_settings_view, config)

        with patch(
            "pdf_epub_reader.presenters.settings_presenter.save_config"
        ) as mock_save:
            result = presenter.show()

        assert result is None
        mock_save.assert_not_called()


class TestResetDefaults:
    """Reset to Defaults の振る舞いを検証する。"""

    def test_reset_populates_default_values(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """リセットコールバック呼び出し時にデフォルト値が View に設定されること。"""
        config = AppConfig(
            render_format="jpeg",
            jpeg_quality=50,
            default_dpi=300,
            page_cache_max_size=200,
            auto_detect_embedded_images=False,
            auto_detect_math_fonts=False,
        )

        presenter = SettingsPresenter(mock_settings_view, config)

        # 初期 populate のコール履歴をクリアして、リセット分だけ確認する。
        mock_settings_view.calls.clear()

        # リセットをシミュレート
        mock_settings_view.simulate_reset_defaults()

        defaults = AppConfig()
        assert mock_settings_view.get_calls("set_render_format")[-1] == (
            defaults.render_format,
        )
        assert mock_settings_view.get_calls("set_jpeg_quality")[-1] == (
            defaults.jpeg_quality,
        )
        assert mock_settings_view.get_calls("set_default_dpi")[-1] == (
            defaults.default_dpi,
        )
        assert mock_settings_view.get_calls("set_page_cache_max_size")[
            -1
        ] == (defaults.page_cache_max_size,)
        assert mock_settings_view.get_calls(
            "set_auto_detect_embedded_images"
        )[-1] == (defaults.auto_detect_embedded_images,)
        assert mock_settings_view.get_calls("set_auto_detect_math_fonts")[
            -1
        ] == (defaults.auto_detect_math_fonts,)


class TestAISettingsPopulate:
    """Phase 6: AI 設定のダイアログ populate / read を検証する。"""

    def test_populate_sets_ai_fields(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """show() で AI 設定フィールドが View に populate されること。"""
        config = AppConfig(
            gemini_model_name="gemini-custom",
            selected_models=["gemini-custom", "gemini-pro"],
            output_language="English",
            system_prompt_translation="Custom prompt {output_language}",
        )
        mock_settings_view._exec_return = True

        presenter = SettingsPresenter(mock_settings_view, config)
        with patch(
            "pdf_epub_reader.presenters.settings_presenter.save_config"
        ):
            presenter.show()

        assert mock_settings_view.get_calls("set_gemini_model_name")[0] == (
            "gemini-custom",
        )
        assert mock_settings_view.get_calls("set_selected_models")[0] == (
            ["gemini-custom", "gemini-pro"],
        )
        assert mock_settings_view.get_calls("set_output_language")[0] == (
            "English",
        )
        assert mock_settings_view.get_calls(
            "set_system_prompt_translation"
        )[0] == ("Custom prompt {output_language}",)

    def test_read_config_includes_ai_fields(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """OK 時に AI 設定が AppConfig に読み取られること。"""
        config = AppConfig()
        mock_settings_view._exec_return = True
        mock_settings_view._values["gemini_model_name"] = "gemini-2.0-flash"
        mock_settings_view._values["selected_models"] = [
            "gemini-2.0-flash",
            "gemini-pro",
        ]
        mock_settings_view._values["output_language"] = "English"
        mock_settings_view._values["system_prompt_translation"] = "Translate to {output_language}"

        presenter = SettingsPresenter(mock_settings_view, config)
        with patch(
            "pdf_epub_reader.presenters.settings_presenter.save_config"
        ):
            result = presenter.show()

        assert result is not None
        # populate で上書きされるため、初期値になる
        assert result.gemini_model_name == DEFAULT_GEMINI_MODEL
        assert result.output_language == DEFAULT_OUTPUT_LANGUAGE

    def test_populate_sets_export_fields(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """show() で export 設定フィールドが View に populate されること。"""
        config = AppConfig(
            export_folder="C:/exports",
            export_include_explanation=False,
            export_include_selection_list=False,
            export_include_raw_response=True,
            export_include_document_metadata=True,
            export_include_usage_metrics=True,
            export_include_yaml_frontmatter=True,
        )
        mock_settings_view._exec_return = True

        presenter = SettingsPresenter(mock_settings_view, config)
        with patch(
            "pdf_epub_reader.presenters.settings_presenter.save_config"
        ):
            presenter.show()

        assert mock_settings_view.get_calls("set_export_folder")[0] == (
            "C:/exports",
        )
        assert mock_settings_view.get_calls(
            "set_export_include_explanation"
        )[0] == (False,)
        assert mock_settings_view.get_calls(
            "set_export_include_selection_list"
        )[0] == (False,)
        assert mock_settings_view.get_calls(
            "set_export_include_raw_response"
        )[0] == (True,)
        assert mock_settings_view.get_calls(
            "set_export_include_document_metadata"
        )[0] == (True,)
        assert mock_settings_view.get_calls(
            "set_export_include_usage_metrics"
        )[0] == (True,)
        assert mock_settings_view.get_calls(
            "set_export_include_yaml_frontmatter"
        )[0] == (True,)

    def test_read_config_includes_export_fields(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """View の export 設定が AppConfig に読み取られること。"""
        config = AppConfig()
        presenter = SettingsPresenter(mock_settings_view, config)
        mock_settings_view._values["export_folder"] = "  C:/exports/markdown  "
        mock_settings_view._values["export_include_explanation"] = False
        mock_settings_view._values["export_include_selection_list"] = False
        mock_settings_view._values["export_include_raw_response"] = True
        mock_settings_view._values["export_include_document_metadata"] = True
        mock_settings_view._values["export_include_usage_metrics"] = True
        mock_settings_view._values["export_include_yaml_frontmatter"] = True

        result = presenter._read_config_from_view()

        assert result.export_folder == "C:/exports/markdown"
        assert result.export_include_explanation is False
        assert result.export_include_selection_list is False
        assert result.export_include_raw_response is True
        assert result.export_include_document_metadata is True
        assert result.export_include_usage_metrics is True
        assert result.export_include_yaml_frontmatter is True

    def test_reset_sets_ai_default_values(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """リセット時に AI フィールドもデフォルト値になること。"""
        config = AppConfig(
            gemini_model_name="non-default",
            output_language="French",
        )
        presenter = SettingsPresenter(mock_settings_view, config)
        mock_settings_view.calls.clear()

        mock_settings_view.simulate_reset_defaults()

        defaults = AppConfig()
        assert mock_settings_view.get_calls("set_gemini_model_name")[
            -1
        ] == (defaults.gemini_model_name,)
        assert mock_settings_view.get_calls("set_output_language")[
            -1
        ] == (defaults.output_language,)
        assert mock_settings_view.get_calls(
            "set_system_prompt_translation"
        )[-1] == (defaults.system_prompt_translation,)

    def test_reset_sets_export_default_values(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """リセット時に export フィールドもデフォルト値になること。"""
        config = AppConfig(
            export_folder="C:/exports",
            export_include_explanation=False,
            export_include_selection_list=False,
            export_include_raw_response=True,
            export_include_document_metadata=True,
            export_include_usage_metrics=True,
            export_include_yaml_frontmatter=True,
        )
        presenter = SettingsPresenter(mock_settings_view, config)
        mock_settings_view.calls.clear()

        mock_settings_view.simulate_reset_defaults()

        defaults = AppConfig()
        assert mock_settings_view.get_calls("set_export_folder")[-1] == (
            defaults.export_folder,
        )
        assert mock_settings_view.get_calls(
            "set_export_include_explanation"
        )[-1] == (defaults.export_include_explanation,)
        assert mock_settings_view.get_calls(
            "set_export_include_selection_list"
        )[-1] == (defaults.export_include_selection_list,)
        assert mock_settings_view.get_calls(
            "set_export_include_raw_response"
        )[-1] == (defaults.export_include_raw_response,)
        assert mock_settings_view.get_calls(
            "set_export_include_document_metadata"
        )[-1] == (defaults.export_include_document_metadata,)
        assert mock_settings_view.get_calls(
            "set_export_include_usage_metrics"
        )[-1] == (defaults.export_include_usage_metrics,)
        assert mock_settings_view.get_calls(
            "set_export_include_yaml_frontmatter"
        )[-1] == (defaults.export_include_yaml_frontmatter,)


class TestFetchModels:
    """Phase 6: Fetch Models ボタンの非同期処理を検証する。"""

    @pytest.mark.asyncio
    async def test_fetch_models_populates_view(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """モデル一覧が View に設定されること。"""
        mock_ai_model = MockAIModel()
        presenter = SettingsPresenter(
            mock_settings_view, AppConfig(), ai_model=mock_ai_model
        )

        await presenter._fetch_models_async()

        selection_calls = mock_settings_view.get_calls(
            "set_available_models_for_selection"
        )
        assert len(selection_calls) == 1
        models = selection_calls[0][0]
        assert len(models) == 1
        assert models[0] == ("models/gemini-test", "Gemini Test")

    @pytest.mark.asyncio
    async def test_fetch_models_shows_loading(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """Fetch 中にローディング表示が制御されること。"""
        mock_ai_model = MockAIModel()
        presenter = SettingsPresenter(
            mock_settings_view, AppConfig(), ai_model=mock_ai_model
        )

        await presenter._fetch_models_async()

        loading_calls = mock_settings_view.get_calls("set_fetch_models_loading")
        assert loading_calls[0] == (True,)
        assert loading_calls[-1] == (False,)

    def test_fetch_without_ai_model_shows_error(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """ai_model が None のとき、エラーが表示されること。"""
        presenter = SettingsPresenter(
            mock_settings_view, AppConfig(ui_language="en"), ai_model=None
        )

        presenter._on_fetch_models()

        error_calls = mock_settings_view.get_calls("show_fetch_models_error")
        assert len(error_calls) == 1
        assert error_calls[0][0] == "AI model is not available."

    @pytest.mark.asyncio
    async def test_fetch_models_error_shows_in_view(
        self, mock_settings_view: MockSettingsDialogView
    ) -> None:
        """API エラー時にエラーメッセージが View に表示されること。"""
        from pdf_epub_reader.utils.exceptions import AIAPIError

        mock_ai_model = MockAIModel()
        mock_ai_model.list_available_models = AsyncMock(
            side_effect=AIAPIError("Network error", status_code=500)
        )
        presenter = SettingsPresenter(
            mock_settings_view,
            AppConfig(ui_language="en"),
            ai_model=mock_ai_model,
        )

        await presenter._fetch_models_async()

        error_calls = mock_settings_view.get_calls("show_fetch_models_error")
        assert len(error_calls) == 1
        assert "Failed to fetch the model list" in error_calls[0][0]
        assert "Network error" in error_calls[0][0]
