"""UI 文言を Presenter から View へ渡すための DTO 群。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BookmarkPanelTexts:
    """しおりパネルの静的文言。"""

    header_label: str


@dataclass(frozen=True)
class MainWindowTexts:
    """MainWindow が表示する静的文言とダイアログ文言。"""

    window_title: str
    file_menu_title: str
    open_action_text: str
    recent_menu_title: str
    recent_none_text: str
    quit_action_text: str
    view_menu_title: str
    bookmark_toggle_text: str
    edit_menu_title: str
    preferences_action_text: str
    cache_menu_title: str
    cache_management_action_text: str
    language_menu_title: str
    language_settings_action_text: str
    overlay_page_label: str
    default_status_text: str
    open_dialog_title: str
    open_dialog_filter: str
    password_dialog_title: str
    password_dialog_message_template: str
    bookmark_panel: BookmarkPanelTexts


@dataclass(frozen=True)
class AnalysisStatusTexts:
    """AI request の running / cancel / timing 文言。"""

    running_message: str
    cancelled_message: str
    timing_only: str
    timing_with_graph: str
    cancel_link_text: str


@dataclass(frozen=True)
class SidePanelTexts:
    """サイドパネルで使う静的文言と表示テンプレート。"""

    model_label: str
    model_unset_placeholder: str
    selection_section_title: str
    selection_summary_template: str
    selection_clear_button: str
    selection_warning_text: str
    selection_empty_text: str
    selection_preview_label: str
    selection_preview_placeholder: str
    selection_force_image_text: str
    plotly_toggle_tooltip: str
    plotly_toggle_tooltip_off: str
    plotly_toggle_tooltip_json: str
    plotly_toggle_tooltip_python: str
    ai_section_title: str
    translation_button_text: str
    translation_explain_button_text: str
    translation_tab_text: str
    translation_placeholder_text: str
    custom_tab_text: str
    custom_prompt_placeholder: str
    custom_submit_button_text: str
    export_button_text: str
    custom_placeholder_text: str
    cache_status_placeholder: str
    cache_create_button_text: str
    cache_delete_button_text: str
    cache_remaining_template: str
    cache_expired_text: str
    selection_card_page_template: str
    selection_card_delete_button: str
    selection_card_pending_text: str
    selection_card_error_text: str
    selection_card_ready_text: str
    selection_card_extracting_text: str
    selection_card_extract_failed_text: str
    selection_card_no_text: str


@dataclass(frozen=True)
class PlotlyTexts:
    """Plotly 可視化まわりで使う静的文言。"""

    multi_select_dialog_title: str
    multi_select_dialog_label: str
    multi_select_cancel_button_text: str
    spec_fallback_title_template: str
    render_success_message_template: str
    extraction_failed_message: str
    restore_failed_message_template: str
    invalid_json_message_template: str
    window_title_template: str
    sandbox_running_message: str
    sandbox_timeout_message: str
    sandbox_runtime_error_message: str
    sandbox_static_check_error_message: str
    sandbox_cancelled_message: str
    sandbox_provisioning_message: str
    sandbox_provisioning_failed_message: str
    sandbox_provisioning_failed_offline_message: str
    sandbox_fallback_to_json_message: str
    sandbox_cancel_link_text: str


@dataclass(frozen=True)
class SettingsDialogTexts:
    """設定ダイアログの静的文言。"""

    window_title: str
    rendering_tab_text: str
    detection_tab_text: str
    ai_tab_text: str
    export_tab_text: str
    visualization_tab_text: str
    image_format_label: str
    jpeg_quality_label: str
    default_dpi_label: str
    page_cache_size_label: str
    high_quality_downscale_text: str
    auto_detect_images_text: str
    auto_detect_math_text: str
    default_model_label: str
    available_models_label: str
    fetch_models_button_text: str
    fetch_models_loading_text: str
    output_language_label: str
    translation_prompt_label: str
    cache_ttl_label: str
    export_folder_label: str
    export_browse_button_text: str
    export_include_explanation_text: str
    export_include_selection_list_text: str
    export_include_raw_response_text: str
    export_include_document_metadata_text: str
    export_include_usage_metrics_text: str
    export_include_yaml_frontmatter_text: str
    plotly_multi_spec_prompt_text: str
    plotly_multi_spec_first_only_text: str
    plotly_timeout_label: str
    plotly_timeout_suffix_seconds: str
    minutes_suffix: str
    reset_defaults_button_text: str
    ok_button_text: str
    cancel_button_text: str


@dataclass(frozen=True)
class MarkdownExportTexts:
    """Markdown export 用の UI 文言と Markdown ラベル。"""

    success_message_template: str
    failure_message_template: str
    folder_unset_message: str
    exported_at_label: str
    action_label: str
    model_label: str
    source_document_label: str
    source_file_label: str
    selections_section_title: str
    ai_response_section_title: str
    explanation_section_title: str
    raw_response_section_title: str
    document_metadata_section_title: str
    usage_metrics_section_title: str
    document_title_label: str
    file_name_label: str
    selection_count_label: str
    prompt_tokens_label: str
    cached_tokens_label: str
    candidates_tokens_label: str
    total_tokens_label: str
    action_translation_label: str
    action_custom_prompt_label: str


@dataclass(frozen=True)
class CacheDialogTexts:
    """キャッシュ管理ダイアログの静的文言と表示テンプレート。"""

    window_title: str
    tab_current_text: str
    tab_list_text: str
    field_name_label: str
    field_model_label: str
    field_tokens_label: str
    field_remaining_ttl_label: str
    field_expire_time_label: str
    field_status_label: str
    field_new_ttl_label: str
    button_update_ttl_text: str
    button_create_text: str
    button_delete_text: str
    button_delete_selected_text: str
    button_close_text: str
    table_name_header: str
    table_model_header: str
    table_display_name_header: str
    table_tokens_header: str
    table_expire_header: str
    status_active_text: str
    status_inactive_text: str
    status_expired_text: str
    ttl_minutes_seconds_template: str
    minutes_suffix: str
    not_set_text: str


@dataclass(frozen=True)
class LanguageDialogTexts:
    """表示言語ダイアログの静的文言。"""

    window_title: str
    description_text: str
    label_text: str
    ok_button_text: str
    cancel_button_text: str