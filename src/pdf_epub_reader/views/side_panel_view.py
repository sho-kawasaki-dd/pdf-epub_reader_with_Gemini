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
from pathlib import Path

import markdown
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# タブインデックスと AnalysisMode.value の対応。
# Presenter は文字列でモードを受け取るため、ここで変換する。
_TAB_NAMES = {0: "translation", 1: "custom_prompt"}


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

    def _header_text(self) -> str:
        prefix = "▼" if self._expanded else "▶"
        return f"{prefix} {self._title}"

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._toggle_btn.setText(self._header_text())


class SidePanelView(QWidget):
    """ISidePanelView Protocol を満たすサイドパネル実装。

    上から順に「選択テキスト（折りたたみ可能）」
    「ローディングバー」「タブ（翻訳 / カスタム）」「キャッシュステータス」
    を縦積みし、ボタンイベントはコールバックで外部に通知する。

    Phase 4 で AI 回答欄を QWebEngineView + KaTeX に差し替え、
    Markdown・数式・化学式のレンダリングに対応した。
    Phase 6.5 で選択プレビュー部分を CollapsibleSection で折りたたみ可能にした。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # --- KaTeX ローカルバンドルの baseUrl ---
        # Chromium が file:/// リソースを読み込めるよう、
        # setHtml() の第二引数に渡す QUrl を保持する。
        katex_dir = _get_katex_dir()
        self._katex_base_url = QUrl.fromLocalFile(str(katex_dir) + "/")

        # --- コールバック保持用 ---
        self._on_translate_requested: Callable[[bool], None] | None = None
        self._on_custom_prompt_submitted: Callable[[str], None] | None = None
        self._on_tab_changed: Callable[[str], None] | None = None
        self._on_force_image_toggled: Callable[[bool], None] | None = None
        self._on_model_changed: Callable[[str], None] | None = None

        # --- ウィジェット構築 ---
        layout = QVBoxLayout(self)

        # Phase 6: モデル選択プルダウン
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("モデル:"))
        self._model_combo = QComboBox()
        self._model_combo.currentTextChanged.connect(self._fire_model_changed)
        model_row.addWidget(self._model_combo, 1)
        layout.addLayout(model_row)

        # 選択テキスト（折りたたみ可能セクション）
        self._selection_section = CollapsibleSection("選択テキスト", expanded=True)
        sel_layout = self._selection_section.content_layout()

        self._selected_text_edit = QTextEdit()
        self._selected_text_edit.setReadOnly(True)
        self._selected_text_edit.setMaximumHeight(120)
        self._selected_text_edit.setPlaceholderText(
            "ドキュメント上でテキストを選択してください"
        )
        sel_layout.addWidget(self._selected_text_edit)

        # Phase 4: サムネイルプレビュー（クロップ画像がある場合のみ表示）
        self._thumbnail_label = QLabel()
        self._thumbnail_label.setMaximumHeight(100)
        self._thumbnail_label.setVisible(False)
        sel_layout.addWidget(self._thumbnail_label)

        # Phase 4:「画像としても送信」チェックボックス
        self._force_image_checkbox = QCheckBox("画像としても送信")
        self._force_image_checkbox.setChecked(False)
        self._force_image_checkbox.toggled.connect(self._fire_force_image_toggled)
        sel_layout.addWidget(self._force_image_checkbox)

        layout.addWidget(self._selection_section)

        # ローディングバー（通常は非表示）
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate モード
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # タブウィジェット
        self._tab_widget = QTabWidget()
        self._tab_widget.currentChanged.connect(self._handle_tab_changed)
        layout.addWidget(self._tab_widget)

        # --- 翻訳タブ ---
        translation_tab = QWidget()
        translation_layout = QVBoxLayout(translation_tab)

        # 翻訳ボタン群（横並び）
        btn_layout = QHBoxLayout()
        self._translate_btn = QPushButton("翻訳")
        self._translate_btn.clicked.connect(lambda: self._fire_translate(False))
        btn_layout.addWidget(self._translate_btn)

        self._explain_btn = QPushButton("解説付き翻訳")
        self._explain_btn.clicked.connect(lambda: self._fire_translate(True))
        btn_layout.addWidget(self._explain_btn)
        translation_layout.addLayout(btn_layout)

        # Phase 4: 翻訳結果表示エリアを QWebEngineView に差し替え
        self._translation_result = QWebEngineView()
        self._translation_result.setHtml(
            "<html><body style='color:#999;font-size:14px;'>"
            "翻訳結果がここに表示されます</body></html>",
            self._katex_base_url,
        )
        translation_layout.addWidget(self._translation_result)

        self._tab_widget.addTab(translation_tab, "翻訳")

        # --- カスタムプロンプトタブ ---
        custom_tab = QWidget()
        custom_layout = QVBoxLayout(custom_tab)

        # プロンプト入力欄
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setMaximumHeight(100)
        self._prompt_edit.setPlaceholderText("カスタムプロンプトを入力...")
        custom_layout.addWidget(self._prompt_edit)

        # 送信ボタン
        self._submit_btn = QPushButton("送信")
        self._submit_btn.clicked.connect(self._fire_custom_prompt)
        custom_layout.addWidget(self._submit_btn)

        # Phase 4: カスタム結果表示エリアも QWebEngineView に差し替え
        self._custom_result = QWebEngineView()
        self._custom_result.setHtml(
            "<html><body style='color:#999;font-size:14px;'>"
            "結果がここに表示されます</body></html>",
            self._katex_base_url,
        )
        custom_layout.addWidget(self._custom_result)

        self._tab_widget.addTab(custom_tab, "カスタムプロンプト")

        # キャッシュステータス
        self._cache_label = QLabel("キャッシュステータス: ---")
        layout.addWidget(self._cache_label)

        # ローディング中に無効化する全ボタンのリスト
        self._all_buttons = [
            self._translate_btn,
            self._explain_btn,
            self._submit_btn,
        ]

    # --- ISidePanelView Display commands ---

    def set_selected_text(self, text: str) -> None:
        """選択テキスト欄の内容を差し替える。"""
        self._selected_text_edit.setPlainText(text)
        # テキストのみの場合はサムネイルを非表示にする
        self._thumbnail_label.setVisible(False)

    def set_selected_content_preview(
        self, text: str, thumbnail: bytes | None
    ) -> None:
        """選択テキストとサムネイル画像のプレビューを表示する。

        Phase 4 で追加。テキストに加え、クロップ画像のサムネイルも
        表示できるようにする。thumbnail が None ならサムネイルは非表示。
        """
        self._selected_text_edit.setPlainText(text)
        if thumbnail:
            pixmap = QPixmap()
            pixmap.loadFromData(thumbnail)
            # サムネイルは最大幅をパネル幅に合わせ、高さ100pxに収める
            self._thumbnail_label.setPixmap(
                pixmap.scaledToHeight(100, mode=Qt.SmoothTransformation)
            )
            self._thumbnail_label.setVisible(True)
        else:
            self._thumbnail_label.setVisible(False)

    def update_result_text(self, text: str) -> None:
        """現在アクティブなタブの結果表示エリアに Markdown→HTML を反映する。

        Phase 4 で QTextEdit → QWebEngineView に差し替えたため、
        Markdown テキストを HTML に変換して setHtml する。
        """
        html = _render_markdown_html(text)
        current_tab = self._tab_widget.currentIndex()
        if current_tab == 0:
            self._translation_result.setHtml(html, self._katex_base_url)
        else:
            self._custom_result.setHtml(html, self._katex_base_url)

    def show_loading(self, loading: bool) -> None:
        """ローディングバーの表示切り替えとボタンの有効/無効を制御する。"""
        self._progress_bar.setVisible(loading)
        for btn in self._all_buttons:
            btn.setEnabled(not loading)

    def update_cache_status_brief(self, text: str) -> None:
        """キャッシュステータスラベルのテキストを差し替える。"""
        self._cache_label.setText(text)

    def set_active_tab(self, mode: str) -> None:
        """モード文字列に対応するタブをアクティブにする。"""
        # _TAB_NAMES の逆引きでインデックスを特定する。
        for idx, name in _TAB_NAMES.items():
            if name == mode:
                self._tab_widget.setCurrentIndex(idx)
                return

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

    def set_on_tab_changed(self, cb: Callable[[str], None]) -> None:
        """タブ切り替え時に呼ばれるコールバックを登録する。"""
        self._on_tab_changed = cb

    def set_on_force_image_toggled(
        self, cb: Callable[[bool], None]
    ) -> None:
        """「画像としても送信」チェックボックスの切り替えコールバックを登録する。"""
        self._on_force_image_toggled = cb

    # --- Phase 6: モデル選択 ---

    def set_available_models(self, model_names: list[str]) -> None:
        """モデル選択プルダウンの選択肢を設定する。"""
        current = self._model_combo.currentText()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItems(model_names)
        # 元の選択を復元できる場合は復元
        idx = self._model_combo.findText(current)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        self._model_combo.blockSignals(False)

    def set_selected_model(self, model_name: str) -> None:
        """モデル選択プルダウンの現在値を設定する。"""
        idx = self._model_combo.findText(model_name)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)

    def set_on_model_changed(
        self, cb: Callable[[str], None]
    ) -> None:
        """モデル選択プルダウンの変更時コールバックを登録する。"""
        self._on_model_changed = cb

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

    def _fire_force_image_toggled(self, checked: bool) -> None:
        """チェックボックスの切り替えをコールバックに変換する。"""
        if self._on_force_image_toggled:
            self._on_force_image_toggled(checked)

    def _fire_model_changed(self, model_name: str) -> None:
        """モデルプルダウンの変更をコールバックに変換する。"""
        if self._on_model_changed and model_name:
            self._on_model_changed(model_name)

    def _handle_tab_changed(self, index: int) -> None:
        """QTabWidget のタブ切り替えシグナルをコールバックに変換する。"""
        if self._on_tab_changed and index in _TAB_NAMES:
            self._on_tab_changed(_TAB_NAMES[index])
