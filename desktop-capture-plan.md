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
3. Gemini AI 層・キャッシュは **adapter 経由で既存コードを再利用**し、新規コードは最小限に抑える
4. 既存の `pdf_epub_reader` / `browser_api` には **変更を加えない**。新規パッケージを追加する
5. **設定は `DesktopCaptureConfig` を `desktop_capture` パッケージ内に独立定義する。**`AppConfig` には一切変更を加えない
6. グローバルホットキーは **`ctypes.windll.user32.RegisterHotKey` を第一候補**とし、使用できない環境向けに **ボタン起動 + タイマー付き遅延キャプチャ**を用意する
7. WGC フォールバックは Python から `IDirect3D11Texture2D` を直接扱わず、**外部 helper.exe を subprocess で呼び出す境界**を設ける
8. 当面は **横書き前提**で実装し、縦書きは将来対応とする。ルビ誤読は OCR 後処理と Gemini への補助指示の両方で抑制する

---

## アーキテクチャ

```text
src/
  desktop_capture/          ← 新規パッケージ
    __init__.py
    __main__.py             ← 起動エントリ
    app.py                  ← QApplication + qasync 起動
    config.py               ← DesktopCaptureConfig（独立した設定クラス）
    adapters/
      ai_gateway.py         ← DesktopCaptureConfig と AIModel の橋渡し adapter
    capture/
      hotkey.py             ← RegisterHotKey ラッパー
      trigger_panel.py      ← 即時/遅延キャプチャ起動 UI
      gateway.py            ← CaptureGateway プロトコル（Phase 2 以降）
      overlay.py            ← 透過オーバーレイウィンドウ（矩形選択 UI）
      screenshot.py         ← mss で全画面キャプチャ → 矩形 crop + 前処理
      wgc_backend.py        ← 外部 WGC helper.exe を呼ぶクライアント（Phase 1.5 以降）
    ocr/
      gateway.py            ← OcrGateway プロトコル（切り替え境界）
      windows_ocr.py        ← Windows OCR API 実装（pywinrt）
      rapidocr_backend.py   ← RapidOCR 実装
      factory.py            ← ocr_backend 設定値からゲートウェイ生成
    presenter.py            ← キャプチャ → OCR → AI 連携のオーケストレーション
    result_window.py        ← 翻訳・解説結果を表示する小ウィンドウ
```

### 既存資産の再利用マップ

| 既存コード                                   | desktop_capture での使い方                                               |
| -------------------------------------------- | ------------------------------------------------------------------------ |
| `pdf_epub_reader.models.ai_model.AIModel`    | `desktop_capture.adapters.ai_gateway` から再利用し、設定差分を吸収する   |
| `pdf_epub_reader.dto.AnalysisRequest/Result` | OCR テキスト + crop 画像を詰めて渡す                                     |
| `qasync` イベントループ統合                  | `pdf_epub_reader.infrastructure.event_loop` を参照して同じパターンで実装 |

> **注意:** `pdf_epub_reader.utils.config.AppConfig` には変更を加えない。設定は `desktop_capture/config.py` の `DesktopCaptureConfig` で完結させる。
> **注意:** `AIModel` は `AppConfig` 前提のため、desktop_capture 側では adapter を 1 枚挟み、`DesktopCaptureConfig` から Gemini 実行に必要な最小設定だけを橋渡しする。

### 起動トリガー方針

- グローバルホットキーは `RegisterHotKey` を優先し、キーボード hook ベースのライブラリは Phase 1 では使わない
- ホットキー登録に失敗した場合や競合がある場合でも使えるように、小さな起動パネルに `Capture now` / `Capture in 3s` / `Capture in 5s` を用意する
- 遅延キャプチャは Kindle など前面アプリへフォーカスを戻してから撮影できるため、ホットキー非対応環境の主要フォールバックとする

ブラウザ拡張の矩形選択ロジック（[browser-extension/src/content/selection/rectangleSelectionController.ts](browser-extension/src/content/selection/rectangleSelectionController.ts)）と crop 処理（[browser-extension/src/background/services/cropSelectionImage.ts](browser-extension/src/background/services/cropSelectionImage.ts)）は、Python 版実装の設計見本として参照する。

---

## OCR バックエンド設計

### プロトコル（切り替え境界）

```python
from dataclasses import dataclass, field
from typing import Literal, Protocol

@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: tuple[int, int, int, int]
    confidence: float | None = None
    role: Literal["body", "ruby", "unknown"] = "unknown"

@dataclass(frozen=True)
class OcrResult:
    text: str
    lines: list[OcrLine] = field(default_factory=list)
    writing_mode: Literal["horizontal", "vertical", "unknown"] = "unknown"

class OcrGateway(Protocol):
    async def extract(self, image_bytes: bytes) -> OcrResult: ...
```

