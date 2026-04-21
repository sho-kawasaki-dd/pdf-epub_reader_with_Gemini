# Desktop Capture 翻訳・解説アプリ 企画書

## 概要

PC 版 Kindle や楽天 Kobo Desktop など、DRM 管理下のデスクトップ電子書籍アプリの画面を範囲選択でキャプチャし、OCR でテキスト化した上で Gemini API に翻訳・解説させる companion アプリを追加開発する。

既存の `gem-read` リポジトリが持つ AI 連携層・キャッシュ管理・設定管理を最大限再利用し、フロントエンド（キャプチャ UI）と OCR 前処理のみを新規追加する。

---

## 解決したい問題

| 問題 | 現状のギャップ |
|---|---|
| Kindle/Kobo は PDF/EPUB ファイルを直接開けない | 既存の `pdf_epub_reader` は PyMuPDF 前提 |
| DRM 書籍のテキストはクリップボード経由で取りにくい | DOM アクセス・Accessibility API は信頼性が低い |
| 画面上の文章をそのまま翻訳・解説したい | ブラウザ拡張は Web ページ専用 |

---

## 方針

1. **OCR なしの PoC → OCR 併用の本番** の 2 段階で進める
2. 最初から **Windows OCR API と RapidOCR を切り替え可能** にしてバックエンド選択を早期に検証できるようにする
3. Gemini AI 層・キャッシュ・設定管理は **既存コードを直接再利用**、新規コードは最小限に抑える
4. 既存の `pdf_epub_reader` / `browser_api` には **変更を加えない**。新規パッケージを追加する

---

## アーキテクチャ

```
src/
  desktop_capture/          ← 新規パッケージ
    __init__.py
    __main__.py             ← 起動エントリ
    app.py                  ← QApplication + qasync 起動
    capture/
      overlay.py            ← 透過オーバーレイウィンドウ（矩形選択 UI）
      screenshot.py         ← 画面全体キャプチャ → 矩形 crop
    ocr/
      gateway.py            ← OcrGateway プロトコル（切り替え境界）
      windows_ocr.py        ← Windows OCR API 実装
      rapidocr_backend.py   ← RapidOCR 実装
      factory.py            ← ocr_backend 設定値からゲートウェイ生成
    presenter.py            ← キャプチャ → OCR → AI 連携のオーケストレーション
    result_window.py        ← 翻訳・解説結果を表示する小ウィンドウ
```

### 既存資産の再利用マップ

| 既存コード | desktop_capture での使い方 |
|---|---|
| `pdf_epub_reader.models.ai_model.AIModel` | そのまま `import` して Gemini 解析に使用 |
| `pdf_epub_reader.dto.AnalysisRequest/Result` | OCR テキスト + crop 画像を詰めて渡す |
| `pdf_epub_reader.utils.config.AppConfig` | `ocr_backend` フィールドを 1 つ追加して共用 |
| `pdf_epub_reader.utils.config.load_config/save_config` | 設定ファイルの読み書きをそのまま使用 |
| `qasync` イベントループ統合 | `pdf_epub_reader.infrastructure.event_loop` を参照して同じパターンで実装 |

ブラウザ拡張の矩形選択ロジック（[browser-extension/src/content/selection/rectangleSelectionController.ts](browser-extension/src/content/selection/rectangleSelectionController.ts)）と crop 処理（[browser-extension/src/background/services/cropSelectionImage.ts](browser-extension/src/background/services/cropSelectionImage.ts)）は、Python 版実装の設計見本として参照する。

---

## OCR バックエンド設計

### プロトコル（切り替え境界）

```python
from typing import Protocol

class OcrGateway(Protocol):
    async def extract_text(self, image_bytes: bytes) -> str: ...
```

### Windows OCR API 実装

- `winsdk` または `winrt` パッケージ経由で `Windows.Media.Ocr.OcrEngine` を呼ぶ
- 追加モデルファイル不要。OS に標準搭載
- Python 3.13 対応状況を着手前に確認する
- 対応言語は OS にインストール済みの言語パックに依存

### RapidOCR 実装

- `rapidocr-onnxruntime` パッケージを使用
- 日本語対応モデル（`.onnx`）を初回ダウンロードまたは同梱
- モデルサイズは数十 MB 程度
- ONNX Runtime のみに依存し PyTorch 不要

### ファクトリ

```python
def create_ocr_gateway(config: AppConfig) -> OcrGateway:
    if config.ocr_backend == "rapidocr":
        return RapidOcrGateway()
    return WindowsOcrGateway()  # デフォルト
```

---

## AppConfig への変更

`src/pdf_epub_reader/utils/config.py` の `AppConfig` に 1 フィールドを追加する。

```python
ocr_backend: Literal["windows", "rapidocr"] = "windows"
```

既存の `load_config` / `save_config` がそのまま JSON 永続化を処理するため、追加の配線は不要。

---

## 実装フェーズ

### Phase 1 — OCR なし PoC（最速検証）

目標：Kindle の画面上の選択領域を Gemini に画像として渡し、翻訳が返ってくることを確認する。

