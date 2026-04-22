# Desktop Capture 翻訳・解説アプリ 企画書

## 概要

PC 版 Kindle や楽天 Kobo Desktop など、DRM 管理下のデスクトップ電子書籍アプリの画面を範囲選択でキャプチャし、OCR でテキスト化した上で Gemini API に翻訳・解説させる companion アプリを追加開発する。

既存の `gem-read` リポジトリが持つ AI 連携層・キャッシュ管理・設定管理を最大限再利用し、フロントエンド（キャプチャ UI）と OCR 前処理のみを新規追加する。

---

## 解決したい問題

| 問題                                               | 現状のギャップ                                 |
| -------------------------------------------------- | ---------------------------------------------- |
| Kindle/Kobo は PDF/EPUB ファイルを直接開けない     | 既存の `pdf_epub_reader` は PyMuPDF 前提       |
| DRM 書籍のテキストはクリップボード経由で取りにくい | DOM アクセス・Accessibility API は信頼性が低い |
| 画面上の文章をそのまま翻訳・解説したい             | ブラウザ拡張は Web ページ専用                  |

---

## 方針

1. **OCR なしの PoC → OCR 併用の本番** の 2 段階で進める
2. 最初から **Windows OCR API と RapidOCR を切り替え可能** にしてバックエンド選択を早期に検証できるようにする
3. Gemini AI 層・キャッシュは **既存コードを直接再利用**、新規コードは最小限に抑える
4. 既存の `pdf_epub_reader` / `browser_api` には **変更を加えない**。新規パッケージを追加する
5. **設定は `DesktopCaptureConfig` を `desktop_capture` パッケージ内に独立定義する。**`AppConfig` には一切変更を加えない

---

## アーキテクチャ

```
src/
  desktop_capture/          ← 新規パッケージ
    __init__.py
    __main__.py             ← 起動エントリ
    app.py                  ← QApplication + qasync 起動
    config.py               ← DesktopCaptureConfig（独立した設定クラス）
    capture/
      gateway.py            ← CaptureGateway プロトコル（Phase 2 以降）
      overlay.py            ← 透過オーバーレイウィンドウ（矩形選択 UI）
      screenshot.py         ← mss で全画面キャプチャ → 矩形 crop + 前処理
      wgc_backend.py        ← pywinrt WGC 実装（Phase 1.5 以降）
    ocr/
      gateway.py            ← OcrGateway プロトコル（切り替え境界）
      windows_ocr.py        ← Windows OCR API 実装（pywinrt）
      rapidocr_backend.py   ← RapidOCR 実装
      factory.py            ← ocr_backend 設定値からゲートウェイ生成
    presenter.py            ← キャプチャ → OCR → AI 連携のオーケストレーション
    result_window.py        ← 翻訳・解説結果を表示する小ウィンドウ
```

### 既存資産の再利用マップ

| 既存コード                                          | desktop_capture での使い方                                               |
| --------------------------------------------------- | ------------------------------------------------------------------------ |
| `pdf_epub_reader.models.ai_model.AIModel`           | そのまま `import` して Gemini 解析に使用                                 |
| `pdf_epub_reader.dto.AnalysisRequest/Result`        | OCR テキスト + crop 画像を詰めて渡す                                     |
| `qasync` イベントループ統合                         | `pdf_epub_reader.infrastructure.event_loop` を参照して同じパターンで実装 |

> **注意:** `pdf_epub_reader.utils.config.AppConfig` には変更を加えない。設定は `desktop_capture/config.py` の `DesktopCaptureConfig` で完結させる。

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

- **`pywinrt`** パッケージ経由で `Windows.Media.Ocr.OcrEngine` を呼ぶ（`winsdk` は更新停滞のため不採用）
- 追加モデルファイル不要。OS に標準搭載
- 対応言語は OS にインストール済みの言語パックに依存

### RapidOCR 実装

- `rapidocr-onnxruntime` パッケージを使用
- 日本語対応モデル（`.onnx`）を初回ダウンロードまたは同梱
- モデルサイズは数十 MB 程度
- ONNX Runtime のみに依存し PyTorch 不要

### ファクトリ

```python
def create_ocr_gateway(config: DesktopCaptureConfig) -> OcrGateway:
    if config.ocr_backend == "rapidocr":
        return RapidOcrGateway()
    return WindowsOcrGateway()  # デフォルト
```

---

## DesktopCaptureConfig

`src/desktop_capture/config.py` に独立した設定クラスを定義する。`AppConfig` には一切変更を加えない。

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class DesktopCaptureConfig:
    # OCR バックエンド選択
    ocr_backend: Literal["windows", "rapidocr"] = "windows"
    # キャプチャバックエンド選択（Phase 1.5 以降）
    capture_backend: Literal["mss", "wgc"] = "mss"
    # Gemini モデル名
    gemini_model_name: str = ""
    # 出力言語
    output_language: str = "日本語"
    # システムプロンプト（OCR ノイズ補正の指示を含む）
    system_prompt: str = (
        "You are a translator and annotator. Translate the given text into {output_language}.\n"
        "The input text may be extracted by OCR and may contain duplicated characters from ruby "
        "(furigana) annotations. Infer the correct text from context before translating.\n"
        "Output the response in Markdown format."
    )
