"""AI サイドパネルの PySide6 実装。

ISidePanelView Protocol を満たし、翻訳・カスタムプロンプトの操作と
AI 解析結果の表示を担当する。このクラス自身はロジックを持たず、
ボタン押下やタブ切り替えの通知をコールバック経由で Presenter に渡すだけ。

Phase 4 で以下を追加:
- 「画像としても送信」チェックボックス（セッション内、デフォルト OFF）
- 選択範囲のサムネイルプレビュー（QLabel）
- AI 回答欄を QWebEngineView + markdown + KaTeX に差し替え
  Markdown→HTML 変換は View 層の責務（表示形式の責務）
"""

from __future__ import annotations

import importlib.resources
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import markdown
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QMenu,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdf_epub_reader.dto import SelectionSlot, SelectionSnapshot, SidePanelTexts
from pdf_epub_reader.utils.config import DEFAULT_UI_LANGUAGE


# タブインデックスと AnalysisMode.value の対応。
# Presenter は文字列でモードを受け取るため、ここで変換する。
_TAB_NAMES = {0: "translation", 1: "custom_prompt"}
_PLOTLY_MODE_ORDER = ("off", "json", "python")


def _get_katex_dir() -> Path:
    """KaTeX ローカルバンドルのディレクトリパスを返す。

    importlib.resources を使ってパッケージリソースのパスを解決する。
    これにより pip install 後もバンドルへの参照が壊れない。
    """
    return Path(
        str(importlib.resources.files("pdf_epub_reader") / "resources" / "katex")
    )


def _render_markdown_html(md_text: str) -> str:
    """Markdown テキストを KaTeX 対応の HTML 文字列に変換する。

    Markdown→HTML 変換は ``markdown`` ライブラリで行い、
    数式レンダリングは KaTeX の auto-render + mhchem で行う。
    この関数は View 層の責務であり、表示形式の変換のみを担当する。
    """
    katex_dir = _get_katex_dir()
    # file:// URL に変換（Windows パスの場合もスラッシュ区切りに統一）
    katex_base_url = katex_dir.as_uri()

    # Markdown → HTML 変換（fenced_code, tables, nl2br 拡張を有効化）
    html_body = markdown.markdown(
        md_text,
        extensions=["fenced_code", "tables", "nl2br"],
    )

    # KaTeX + auto-render + mhchem を読み込む完全な HTML を構築する。
    # delimiters 設定で $...$ (インライン) と $$...$$ (ディスプレイ) に対応し、
    # mhchem で \ce{...} 化学式もレンダリングする。
    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="{katex_base_url}/katex.min.css">
<script src="{katex_base_url}/katex.min.js"></script>
<script src="{katex_base_url}/contrib/mhchem.min.js"></script>
<script src="{katex_base_url}/contrib/auto-render.min.js"></script>
<style>
  body {{
    font-family: "Segoe UI", "Yu Gothic UI", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    margin: 8px;
    color: #333;
  }}
  pre {{
    background: #f4f4f4;
    padding: 8px;
    border-radius: 4px;
    overflow-x: auto;
  }}
  code {{
    background: #f0f0f0;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 13px;
  }}
  pre code {{
    background: none;
    padding: 0;
  }}
  table {{
    border-collapse: collapse;
    margin: 8px 0;
  }}
  th, td {{
    border: 1px solid #ccc;
    padding: 4px 8px;
  }}
  blockquote {{
    border-left: 3px solid #ccc;
    margin-left: 0;
    padding-left: 12px;
    color: #666;
  }}
</style>
</head>
<body>
{html_body}
<script>
  document.addEventListener("DOMContentLoaded", function() {{
    renderMathInElement(document.body, {{
      delimiters: [
        {{left: "$$", right: "$$", display: true}},
        {{left: "$", right: "$", display: false}},
        {{left: "\\\\(", right: "\\\\)", display: false}},
        {{left: "\\\\[", right: "\\\\]", display: true}}
      ],
      throwOnError: false
    }});
  }});
