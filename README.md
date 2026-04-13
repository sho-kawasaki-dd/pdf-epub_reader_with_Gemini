# Gem Read

## 概要 / Overview

日本語:

Gem Read は、PySide6 ベースのローカルデスクトップ向け PDF / EPUB ビューアです。ドキュメントを画像として表示しながら、選択した範囲を Gemini に送信して翻訳、解説付き翻訳、カスタム解析を行えます。

AI 機能を使わなくても、文書の閲覧、ズーム、目次ジャンプ、複数範囲選択、UI 言語切替などのローカル機能は利用できます。

本リポジトリの README は v1.0.0 時点の実装を基準にしています。

English:

Gem Read is a local desktop PDF/EPUB viewer built with PySide6. It renders documents as images and lets you send selected regions to Gemini for translation, translation with explanation, and custom analysis.

You can still use the local viewer features without AI, including document viewing, zooming, table-of-contents navigation, multi-region selection, and UI language switching.

This README reflects the implementation state of version 1.0.0.

## 主な機能 / Key Features

日本語:

- PDF / EPUB の表示
- 高 DPI を考慮したズーム表示
- 複数矩形選択と順序付きプレビュー
- 選択領域のテキスト送信と画像付きマルチモーダル送信
- Gemini モデルの切り替え
- 翻訳、解説付き翻訳、カスタムプロンプト解析
- Context Cache の作成、削除、TTL 更新、一覧確認
- Markdown、LaTeX 数式、化学式の表示
- 目次パネルからのページ移動
- 日本語 / English の UI 切替
- レンダリング、検出、AI 設定をまとめた設定ダイアログ

English:

- PDF and EPUB viewing
- High-DPI-aware zooming
- Multi-rectangle selection with ordered preview
- Text-only and image-assisted multimodal Gemini requests
- Gemini model switching
- Translation, translation with explanation, and custom prompt analysis
- Context cache creation, deletion, TTL update, and listing
- Markdown, LaTeX math, and chemical formula rendering
- Page navigation from the table-of-contents panel
- Japanese / English UI switching
- Unified settings dialog for rendering, detection, and AI options

## 動作要件 / Requirements

日本語:

- Python 3.13 以上
- GUI を表示できるデスクトップ環境
- Gemini API を使う場合は `GEMINI_API_KEY`
- 依存関係は `pyproject.toml` で管理されています

主なランタイム依存は PySide6、PyMuPDF、google-genai、qasync、markdown、Pillow、python-dotenv、platformdirs です。

English:

- Python 3.13 or newer
- A desktop environment capable of running a GUI application
- `GEMINI_API_KEY` if you want to use Gemini features
- Dependencies are managed in `pyproject.toml`

Main runtime dependencies include PySide6, PyMuPDF, google-genai, qasync, markdown, Pillow, python-dotenv, and platformdirs.

## インストール / Installation

日本語:

`uv` を使う前提の最小セットアップです。

```bash
uv sync --dev
```

`.env.example` をもとに `.env` を作成し、Gemini を使う場合は API キーを設定します。

```env
GEMINI_API_KEY=your-api-key-here
```

アプリを起動します。

```bash
uv run python -m pdf_epub_reader
```

Windows PowerShell では、リポジトリルートの起動スクリプトも使えます。

```powershell
.\gem-read_launch.ps1
```

English:

This is the minimal setup flow using `uv`.

```bash
uv sync --dev
```

Create a `.env` file from `.env.example` and set your API key if you want to use Gemini.

```env
GEMINI_API_KEY=your-api-key-here
```

Start the application.

```bash
uv run python -m pdf_epub_reader
```

On Windows PowerShell, you can also use the launcher script from the repository root.

```powershell
.\gem-read_launch.ps1
```

## 設定 / Configuration

日本語:

- AI 機能は環境変数 `GEMINI_API_KEY` を使います
- ユーザー設定は OS 標準の設定ディレクトリに JSON で保存されます
- UI 表示言語と AI 出力言語は別設定です
- 設定ダイアログでは、レンダリング形式、JPEG 品質、DPI、ページキャッシュ数、自動画像検出、自動数式検出、モデル選択、翻訳プロンプト、出力言語、キャッシュ TTL を変更できます

English:

- AI features use the `GEMINI_API_KEY` environment variable
- User settings are stored as JSON in the OS-standard configuration directory
- UI language and AI output language are separate settings
- The settings dialog lets you change render format, JPEG quality, DPI, page cache size, automatic image detection, automatic math detection, model selection, translation prompt, output language, and cache TTL

## 使い方 / Usage

日本語:

1. アプリを起動し、ファイルを開きます。
2. PDF または EPUB を表示します。
3. ドキュメント上をドラッグして範囲選択します。
4. 複数選択したい場合は `Ctrl+ドラッグ` で追加します。
5. サイドパネルでモデルを選び、翻訳、解説付き翻訳、またはカスタム解析を実行します。
6. 必要に応じてキャッシュを作成し、キャッシュ管理ダイアログで状態や TTL を確認します。
7. 目次パネル、設定ダイアログ、表示言語ダイアログを使って表示や挙動を調整します。

主なショートカット:

- `Ctrl+B`: 目次パネルの表示切替
- `Ctrl+,`: 設定ダイアログ
- `Ctrl+Shift+G`: キャッシュ管理
- `Esc`: 現在の選択をクリア

English:

1. Start the application and open a file.
2. Display a PDF or EPUB document.
3. Drag on the document to create a selection.
4. Use `Ctrl+drag` to append additional selections.
5. Choose a model in the side panel and run translation, translation with explanation, or custom analysis.
6. Create a cache when needed, then inspect its state or TTL from the cache management dialog.
7. Use the table-of-contents panel, settings dialog, and language dialog to adjust behavior and presentation.

Main shortcuts:

- `Ctrl+B`: Toggle the table-of-contents panel
- `Ctrl+,`: Open the settings dialog
- `Ctrl+Shift+G`: Open cache management
- `Esc`: Clear the current selection

## 既知の制約 / Known Limitations

日本語:

- `GEMINI_API_KEY` が未設定でもアプリは起動しますが、AI 機能は利用できません
- 本 README にはスクリーンショットを含めていません
- ライセンス条件の詳細は `LICENSE` ファイルを参照してください
- OS ごとの配布手順やバイナリ配布はこの README の対象外です

English:

- The application can start without `GEMINI_API_KEY`, but AI features will not be available
- This README does not include screenshots
- See the `LICENSE` file for the full license terms
- OS-specific packaging and binary distribution are outside the scope of this README

## ライセンス / License

日本語:

このプロジェクトは AGPL-3.0-or-later の下で提供されます。詳細は `LICENSE` ファイルを参照してください。

English:

This project is distributed under AGPL-3.0-or-later. See the `LICENSE` file for details.

## Documentation

- [docs/README.md](docs/README.md)

## Windows Launcher

- `gem-read_launch.ps1` runs `uv run python -m pdf_epub_reader` from the repository root.
- The PowerShell launcher is a convenience wrapper; the canonical module entry point remains `python -m pdf_epub_reader`.