- [ ] `desktop_capture` パッケージ骨格を作成
- [ ] `capture/overlay.py`：PySide6 の透過フルスクリーンウィンドウで矩形ドラッグ選択
- [ ] `capture/screenshot.py`：`mss` または `PIL.ImageGrab` で全画面キャプチャ → crop + リサイズ
- [ ] `presenter.py`：crop 画像を `AnalysisRequest(text="", images=[...])` に詰めて `AIModel.analyze` を呼ぶ
- [ ] `result_window.py`：翻訳結果を表示する最小限のウィンドウ
- [ ] `__main__.py`：ホットキー（例: `Ctrl+Shift+G`）で矩形選択を起動
- [ ] `pyproject.toml` に `mss` または `keyboard` を追加

### Phase 2 — OCR 前処理の追加

目標：テキストを OCR で抽出し、画像は補助入力として添付することで解析精度を上げる。

- [ ] `ocr/gateway.py`：`OcrGateway` プロトコル定義
- [ ] `ocr/windows_ocr.py`：Windows OCR API 実装
- [ ] `ocr/factory.py`：ファクトリ実装
- [ ] `AppConfig` に `ocr_backend` フィールド追加
- [ ] `presenter.py` を `text=ocr_result, images=[crop_image]` の複合送信に更新
- [ ] `pyproject.toml` に `winsdk` または `winrt` を追加

### Phase 3 — RapidOCR 追加と切り替え対応

目標：Windows OCR と RapidOCR を設定で切り替えられるようにする。

- [ ] `ocr/rapidocr_backend.py`：RapidOCR 実装（日本語モデル）
- [ ] `factory.py` に RapidOCR 分岐を追加
- [ ] `result_window.py` にバックエンド表示を追加（どの OCR が使われたか）
- [ ] `pyproject.toml` に `rapidocr-onnxruntime` を optional dependency として追加
- [ ] 2 バックエンドの精度・速度を並べて比較できる簡易テスト追加

### Phase 4 — UX 改善

目標：日常使いに耐える完成度にする。

- [ ] 結果ウィンドウのマークダウン表示（既存の `markdown` 依存がすでにある）
- [ ] セッション再実行（同じキャプチャで翻訳・解説・カスタムプロンプトを切り替え）
- [ ] Gemini コンテキストキャッシュの活用（書籍ページを繰り返し読む場合）
- [ ] 設定 UI（OCR バックエンド選択、出力言語、モデル選択）
- [ ] 起動方法の整理（`gem-read_launch.ps1` に並ぶランチャースクリプト追加）

---

## 依存追加の一覧

| パッケージ | 用途 | フェーズ | 備考 |
|---|---|---|---|
| `mss` | 高速スクリーンショット | Phase 1 | `PIL.ImageGrab` でも代替可 |
| `keyboard` | グローバルホットキー | Phase 1 | `pynput` でも代替可 |
| `winsdk` or `winrt` | Windows OCR API バインディング | Phase 2 | Python 3.13 対応要確認 |
| `rapidocr-onnxruntime` | RapidOCR | Phase 3 | optional dependency |

---

## 技術リスクと対策

| リスク | 対策 |
|---|---|
| `winsdk` が Python 3.13 非対応 | `comtypes` 経由の WinRT 呼び出しで代替。または Phase 3 の RapidOCR を先行実装 |
| Kindle/Kobo の画面キャプチャがブロックされる（DRM の場合） | Phase 1 の PoC で早期確認。ブロックされる場合は DWM API 経由のキャプチャを検討 |
| RapidOCR の日本語精度が用途に不十分 | Windows OCR との並走テストで比較し、モデルを差し替えるか PaddleOCR に切り替え |
| フォントが小さい / ルビ混じりで OCR が崩れる | Pillow で前処理（二値化・アップスケール）を `screenshot.py` に挟む |

---

## 起動コマンド（予定）

```powershell
# 通常起動
uv run python -m desktop_capture

# 既存アプリと同時起動（PDF/EPUB リーダー + デスクトップキャプチャ）
.\gem-read_launch.ps1
```

---

## 関連ファイル

- [src/pdf_epub_reader/models/ai_model.py](src/pdf_epub_reader/models/ai_model.py) — 再利用する Gemini AI 層
- [src/pdf_epub_reader/utils/config.py](src/pdf_epub_reader/utils/config.py) — 設定管理（`AppConfig` に `ocr_backend` を追加）
- [src/pdf_epub_reader/dto/ai_dto.py](src/pdf_epub_reader/dto/ai_dto.py) — 再利用する DTO
- [browser-extension/src/content/selection/rectangleSelectionController.ts](browser-extension/src/content/selection/rectangleSelectionController.ts) — 矩形選択の設計参考
- [browser-extension/src/background/services/cropSelectionImage.ts](browser-extension/src/background/services/cropSelectionImage.ts) — crop ロジックの設計参考
- [docs/developer/architecture.md](docs/developer/architecture.md) — 既存アーキテクチャの背景
