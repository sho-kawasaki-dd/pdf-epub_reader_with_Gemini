from __future__ import annotations

import json

from pdf_epub_reader.utils.config import (
    AppConfig,
    load_config,
    save_config,
)


class TestUiLanguageConfig:
    def test_missing_config_uses_os_locale_default(
        self,
        tmp_path,
        monkeypatch,
    ) -> None:
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(
            "pdf_epub_reader.utils.config.locale.getlocale",
            lambda: ("ja_JP", "UTF-8"),
        )

        config = load_config(config_path)

        assert config.ui_language == "ja"

    def test_existing_config_without_ui_language_uses_os_locale_default(
        self,
        tmp_path,
        monkeypatch,
    ) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"window_width": 1600}, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "pdf_epub_reader.utils.config.locale.getlocale",
            lambda: ("ja-JP", "UTF-8"),
        )

        config = load_config(config_path)

        assert config.window_width == 1600
        assert config.ui_language == "ja"

    def test_load_config_normalizes_legacy_ui_language(self, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"ui_language": "en-US"}, ensure_ascii=False),
            encoding="utf-8",
        )

        config = load_config(config_path)

        assert config.ui_language == "en"

    def test_invalid_ui_language_falls_back_to_english(self) -> None:
        config = AppConfig(ui_language="fr-FR")

        assert config.ui_language == "en"

    def test_save_config_writes_normalized_ui_language(self, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        config = AppConfig(ui_language="en")
        config.ui_language = "ja-JP"

        save_config(config, config_path)

        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["ui_language"] == "ja"


class TestAiModelConfig:
    def test_ai_model_fields_are_normalized(self) -> None:
        config = AppConfig(
            gemini_model_name="  ",
            selected_models=["models/a", "", "  ", "models/a", "models/b  "],
        )

        assert config.gemini_model_name == ""
        assert config.selected_models == ["models/a", "models/b"]


class TestMarkdownExportConfig:
    def test_export_fields_use_expected_defaults(self) -> None:
        config = AppConfig()

        assert config.export_folder == ""
        assert config.export_include_explanation is True
        assert config.export_include_selection_list is True
        assert config.export_include_raw_response is False
        assert config.export_include_document_metadata is False
        assert config.export_include_usage_metrics is False
        assert config.export_include_yaml_frontmatter is False

    def test_export_folder_is_trimmed_and_round_trips(self, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        config = AppConfig(
            export_folder="  C:/exports/markdown  ",
            export_include_explanation=False,
            export_include_selection_list=False,
            export_include_raw_response=True,
            export_include_document_metadata=True,
            export_include_usage_metrics=True,
            export_include_yaml_frontmatter=True,
        )

        save_config(config, config_path)
        loaded = load_config(config_path)

        assert loaded.export_folder == "C:/exports/markdown"
        assert loaded.export_include_explanation is False
        assert loaded.export_include_selection_list is False
        assert loaded.export_include_raw_response is True
        assert loaded.export_include_document_metadata is True
        assert loaded.export_include_usage_metrics is True
        assert loaded.export_include_yaml_frontmatter is True


class TestPlotlyVisualizationConfig:
    def test_plotly_fields_use_expected_defaults(self) -> None:
        config = AppConfig()

        assert config.plotly_visualization_mode == "off"
        assert config.plotly_multi_spec_mode == "all_tabs"
        assert config.plotly_sandbox_timeout_s == 10.0

    def test_plotly_fields_round_trip_and_mode_is_normalized(self, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        config = AppConfig(
            plotly_visualization_mode="json",
            plotly_multi_spec_mode="all_tabs",
        )

        save_config(config, config_path)
        loaded = load_config(config_path)

        assert loaded.plotly_visualization_mode == "json"
        assert loaded.plotly_multi_spec_mode == "all_tabs"

    def test_invalid_plotly_mode_falls_back_to_prompt(self) -> None:
        config = AppConfig(plotly_multi_spec_mode="invalid")

        assert config.plotly_multi_spec_mode == "all_tabs"

    def test_legacy_plotly_enabled_true_migrates_to_json_mode(self, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"plotly_visualization_enabled": True}, ensure_ascii=False),
            encoding="utf-8",
        )

        loaded = load_config(config_path)

        assert loaded.plotly_visualization_mode == "json"