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
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCheckBox,
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


class SidePanelView(QWidget):
    """ISidePanelView Protocol を満たすサイドパネル実装。

    上から順に「選択テキスト」「サムネイル」「画像送信チェック」
    「ローディングバー」「タブ（翻訳 / カスタム）」「キャッシュステータス」
    を縦積みし、ボタンイベントはコールバックで外部に通知する。

    Phase 4 で AI 回答欄を QWebEngineView + KaTeX に差し替え、
    Markdown・数式・化学式のレンダリングに対応した。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # --- コールバック保持用 ---
        self._on_translate_requested: Callable[[bool], None] | None = None
        self._on_custom_prompt_submitted: Callable[[str], None] | None = None
        self._on_tab_changed: Callable[[str], None] | None = None
        self._on_force_image_toggled: Callable[[bool], None] | None = None

        # --- ウィジェット構築 ---
        layout = QVBoxLayout(self)

        # 選択テキスト表示
        layout.addWidget(QLabel("選択テキスト:"))
        self._selected_text_edit = QTextEdit()
        self._selected_text_edit.setReadOnly(True)
        self._selected_text_edit.setMaximumHeight(120)
        self._selected_text_edit.setPlaceholderText(
            "ドキュメント上でテキストを選択してください"
        )
        layout.addWidget(self._selected_text_edit)

        # Phase 4: サムネイルプレビュー（クロップ画像がある場合のみ表示）
        self._thumbnail_label = QLabel()
        self._thumbnail_label.setMaximumHeight(100)
        self._thumbnail_label.setVisible(False)
        layout.addWidget(self._thumbnail_label)

        # Phase 4:「画像としても送信」チェックボックス
        self._force_image_checkbox = QCheckBox("画像としても送信")
        self._force_image_checkbox.setChecked(False)
        self._force_image_checkbox.toggled.connect(self._fire_force_image_toggled)
        layout.addWidget(self._force_image_checkbox)

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
            "翻訳結果がここに表示されます</body></html>"
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
            "結果がここに表示されます</body></html>"
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
            self._translation_result.setHtml(html)
        else:
            self._custom_result.setHtml(html)

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

    def _handle_tab_changed(self, index: int) -> None:
        """QTabWidget のタブ切り替えシグナルをコールバックに変換する。"""
        if self._on_tab_changed and index in _TAB_NAMES:
            self._on_tab_changed(_TAB_NAMES[index])