</script>
</body>
</html>"""


class CollapsibleSection(QWidget):
    """クリックで子要素の表示/非表示を切り替えるセクションウィジェット。

    ヘッダー（▶/▼ プレフィックス付き QPushButton）をクリックすると
    コンテンツ領域が展開/折りたたみされる。
    Phase 6.5 で選択プレビュー領域の視認性向上のために導入。
    """

    def __init__(
        self, title: str, parent: QWidget | None = None, expanded: bool = True
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._expanded = expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ヘッダーボタン（フラットスタイル、左寄せ）
        self._toggle_btn = QPushButton(self._header_text())
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setStyleSheet("text-align: left; font-weight: bold;")
        self._toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self._toggle_btn)

        # コンテンツコンテナ
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content.setVisible(self._expanded)
        layout.addWidget(self._content)

    def content_layout(self) -> QVBoxLayout:
        """子ウィジェットを追加するための内部レイアウトを返す。"""
        return self._content_layout

    def is_expanded(self) -> bool:
        """現在展開中かどうかを返す。"""
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        """展開状態を明示的に切り替える。"""
        if self._expanded == expanded:
            return
        self._toggle()

    def toggle(self) -> None:
        """展開状態をトグルする。"""
        self._toggle()

    def _header_text(self) -> str:
        prefix = "▼" if self._expanded else "▶"
        return f"{prefix} {self._title}"

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._toggle_btn.setText(self._header_text())
        self.updateGeometry()

    def set_title(self, title: str) -> None:
        self._title = title
        self._toggle_btn.setText(self._header_text())


class _SelectionCard(QFrame):
    """1 件分の選択スロットを表示するカード。"""

    def __init__(
        self,
        slot: SelectionSlot,
        text_for: Callable[..., str],
        on_delete_requested: Callable[[str], None] | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text_for = text_for
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame {"
            "border: 1px solid #d0d7de;"
            "border-radius: 8px;"
            "background: #fbfcfe;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        badge = QLabel(str(slot.display_number))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(22, 22)
        badge.setStyleSheet(
            "background: rgba(0, 120, 215, 0.86);"
            "color: white;"
            "border-radius: 11px;"
            "font-weight: bold;"
        )
        header_row.addWidget(badge)

        header_text = QLabel(
            self._text_for("selection_card_page_template", page=slot.page_number + 1)
        )
        header_text.setStyleSheet("font-weight: bold;")
        header_row.addWidget(header_text)

        state_label = QLabel(self._state_text(slot))
        state_label.setStyleSheet(self._state_style(slot))
        header_row.addWidget(state_label)
        header_row.addStretch(1)

        delete_button = QPushButton(
            self._text_for("selection_card_delete_button")
        )
        delete_button.setFixedHeight(24)
        delete_button.clicked.connect(
            lambda: on_delete_requested and on_delete_requested(slot.selection_id)
        )
        header_row.addWidget(delete_button)
        layout.addLayout(header_row)

        preview_label = QLabel(self._preview_text(slot))
        preview_label.setWordWrap(True)
        preview_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        preview_label.setStyleSheet("color: #334155;")
        layout.addWidget(preview_label)

        if slot.content and slot.content.cropped_image:
            thumbnail = QPixmap()
            thumbnail.loadFromData(slot.content.cropped_image)
            if not thumbnail.isNull():
                thumbnail_label = QLabel()
                thumbnail_label.setPixmap(
                    thumbnail.scaledToHeight(
                        72, mode=Qt.TransformationMode.SmoothTransformation
                    )
                )
                layout.addWidget(thumbnail_label)

    def _state_text(self, slot: SelectionSlot) -> str:
        if slot.read_state == "pending":
            return self._text_for("selection_card_pending_text")
        if slot.read_state == "error":
            return self._text_for("selection_card_error_text")
        return self._text_for("selection_card_ready_text")

    def _state_style(self, slot: SelectionSlot) -> str:
        if slot.read_state == "pending":
            color = "#b45309"
            background = "#fef3c7"
        elif slot.read_state == "error":
            color = "#b91c1c"
            background = "#fee2e2"
        else:
            color = "#166534"
            background = "#dcfce7"
        return (
            f"color: {color};"
            f"background: {background};"
            "border-radius: 10px;"
            "padding: 2px 8px;"
        )

    def _preview_text(self, slot: SelectionSlot) -> str:
        if slot.read_state == "pending":
            return self._text_for("selection_card_extracting_text")
        if slot.read_state == "error":
            return slot.error_message or self._text_for(
                "selection_card_extract_failed_text"
            )

        text = slot.extracted_text.strip() or self._text_for(
            "selection_card_no_text"
        )
        text = text.replace("\n", " ")
        if len(text) > 140:
            return text[:137] + "..."
        return text


class SidePanelView(QWidget):
    """ISidePanelView Protocol を満たすサイドパネル実装。

    選択一覧セクションと AI 応答セクションを縦 splitter で並べ、
    それぞれ CollapsibleSection として折りたためるようにする。
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        ui_language: str = DEFAULT_UI_LANGUAGE,
    ) -> None:
        super().__init__(parent)
        self._texts: SidePanelTexts | None = None

        # --- KaTeX ローカルバンドルの baseUrl ---
        # Chromium が file:/// リソースを読み込めるよう、
        # setHtml() の第二引数に渡す QUrl を保持する。
        katex_dir = _get_katex_dir()
        self._katex_base_url = QUrl.fromLocalFile(str(katex_dir) + "/")

        # --- コールバック保持用 ---
        self._on_translate_requested: Callable[[bool], None] | None = None
        self._on_custom_prompt_submitted: Callable[[str], None] | None = None
        self._on_export_requested: Callable[[], None] | None = None
        self._on_tab_changed: Callable[[str], None] | None = None
        self._on_force_image_toggled: Callable[[bool], None] | None = None
        self._on_plotly_mode_changed: (
            Callable[[str], None] | None
        ) = None
        self._on_selection_delete_requested: (
            Callable[[str], None] | None
        ) = None
        self._on_clear_selections_requested: Callable[[], None] | None = None
        self._on_model_changed: Callable[[str], None] | None = None
        self._on_cache_create_requested: Callable[[], None] | None = None
        self._on_cache_invalidate_requested: Callable[[], None] | None = None
        self._cache_is_active: bool = False
        self._selection_snapshot = SelectionSnapshot()
        self._combined_selection_preview = ""
        self._plotly_mode = "off"

        # Phase 7.5: カウントダウン状態
        self._on_cache_expired: Callable[[], None] | None = None
        self._cache_base_text: str = ""
        self._expire_time_utc: datetime | None = None
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

        # --- ウィジェット構築 ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Phase 6: モデル選択プルダウン
        model_row = QHBoxLayout()
        self._model_label = QLabel("")
        model_row.addWidget(self._model_label)
        self._model_combo = QComboBox()
        self._model_combo.setEnabled(False)
        self._model_combo.setCurrentIndex(-1)
        self._model_combo.currentTextChanged.connect(self._fire_model_changed)
        model_row.addWidget(self._model_combo, 1)
        layout.addLayout(model_row)

        self._content_splitter = QSplitter(Qt.Orientation.Vertical)
        self._content_splitter.setChildrenCollapsible(False)
        layout.addWidget(self._content_splitter, 1)

        self._selection_section = CollapsibleSection("", expanded=True)
        sel_layout = self._selection_section.content_layout()
        sel_layout.setSpacing(8)

        selection_header_row = QHBoxLayout()
        self._selection_summary_label = QLabel("")
        selection_header_row.addWidget(self._selection_summary_label)
        selection_header_row.addStretch(1)

        self._clear_selections_btn = QPushButton("")
        self._clear_selections_btn.clicked.connect(
            self._fire_clear_selections_requested
        )
        selection_header_row.addWidget(self._clear_selections_btn)
        sel_layout.addLayout(selection_header_row)

        self._selection_warning_label = QLabel("")
        self._selection_warning_label.setWordWrap(True)
        self._selection_warning_label.setStyleSheet(
            "color: #9a3412; background: #ffedd5; border-radius: 6px; padding: 6px 8px;"
        )
        self._selection_warning_label.setVisible(False)
        sel_layout.addWidget(self._selection_warning_label)

        self._selection_list_scroll = QScrollArea()
        self._selection_list_scroll.setWidgetResizable(True)
        self._selection_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._selection_list_container = QWidget()
        self._selection_list_layout = QVBoxLayout(self._selection_list_container)
        self._selection_list_layout.setContentsMargins(0, 0, 0, 0)
        self._selection_list_layout.setSpacing(8)
        self._selection_list_scroll.setWidget(self._selection_list_container)
        sel_layout.addWidget(self._selection_list_scroll, 1)

        self._combined_label = QLabel("")
        self._combined_label.setStyleSheet("font-weight: bold;")
        sel_layout.addWidget(self._combined_label)

        self._combined_preview_edit = QTextEdit()
        self._combined_preview_edit.setReadOnly(True)
        self._combined_preview_edit.setMinimumHeight(120)
        sel_layout.addWidget(self._combined_preview_edit)

        self._force_image_checkbox = QCheckBox("")
        self._force_image_checkbox.setChecked(False)
        self._force_image_checkbox.toggled.connect(self._fire_force_image_toggled)
        sel_layout.addWidget(self._force_image_checkbox)

        self._content_splitter.addWidget(self._selection_section)

        self._ai_section = CollapsibleSection("", expanded=True)
        ai_layout = self._ai_section.content_layout()
        ai_layout.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        ai_layout.addWidget(self._progress_bar)

        action_row = QHBoxLayout()
        self._plotly_toggle_btn = QToolButton()
        self._plotly_toggle_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self._plotly_toggle_btn.clicked.connect(self._cycle_plotly_mode)
        self._plotly_toggle_btn.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._plotly_toggle_btn.customContextMenuRequested.connect(
            self._show_plotly_mode_menu
        )
        self._plotly_mode_menu = QMenu(self)
        self._plotly_mode_actions: dict[str, object] = {}
        for mode, label in (("off", "OFF"), ("json", "JSON"), ("python", "Python")):
            action = self._plotly_mode_menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, selected_mode=mode: self._set_plotly_mode(
                    selected_mode,
                    emit=True,
                )
            )
            self._plotly_mode_actions[mode] = action
        action_row.addWidget(self._plotly_toggle_btn)
        action_row.addStretch(1)
        ai_layout.addLayout(action_row)

        self._tab_widget = QTabWidget()
        self._tab_widget.currentChanged.connect(self._handle_tab_changed)
        ai_layout.addWidget(self._tab_widget, 1)

        export_row = QHBoxLayout()
        export_row.addStretch(1)
        self._export_btn = QPushButton("")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._fire_export_requested)
        export_row.addWidget(self._export_btn)
        ai_layout.addLayout(export_row)

        # --- 翻訳タブ ---
        translation_tab = QWidget()
        translation_layout = QVBoxLayout(translation_tab)

        # 翻訳ボタン群（横並び）
        btn_layout = QHBoxLayout()
        self._translate_btn = QPushButton("")
        self._translate_btn.clicked.connect(lambda: self._fire_translate(False))
        btn_layout.addWidget(self._translate_btn)

        self._explain_btn = QPushButton("")
        self._explain_btn.clicked.connect(lambda: self._fire_translate(True))
        btn_layout.addWidget(self._explain_btn)
        translation_layout.addLayout(btn_layout)

        # Phase 4: 翻訳結果表示エリアを QWebEngineView に差し替え
        self._translation_result = QWebEngineView()
        translation_layout.addWidget(self._translation_result)

        self._tab_widget.addTab(translation_tab, "")

        # --- カスタムプロンプトタブ ---
        custom_tab = QWidget()
        custom_layout = QVBoxLayout(custom_tab)

        # プロンプト入力欄
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setMaximumHeight(100)
        custom_layout.addWidget(self._prompt_edit)

        # 送信ボタン
        self._submit_btn = QPushButton("")
        self._submit_btn.clicked.connect(self._fire_custom_prompt)
        custom_layout.addWidget(self._submit_btn)

        # Phase 4: カスタム結果表示エリアも QWebEngineView に差し替え
        self._custom_result = QWebEngineView()
        custom_layout.addWidget(self._custom_result)

        self._tab_widget.addTab(custom_tab, "")

        self._content_splitter.addWidget(self._ai_section)
        self._content_splitter.setSizes([340, 420])

        cache_row = QHBoxLayout()
        self._cache_label = QLabel("")
        cache_row.addWidget(self._cache_label, 1)
        self._cache_toggle_btn = QPushButton("")
        self._cache_toggle_btn.setFixedWidth(60)
        self._cache_toggle_btn.clicked.connect(self._fire_cache_toggle)
        cache_row.addWidget(self._cache_toggle_btn)
        layout.addLayout(cache_row)

        self._selection_toggle_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+T"), self
        )
        self._selection_toggle_shortcut.activated.connect(
            self._selection_section.toggle
        )

        self._ai_toggle_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+I"), self
        )
        self._ai_toggle_shortcut.activated.connect(self._ai_section.toggle)

        # ローディング中に無効化する全ボタンのリスト
        self._all_buttons = [
            self._clear_selections_btn,
            self._plotly_toggle_btn,
            self._translate_btn,
            self._explain_btn,
            self._submit_btn,
            self._export_btn,
            self._cache_toggle_btn,
        ]

        self._translation_result_has_content = False
        self._custom_result_has_content = False
        self._apply_plotly_mode_visuals()
        self._refresh_selection_widgets()

    # --- ISidePanelView Display commands ---

    def set_selected_text(self, text: str) -> None:
        """後方互換のため、連結プレビュー欄に単一テキストを表示する。"""
        self.set_combined_selection_preview(text)

    def set_selected_content_preview(
        self, text: str, thumbnail: bytes | None
    ) -> None:
        """後方互換のため、連結プレビュー欄に単一テキストを表示する。"""
        self.set_combined_selection_preview(text)

    def update_result_text(self, text: str) -> None:
        """現在アクティブなタブの結果表示エリアに Markdown→HTML を反映する。

        Phase 4 で QTextEdit → QWebEngineView に差し替えたため、
        Markdown テキストを HTML に変換して setHtml する。
        """
        html = _render_markdown_html(text)
        current_tab = self._tab_widget.currentIndex()
        if current_tab == 0:
            self._translation_result_has_content = True
            self._translation_result.setHtml(html, self._katex_base_url)
        else:
            self._custom_result_has_content = True
            self._custom_result.setHtml(html, self._katex_base_url)

    def set_export_enabled(self, enabled: bool) -> None:
        """共有 export ボタンの有効/無効を切り替える。"""
        self._export_btn.setEnabled(enabled)

    def set_selection_snapshot(self, snapshot: SelectionSnapshot) -> None:
        """複数選択一覧のスナップショットを表示に反映する。"""
        self._selection_snapshot = snapshot
        self._refresh_selection_widgets()

    def set_combined_selection_preview(self, text: str) -> None:
        """AI 送信用の連結プレビュー文字列を表示する。"""
        self._combined_selection_preview = text
        self._combined_preview_edit.setPlainText(text)

    def show_loading(self, loading: bool) -> None:
        """ローディングバーの表示切り替えとボタンの有効/無効を制御する。"""
        self._progress_bar.setVisible(loading)
        for btn in self._all_buttons:
            btn.setEnabled(not loading)

    def update_cache_status_brief(self, text: str) -> None:
        """キャッシュステータスラベルのテキストを差し替える。

        カウントダウン中は _on_countdown_tick が残り時間を追記するため、
        ここではベーステキストを保持して即時反映する。
        """
        self._cache_base_text = text
        self._cache_label.setText(text)

    def set_active_tab(self, mode: str) -> None:
        """モード文字列に対応するタブをアクティブにする。"""
        # _TAB_NAMES の逆引きでインデックスを特定する。
        for idx, name in _TAB_NAMES.items():
            if name == mode:
                self._tab_widget.setCurrentIndex(idx)
                return

    def apply_ui_texts(self, texts: SidePanelTexts) -> None:
        """Presenter が解決済みの UI 文言束を適用する。"""
        self._texts = texts
        self._model_label.setText(self._text("model_label"))
        self._selection_section.set_title(self._text("selection_section_title"))
        self._clear_selections_btn.setText(self._text("selection_clear_button"))
        self._selection_warning_label.setText(self._text("selection_warning_text"))
        self._combined_label.setText(self._text("selection_preview_label"))
        self._combined_preview_edit.setPlaceholderText(
            self._text("selection_preview_placeholder")
        )
        self._force_image_checkbox.setText(self._text("selection_force_image_text"))
        self._ai_section.set_title(self._text("ai_section_title"))
        self._apply_plotly_mode_visuals()
        self._translate_btn.setText(self._text("translation_button_text"))
        self._explain_btn.setText(self._text("translation_explain_button_text"))
        self._export_btn.setText(self._text("export_button_text"))
        self._tab_widget.setTabText(0, self._text("translation_tab_text"))
        self._prompt_edit.setPlaceholderText(self._text("custom_prompt_placeholder"))
        self._submit_btn.setText(self._text("custom_submit_button_text"))
        self._tab_widget.setTabText(1, self._text("custom_tab_text"))
        self._cache_base_text = self._text("cache_status_placeholder")
        self._cache_label.setText(self._cache_base_text)
        self._cache_toggle_btn.setText(
            self._cache_toggle_text()
        )
        self._sync_model_combo_placeholder()
        if not self._translation_result_has_content:
            self._set_translation_placeholder()
        if not self._custom_result_has_content:
            self._set_custom_placeholder()
        self._refresh_selection_widgets()

    # --- ISidePanelView Callback registration ---

    def set_on_translate_requested(
        self, cb: Callable[[bool], None]
    ) -> None:
        """翻訳ボタン押下時に呼ばれるコールバックを登録する。"""
        self._on_translate_requested = cb

    def set_on_custom_prompt_submitted(
        self, cb: Callable[[str], None]
    ) -> None:
        """カスタムプロンプト送信時に呼ばれるコールバックを登録する。"""
        self._on_custom_prompt_submitted = cb

    def set_on_export_requested(self, cb: Callable[[], None]) -> None:
        """共有 export ボタン押下時に呼ばれるコールバックを登録する。"""
        self._on_export_requested = cb

    def set_on_tab_changed(self, cb: Callable[[str], None]) -> None:
        """タブ切り替え時に呼ばれるコールバックを登録する。"""
        self._on_tab_changed = cb

    def set_on_force_image_toggled(
        self, cb: Callable[[bool], None]
    ) -> None:
        """「画像としても送信」チェックボックスの切り替えコールバックを登録する。"""
        self._on_force_image_toggled = cb

    def set_on_plotly_mode_changed(
        self, cb: Callable[[str], None]
    ) -> None:
        """Plotly 可視化モード変更コールバックを登録する。"""
        self._on_plotly_mode_changed = cb

    def set_on_selection_delete_requested(
        self, cb: Callable[[str], None]
    ) -> None:
        """選択一覧の個別削除要求コールバックを登録する。"""
        self._on_selection_delete_requested = cb

    def set_on_clear_selections_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """選択一覧の全消去要求コールバックを登録する。"""
        self._on_clear_selections_requested = cb

    # --- Phase 6: モデル選択 ---

    def set_available_models(self, model_names: list[str]) -> None:
        """モデル選択プルダウンの選択肢を設定する。

        候補一覧だけを差し替え、enabled 状態は Presenter 側で制御する。
        """
        current = self._model_combo.currentText()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        if model_names:
            self._model_combo.addItems(model_names)
            idx = self._model_combo.findText(current)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
            else:
                self._model_combo.setCurrentIndex(-1)
        else:
            self._model_combo.setCurrentIndex(-1)
        self._sync_model_combo_placeholder()
        self._model_combo.blockSignals(False)

    def set_selected_model(self, model_name: str) -> None:
        """モデル選択プルダウンの現在値を設定する。"""
        self._model_combo.blockSignals(True)
        if not model_name:
            self._model_combo.setCurrentIndex(-1)
        else:
            idx = self._model_combo.findText(model_name)
            self._model_combo.setCurrentIndex(idx if idx >= 0 else -1)
        self._sync_model_combo_placeholder()
        self._model_combo.blockSignals(False)

    def set_on_model_changed(
        self, cb: Callable[[str], None]
    ) -> None:
        """モデル選択プルダウンの変更時コールバックを登録する。"""
        self._on_model_changed = cb

    def set_model_combo_enabled(self, enabled: bool) -> None:
        """モデル選択プルダウンの有効/無効を切り替える。"""
        self._model_combo.setEnabled(enabled and self._model_combo.count() > 0)
        self._sync_model_combo_placeholder()

    def set_plotly_mode(self, mode: str) -> None:
        """Plotly 可視化モードを UI に反映する。"""
        self._set_plotly_mode(mode, emit=False)

    # --- Phase 7: キャッシュ操作 ---

    def set_on_cache_create_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """キャッシュ作成ボタン押下時のコールバックを登録する。"""
        self._on_cache_create_requested = cb

    def set_on_cache_invalidate_requested(
        self, cb: Callable[[], None]
    ) -> None:
        """キャッシュ削除ボタン押下時のコールバックを登録する。"""
        self._on_cache_invalidate_requested = cb

    def set_cache_active(self, active: bool) -> None:
        """キャッシュ状態に応じてトグルボタンのテキストを切り替える。"""
        self._cache_is_active = active
        self._cache_toggle_btn.setText(self._cache_toggle_text())

    def set_cache_button_enabled(self, enabled: bool) -> None:
        """キャッシュトグルボタンの有効/無効を制御する。"""
        self._cache_toggle_btn.setEnabled(enabled)

    def show_confirm_dialog(self, title: str, message: str) -> bool:
        """確認ダイアログを表示し、OK なら True を返す。"""
        result = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Ok

    # --- Phase 7.5: キャッシュカウントダウン ---

    def start_cache_countdown(self, expire_time: str) -> None:
        """ISO 形式の expire_time からカウントダウンを開始する。

        1 秒間隔の QTimer で残り時間を H:MM:SS 形式で
        _cache_label に追記していく。
        """
        # ISO 8601 パース（末尾 Z を UTC として扱う）
        et = expire_time.replace("Z", "+00:00")
        self._expire_time_utc = datetime.fromisoformat(et).astimezone(
            timezone.utc
        )
        # 開始時に即座に 1 回表示を更新してからタイマーを開始する
        self._on_countdown_tick()
        self._countdown_timer.start()

    def stop_cache_countdown(self) -> None:
        """カウントダウンを停止する。"""
        self._countdown_timer.stop()
        self._expire_time_utc = None

    def set_on_cache_expired(self, cb: Callable[[], None]) -> None:
        """カウントダウン 0 到達時のコールバックを登録する。"""
        self._on_cache_expired = cb

    def _on_countdown_tick(self) -> None:
        """1 秒ごとに残り時間を計算しラベルを更新する。"""
        if self._expire_time_utc is None:
            return
        now = datetime.now(timezone.utc)
        remaining = (self._expire_time_utc - now).total_seconds()
        if remaining <= 0:
            self._countdown_timer.stop()
            self._cache_label.setText(
                self._cache_base_text + " — " + self._text("cache_expired_text")
            )
            self._expire_time_utc = None
            if self._on_cache_expired:
                self._on_cache_expired()
            return
        # H:MM:SS 形式
        total_sec = int(remaining)
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        self._cache_label.setText(
            f"{self._cache_base_text} — {self._text('cache_remaining_template', time=f'{h}:{m:02d}:{s:02d}') }"
        )

    def _refresh_selection_widgets(self) -> None:
        """現在の snapshot に基づいて選択一覧 UI を再構築する。"""
        self._selection_summary_label.setText(
            self._text(
                "selection_summary_template",
                count=len(self._selection_snapshot.slots),
            )
        )
        self._selection_warning_label.setVisible(
            len(self._selection_snapshot.slots) > 10
        )
        self._clear_selections_btn.setEnabled(
            not self._selection_snapshot.is_empty
        )

        self._clear_layout(self._selection_list_layout)

        if self._selection_snapshot.is_empty:
            empty_label = QLabel(self._text("selection_empty_text"))
            empty_label.setStyleSheet("color: #64748b; padding: 6px 2px;")
            self._selection_list_layout.addWidget(empty_label)
        else:
            for slot in self._selection_snapshot.slots:
                self._selection_list_layout.addWidget(
                    _SelectionCard(
                        slot,
                        text_for=self._text,
                        on_delete_requested=self._fire_selection_delete_requested,
                    )
                )

        self._selection_list_layout.addStretch(1)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """レイアウト配下の子ウィジェットをすべて除去する。"""
        while layout.count() > 0:
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _fire_selection_delete_requested(self, selection_id: str) -> None:
        """選択カードの削除要求を Presenter に通知する。"""
        if self._on_selection_delete_requested:
            self._on_selection_delete_requested(selection_id)

    def _fire_clear_selections_requested(self) -> None:
        """全消去要求を Presenter に通知する。"""
        if self._on_clear_selections_requested:
            self._on_clear_selections_requested()

    # --- Internal event handlers ---

    def _fire_translate(self, include_explanation: bool) -> None:
        """翻訳ボタンのクリックをコールバックに変換する。"""
        if self._on_translate_requested:
            self._on_translate_requested(include_explanation)

    def _fire_custom_prompt(self) -> None:
        """送信ボタンのクリックをコールバックに変換する。"""
        if self._on_custom_prompt_submitted:
            self._on_custom_prompt_submitted(
                self._prompt_edit.toPlainText()
            )

    def _fire_export_requested(self) -> None:
        """共有 export ボタンのクリックをコールバックに変換する。"""
        if self._on_export_requested:
            self._on_export_requested()

    def _fire_force_image_toggled(self, checked: bool) -> None:
        """チェックボックスの切り替えをコールバックに変換する。"""
        if self._on_force_image_toggled:
            self._on_force_image_toggled(checked)

    def _cycle_plotly_mode(self) -> None:
        """Plotly トグルを OFF -> JSON -> Python の順で循環させる。"""
        current_index = _PLOTLY_MODE_ORDER.index(self._plotly_mode)
        next_mode = _PLOTLY_MODE_ORDER[(current_index + 1) % len(_PLOTLY_MODE_ORDER)]
        self._set_plotly_mode(next_mode, emit=True)

    def _show_plotly_mode_menu(self, position) -> None:
        """右クリック位置に Plotly モード選択メニューを表示する。"""
        self._plotly_mode_menu.exec(self._plotly_toggle_btn.mapToGlobal(position))

    def _set_plotly_mode(self, mode: str, *, emit: bool) -> None:
        """内部状態を更新し、必要なら Presenter へ変更通知する。"""
        if mode not in _PLOTLY_MODE_ORDER:
            mode = "off"
        self._plotly_mode = mode
        self._apply_plotly_mode_visuals()
        if emit and self._on_plotly_mode_changed is not None:
            self._on_plotly_mode_changed(mode)

    def _apply_plotly_mode_visuals(self) -> None:
        """現在モードに応じてトグルの見た目と tooltip を切り替える。"""
        mode_text = "📊"
        tool_tip = self._text("plotly_toggle_tooltip_off")
        style = (
            "QToolButton { background: #e5e7eb; color: #4b5563; border-radius: 6px; padding: 4px 10px; font-weight: bold; }"
        )
        if self._plotly_mode == "json":
            # JSON モードは Phase 1 の従来挙動に近いことを青系で表現する。
            mode_text = "📊 J"
            tool_tip = self._text("plotly_toggle_tooltip_json")
            style = (
                "QToolButton { background: #dbeafe; color: #1d4ed8; border-radius: 6px; padding: 4px 10px; font-weight: bold; }"
            )
        elif self._plotly_mode == "python":
            # Python モードは sandbox 実行が入るため、別系統の緑で区別する。
            mode_text = "📊 Py"
            tool_tip = self._text("plotly_toggle_tooltip_python")
            style = (
                "QToolButton { background: #dcfce7; color: #15803d; border-radius: 6px; padding: 4px 10px; font-weight: bold; }"
            )

        self._plotly_toggle_btn.setText(mode_text)
        self._plotly_toggle_btn.setToolTip(tool_tip)
        self._plotly_toggle_btn.setStyleSheet(style)

    def _fire_model_changed(self, model_name: str) -> None:
        """モデルプルダウンの変更をコールバックに変換する。"""
        if self._on_model_changed and model_name:
            self._on_model_changed(model_name)

    def _fire_cache_toggle(self) -> None:
        """キャッシュトグルボタンのクリックを状態に応じたコールバックに変換する。"""
        if self._cache_is_active:
            if self._on_cache_invalidate_requested:
                self._on_cache_invalidate_requested()
        else:
            if self._on_cache_create_requested:
                self._on_cache_create_requested()

    def _handle_tab_changed(self, index: int) -> None:
        """QTabWidget のタブ切り替えシグナルをコールバックに変換する。"""
        if self._on_tab_changed and index in _TAB_NAMES:
            self._on_tab_changed(_TAB_NAMES[index])

    def _text(self, field_name: str, **kwargs: object) -> str:
        if self._texts is None:
            return ""
        template = getattr(self._texts, field_name)
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except (IndexError, KeyError, ValueError):
            return template

    def _cache_toggle_text(self) -> str:
        return self._text(
            "cache_delete_button_text"
            if self._cache_is_active
            else "cache_create_button_text"
        )

    def _sync_model_combo_placeholder(self) -> None:
        if self._model_combo.currentIndex() < 0:
            self._model_combo.setPlaceholderText(
                self._text("model_unset_placeholder")
            )
        else:
            self._model_combo.setPlaceholderText("")

    def _set_translation_placeholder(self) -> None:
        self._translation_result.setHtml(
            "<html><body style='color:#999;font-size:14px;'>"
            f"{self._text('translation_placeholder_text')}</body></html>",
            self._katex_base_url,
        )

    def _set_custom_placeholder(self) -> None:
        self._custom_result.setHtml(
            "<html><body style='color:#999;font-size:14px;'>"
            f"{self._text('custom_placeholder_text')}</body></html>",
            self._katex_base_url,
        )