- Phase 2 時点では `writing_mode="horizontal"` を主対象とし、縦書きらしいレイアウトは未対応として検知・通知できる形を残す
- `lines` と `bbox` を保持しておくことで、小さい文字をルビ候補として除外する後処理を Presenter 側に置ける

### Windows OCR API 実装

- **`pywinrt`** パッケージ経由で `Windows.Media.Ocr.OcrEngine` を呼ぶ（`winsdk` は更新停滞のため不採用）
- 追加モデルファイル不要。OS に標準搭載
- 対応言語は OS にインストール済みの言語パックに依存
- 行ごとの bounding box と信頼度を回収し、横書き本文とルビ候補を判別できる材料を `OcrResult` に残す
- **非同期ブリッジング注意：** `pywinrt` が返す `IAsyncOperation` は Python 標準の `asyncio.Future` とは別物。バージョンによっては `await engine.recognize_async(bitmap)` がそのまま動けるが、`qasync` イベントループ上でブロックまたは例外になる場合がある。その際は `asyncio.to_thread()` で同期ラッパーに切り替える。

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

### AI adapter 方針

desktop_capture からは `AIModel` を直接 new せず、`DesktopCaptureAiGateway` のような adapter を介して利用する。

- `DesktopCaptureConfig` から Gemini 実行に必要な項目だけを抽出する
- `AnalysisRequest` への詰め替えと system prompt の注入を adapter 側に寄せる
- 将来 browser_api と同様の設定分離を進める際も desktop_capture 側の Presenter を変更しなくて済む

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
    # グローバルホットキーが使えない場合の遅延キャプチャ秒数
    delayed_capture_seconds: int = 3
    # Gemini モデル名
    gemini_model_name: str = ""
    # 出力言語
    output_language: str = "日本語"
    # システムプロンプト（OCR ノイズ補正の指示を含む）
    system_prompt: str = (
        "You are a translator and annotator. Translate the given text into {output_language}.\n"
      "Assume the source is primarily horizontal Japanese text for now.\n"
        "The input text may be extracted by OCR and may contain duplicated characters from ruby "
      "(furigana) annotations. Prefer the main body text over ruby and infer the correct text from context before translating.\n"
        "Output the response in Markdown format."
    )