```

設定ファイルは `platformdirs.user_config_dir("gem-read-capture")` 以下の独立した JSON ファイルに永続化し、`pdf_epub_reader` の設定ファイルと衝突しない。

---

## 実装フェーズ

### Phase 1 — OCR なし PoC（最速検証）

目標：Kindle の画面上の選択領域を Gemini に画像として渡し、翻訳が返ってくることを確認する。

- [ ] `desktop_capture` パッケージ骨格を作成（`config.py` に `DesktopCaptureConfig` を定義）
- [ ] `capture/overlay.py`：PySide6 の透過フルスクリーンウィンドウで矩形ドラッグ選択
- [ ] `capture/screenshot.py`：`mss` で全画面キャプチャ → crop + リサイズ（前処理は Phase 2 で追加）
- [ ] `presenter.py`：crop 画像を `AnalysisRequest(text="", images=[...])` に詰めて `AIModel.analyze` を呼ぶ
- [ ] `result_window.py`：翻訳結果を表示する最小限のウィンドウ
- [ ] `__main__.py`：**`pynput`** でグローバルホットキー（例: `Ctrl+Shift+G`）で矩形選択を起動
- [ ] `pyproject.toml` に `mss`・`pynput` を追加
- [ ] **実機確認:** mss で Kindle 画面がキャプチャできるか検証。真っ黒の場合は Phase 1.5 に移行

> **注意:** `pynput` は `SetWindowsHookEx` ベースのため管理者権限は不要。ただし Kindle 自体が管理者権限で動いている場合はホットキーが届かないことがある。Phase 1 の実機確認時に合わせて検証する。

### Phase 1.5 — WGC フォールバック（DRM 対策）

目標：mss でキャプチャがブロックされた場合（真っ黒画像）に pywinrt / WGC へ切り替える。

- [ ] `capture/gateway.py`：`CaptureGateway` プロトコル定義
  ```python
  class CaptureGateway(Protocol):
      async def capture_screen(self) -> Image: ...
  ```
- [ ] `capture/screenshot.py` を `MssCaptureGateway` として `CaptureGateway` に準拠させリファクタ
- [ ] `capture/wgc_backend.py`：**`pywinrt`** の `Windows.Graphics.Capture` API 実装
- [ ] `presenter.py` に真っ黒画像チェックを追加。DRM 検知時はユーザーへ通知し WGC へ切り替えを促す
- [ ] `DesktopCaptureConfig` に `capture_backend: Literal["mss", "wgc"] = "mss"` を有効化
- [ ] Phase 1 の PoC 結果で mss が問題なければ本フェーズはスキップ可

### Phase 2 — OCR 前処理の追加

目標：テキストを OCR で抽出し、画像は補助入力として添付することで解析精度を上げる。

- [ ] `ocr/gateway.py`：`OcrGateway` プロトコル定義
- [ ] `ocr/windows_ocr.py`：**`pywinrt`** 経由の Windows OCR API 実装
- [ ] `ocr/factory.py`：ファクトリ実装（`DesktopCaptureConfig.ocr_backend` を参照）
- [ ] `capture/screenshot.py` に画像前処理を追加
  - 背景色に依存しない二値化・コントラスト調整（セピア・ナイトモード対応）
  - アスペクト比を維持したまま 2 倍アップスケール（小文字の OCR 精度向上）
- [ ] `presenter.py` を `text=ocr_result, images=[crop_image]` の複合送信に更新
- [ ] `pyproject.toml` に `pywinrt` を追加

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

| パッケージ             | 用途                                      | フェーズ   | 備考                                       |
| ---------------------- | ----------------------------------------- | ---------- | ------------------------------------------ |
| `mss`                  | 高速スクリーンショット（GDI 方式）        | Phase 1    |                                            |
| `pynput`               | グローバルホットキー                      | Phase 1    | 管理者権限不要。Kindle が管理者権限の場合は実機確認が必要 |
| `pywinrt`              | Windows OCR API + WGC キャプチャ両用      | Phase 1.5 / 2 | Python 3.13 対応済み・Microsoft 推奨    |
| `rapidocr-onnxruntime` | RapidOCR                                  | Phase 3    | optional dependency                        |

---

## 技術リスクと対策

| リスク                                                     | 対策                                                                                         |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| mss でキャプチャが真っ黒になる（DRM）                     | Phase 1.5 で `pywinrt` WGC API へ切り替え。閲覧ソフトのハードウェアアクセラレーション無効化も案内 |
| WGC 実装が Python から難航する                             | `pywinrt` は WGC の Python バインディング実績が少ない。Phase 1.5 はバックログ扱いで着手前に PoC を行う |
| `pynput` が Kindle（管理者権限）の裏でホットキーを拾えない | Phase 1 実機確認時に検証。必要なら `ctypes` + `RegisterHotKey` へ切り替え                   |
| RapidOCR の日本語精度が用途に不十分                        | Windows OCR との並走テストで比較し、モデルを差し替えるか PaddleOCR に切り替え               |
| ルビ混じりで OCR テキストが崩れる                          | `DesktopCaptureConfig.system_prompt` の OCR ノイズ補正指示で Gemini に文脈復元させる（前処理より確実）|

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
- [src/pdf_epub_reader/dto/ai_dto.py](src/pdf_epub_reader/dto/ai_dto.py) — 再利用する DTO
- [browser-extension/src/content/selection/rectangleSelectionController.ts](browser-extension/src/content/selection/rectangleSelectionController.ts) — 矩形選択の設計参考
- [browser-extension/src/background/services/cropSelectionImage.ts](browser-extension/src/background/services/cropSelectionImage.ts) — crop ロジックの設計参考
- [docs/developer/architecture.md](docs/developer/architecture.md) — 既存アーキテクチャの背景