```

設定ファイルは `platformdirs.user_config_dir("gem-read-capture")` 以下の独立した JSON ファイルに永続化し、`pdf_epub_reader` の設定ファイルと衝突しない。

---

## 実装フェーズ

### Phase 1 — OCR なし PoC（最速検証）

目標：Kindle の画面上の選択領域を Gemini に画像として渡し、翻訳が返ってくることを確認する。

- [x] `desktop_capture` パッケージ骨格を作成（`config.py` に `DesktopCaptureConfig` を定義）
- [x] `app.py`：起動直後に `ctypes.windll.shcore.SetProcessDpiAwareness(2)` を呼び **Per-Monitor DPI Aware V2** を強制する。これを省くと PySide6 が返す論理ピクセル座標と mss が撮影する物理ピクセル画像のスケールが乖離し、crop 位置がずれるバグが発生する
- [x] `capture/overlay.py`：PySide6 の透過フルスクリーンウィンドウで矩形ドラッグ選択。マルチモニター環境ではスクリーンごとに `QScreen.devicePixelRatio()` を取得し、論理座標を物理座標へ変換してから `CaptureRequest.crop_rect` に渡す
- [x] `capture/screenshot.py`：`mss` で全画面キャプチャ → crop + リサイズ（前処理は Phase 2 で追加）
- [x] `adapters/ai_gateway.py`：`DesktopCaptureConfig` を `AIModel` 向け入力へ橋渡しする adapter を追加
- [x] `presenter.py`：crop 画像を `AnalysisRequest(text="", images=[...])` に詰めて adapter 経由で `AIModel.analyze` を呼ぶ
- [x] `result_window.py`：翻訳結果を表示する最小限のウィンドウ
- [x] `capture/hotkey.py`：`ctypes.windll.user32.RegisterHotKey` でグローバルホットキー（例: `Ctrl+Shift+G`）を登録
- [x] `capture/trigger_panel.py`：`Capture now` / `Capture in 3s` / `Capture in 5s` の代替起動 UI を追加
- [x] `pyproject.toml` に `mss` を追加（ホットキーは標準ライブラリで実装）
- [x] **実機確認:** `RegisterHotKey` が登録できるか、競合時に遅延キャプチャへフォールバックできるか、mss で Kindle 画面がキャプチャできるか検証する

> **注意:** `RegisterHotKey` はキーボード hook より検知リスクが低いが、予約済みキーや他アプリとの競合で登録に失敗することがある。その場合は trigger panel からの即時/遅延キャプチャを使う。
> **実機確認結果(2026-04-27)** Kindle for PC で mss を用いたキャプチャおよび翻訳結果取得は成功。楽天koboはDRM の影響で真っ黒画像になるため、Phase 1.5 で WGC フォールバックを実装する必要がある。モニターが複数ある場合に、対象となるモニターを選択できるようにしたい。

### Phase 1.5 — WGC フォールバック（DRM 対策）

目標：mss でキャプチャがブロックされた場合（真っ黒画像）に WGC helper.exe 経由のキャプチャへ切り替える。

- [ ] `capture/gateway.py`：CaptureGateway の要求・応答 DTO とプロトコルを定義

  ```python
  from dataclasses import dataclass
  from typing import Literal, Protocol

  @dataclass(frozen=True)
  class CaptureRect:
      left: int
      top: int
      width: int
      height: int

  @dataclass(frozen=True)
  class CaptureRequest:
      monitor_index: int | None = None
      crop_rect: CaptureRect | None = None

  @dataclass(frozen=True)
  class CaptureResult:
      image_bytes: bytes  # メモリ上で受け渡し（一時ファイル不使用）
      image_width: int
      image_height: int
      backend: Literal["mss", "wgc"]
      drm_suspected: bool = False
      warning: str | None = None

  class CaptureGateway(Protocol):
      async def capture(self, request: CaptureRequest) -> CaptureResult: ...
  ```

- [ ] `capture/screenshot.py` を `MssCaptureGateway` として `CaptureGateway` に準拠させリファクタ
- [ ] `capture/wgc_backend.py`：外部 `capture-helper.exe` を `subprocess` で呼び出す WGC クライアント実装
- [ ] `capture-helper/`：C# などで WGC を扱う helper プロジェクトを追加し、PNG バイト列を **標準出力（stdout）** に書き込み、JSON メタデータを **標準エラー出力（stderr）** に返す（`Console.OpenStandardOutput()` に PNG を流し込み、`Console.Error` にメタデータを出力）
- [ ] `presenter.py` に真っ黒画像チェックを追加。DRM 検知時はユーザーへ通知し WGC helper への切り替えを促す
- [ ] `DesktopCaptureConfig` に `capture_backend: Literal["mss", "wgc"] = "mss"` を有効化
- [ ] helper との I/O は **標準出力（stdout）バイナリ + 標準エラー出力（stderr）JSON** を本番採用とする。一時 PNG + JSON はゴミファイルリスク・ディスク I/O オーバーヘッド・クリーンアップロジックの追加実装が必要になるため採用しない。名前付きパイプ（Named Pipes）は同一 helper プロセスを複数回使い回す必要が生じた場合の追加選択肢として保留する
- [ ] Phase 1 の PoC 結果で mss が問題なければ本フェーズはスキップ可

### Phase 2 — OCR 前処理の追加

目標：テキストを OCR で抽出し、画像は補助入力として添付することで解析精度を上げる。

- [ ] `ocr/gateway.py`：`OcrGateway` プロトコル定義
- [ ] `ocr/windows_ocr.py`：**`pywinrt`** 経由の Windows OCR API 実装。`qasync` イベントループ上で `await recognize_async()` が正常動作するか検証し、問題が出る場合は `asyncio.to_thread()` で同期ラッパーに切り替える
- [ ] `ocr/factory.py`：ファクトリ実装（`DesktopCaptureConfig.ocr_backend` を参照）
- [ ] `capture/screenshot.py` に画像前処理を追加
  - 背景色に依存しない二値化・コントラスト調整（セピア・ナイトモード対応）
  - アスペクト比を維持したまま 2 倍アップスケール（小文字の OCR 精度向上）
- [ ] `presenter.py` に横書き前提の OCR 後処理を追加
  - 小さく上側にある文字をルビ候補として除外
  - 縦書きらしいレイアウトを検知した場合は未対応として通知
- [ ] `presenter.py` を `text=ocr_result.text, images=[crop_image]` の複合送信に更新
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

- [ ] 翻訳・翻訳+解説・カスタムプロンプトの切り替え UI（例: 結果ウィンドウのタブ切り替え）
- [ ] 結果ウィンドウのマークダウン表示（既存の `markdown` 依存がすでにある）
- [ ] セッション再実行（同じキャプチャで翻訳・解説・カスタムプロンプトを切り替え）
- [ ] 複数枚バッチ対応
  - 複数回キャプチャした画像を順序付きセッションとして保持する
  - 画像ごとに削除・並べ替え・再キャプチャを行えるようにする
  - OCR と AI には順序を保ったまま複数画像を送信できるようにする
- [ ] Gemini コンテキストキャッシュの活用（書籍ページを繰り返し読む場合）
- [ ] 設定 UI（OCR バックエンド選択、出力言語、モデル選択）
- [ ] 起動方法の整理（`gem-read_launch.ps1` に並ぶランチャースクリプト追加）

---

## 依存追加の一覧

| パッケージ             | 用途                               | フェーズ | 備考                                 |
| ---------------------- | ---------------------------------- | -------- | ------------------------------------ |
| `mss`                  | 高速スクリーンショット（GDI 方式） | Phase 1  |                                      |
| `pywinrt`              | Windows OCR API                    | Phase 2  | Python 3.13 対応済み・Microsoft 推奨 |
| `rapidocr-onnxruntime` | RapidOCR                           | Phase 3  | optional dependency                  |

補足:

- ホットキーは `ctypes.windll.user32.RegisterHotKey` を使うため追加依存は不要
- WGC helper は Python パッケージ依存ではなく、別途ビルドする self-contained executable を想定する

---

## 技術リスクと対策

| リスク                                          | 対策                                                                                                      |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| mss でキャプチャが真っ黒になる（DRM）           | Phase 1.5 で WGC helper.exe 経由へ切り替え。閲覧ソフトのハードウェアアクセラレーション無効化も案内        |
| WGC 実装が Python から難航する                  | Python では直接触らず helper.exe に分離する。helper は PoC を先に作り、成功したら subprocess 統合する     |
| `RegisterHotKey` が予約済みキーや競合で使えない | 起動パネルの即時/遅延キャプチャを常設し、ホットキーは補助トリガーとして扱う                               |
| helper.exe の配布・更新が煩雑になる             | self-contained publish を前提にし、バージョンと配置場所を `desktop_capture` 側で明示管理する              |
| RapidOCR の日本語精度が用途に不十分             | Windows OCR との並走テストで比較し、モデルを差し替えるか PaddleOCR に切り替え                             |
| ルビ混じりで OCR テキストが崩れる               | bounding box ベースでルビ候補を落とし、残差は `DesktopCaptureConfig.system_prompt` で Gemini に補正させる |
| 縦書き文書で OCR 品質が大きく落ちる             | Phase 2 では横書き前提に限定し、縦書き検知時は未対応メッセージを出して誤解析を避ける                      |
| DPI スケーリングによる crop 座標ずれ            | 起動エントリ（`app.py`）で `SetProcessDpiAwareness(2)` を呼び Per-Monitor DPI Aware V2 を強制。マルチモニター環境では `QScreen.devicePixelRatio()` で論理→物理座標変換を行い `CaptureRequest.crop_rect` に渡す |
| `pywinrt` の非同期処理が `qasync` で動かない    | `IAsyncOperation` は `asyncio.Future` とは別物。`await recognize_async()` で例外・ブロックが出る場合は `asyncio.to_thread()` で同期ラッパーに切り替える                                                     |
| WGC helper との I/O でゴミファイルが残る        | 一時ファイルを使わず stdout バイナリ + stderr JSON を本番採用。Python 側がクラッシュしてもディスクに残骸が生じない                                                                                            |

---

## 起動コマンド（予定）

```powershell
# 通常起動
uv run python -m desktop_capture

# 既存アプリと同時起動（PDF/EPUB リーダー + デスクトップキャプチャ）
.\gem-read_launch.ps1
````

---

## 関連ファイル

- [src/pdf_epub_reader/models/ai_model.py](src/pdf_epub_reader/models/ai_model.py) — 再利用する Gemini AI 層
- [src/pdf_epub_reader/dto/ai_dto.py](src/pdf_epub_reader/dto/ai_dto.py) — 再利用する DTO
- [browser-extension/src/content/selection/rectangleSelectionController.ts](browser-extension/src/content/selection/rectangleSelectionController.ts) — 矩形選択の設計参考
- [browser-extension/src/background/services/cropSelectionImage.ts](browser-extension/src/background/services/cropSelectionImage.ts) — crop ロジックの設計参考
- [docs/developer/architecture.md](docs/developer/architecture.md) — 既存アーキテクチャの背景
