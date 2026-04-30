# Visual Studio WGC Helper 実装計画

## 目的

`desktop_capture` の Phase 1.5 で追加する `capture-helper.exe` を、Visual Studio を使って段階的に実装するための具体計画を整理する。

この helper の役割は次の 3 点に限定する。

- Windows Graphics Capture を使って対象モニターまたはウィンドウをキャプチャする
- Python 側から渡された矩形で crop する
- PNG バイト列を `stdout`、メタデータ JSON を `stderr` に返して終了する

既存の選択 UI、Gemini 連携、結果表示は Python 側が担当する。helper 側で UI やアプリ状態管理を持ち込まない。

---

## スコープ

### 含めるもの

- Visual Studio での Solution / Project 作成
- WGC を用いた単発スクリーンショット取得
- monitor 指定と crop 対応
- `stdout` / `stderr` ベースのプロセス間 I/O
- self-contained な `win-x64` 配布物の作成

### 含めないもの

- helper 側の GUI
- 領域選択 UI
- OCR
- Gemini API 呼び出し
- 常駐プロセス化
- 名前付きパイプ対応

---

## 既存計画との対応

この文書は [desktop-capture-plan.md](desktop-capture-plan.md) の Phase 1.5 を、Visual Studio 上の実行手順に落とし込んだ補助計画である。

最終的に Python 側で必要になる契約は次の通り。

- 成功時: `stdout` に PNG バイト列、`stderr` に JSON メタデータ
- 失敗時: `stdout` は空、`stderr` に JSON エラー情報、プロセスは非 0 終了
- Python 側は `subprocess` で helper を起動し、戻り値を `CaptureGateway` 実装へ詰め替える

---

## 推奨プロジェクト構成

```text
capture-helper/
  GemRead.CaptureHelper.sln
  src/
    GemRead.CaptureHelper/
      GemRead.CaptureHelper.csproj
      Program.cs
      Cli/
        CaptureOptions.cs
        ExitCodes.cs
        JsonStderrWriter.cs
      Capture/
        WgcCaptureService.cs
        CaptureResult.cs
        CaptureMetadata.cs
        MonitorResolver.cs
        Cropper.cs
      Imaging/
        PngEncoder.cs
      Interop/
        GraphicsCaptureItemInterop.cs
        NativeMethods.cs
  artifacts/
    publish/
```

`src` と `artifacts` を分けておくと、Visual Studio の publish 出力とソース管理を切り分けやすい。

---

## 推奨技術選定

### プロジェクト種別

- `Console App` を採用する
- 理由: 最終成果物が `subprocess` 前提であり、標準出力と終了コードを扱いやすい

### ターゲット

- `.NET 8`
- `TargetFramework`: `net8.0-windows10.0.19041.0` 以上
- `Platform`: `x64`

### 実装方針

- 最初は「PNG をファイル保存するだけ」の PoC を通す
- その後で CLI 引数と `stdout` / `stderr` 契約を追加する
- 最初から Python 連携まで一気に進めない

---

## Visual Studio 事前準備

### Visual Studio Installer

- `Desktop development with .NET` をインストールする
- Windows 10/11 SDK を入れる
- 必要なら最新の .NET 8 SDK を入れる

### 確認項目

- `Visual Studio 2022` が利用可能であること
- Windows 11 または WGC 対応の Windows 10 環境であること
- `x64` 実行が可能であること

---

## Solution 作成手順

### Step 1: Solution を作る

1. Visual Studio を開く
2. `Create a new project` を選ぶ
3. `Console App` を選ぶ
4. Project name を `GemRead.CaptureHelper` にする
5. Location を `gem-read\capture-helper\src` にする
6. Solution name を `GemRead.CaptureHelper` にする
7. Framework を `.NET 8` にする

### Step 2: プロジェクト設定を固定する

`Project > Properties` で次を確認する。

- `Target framework`: `.NET 8.0 (Windows)` 相当
- `Platform target`: `x64`
- `Nullable`: `enable`
- `Implicit usings`: `enable`

必要なら `.csproj` を直接次のように調整する。

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0-windows10.0.19041.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <Platforms>x64</Platforms>
  </PropertyGroup>
</Project>
```

### Step 3: ディレクトリを整理する

Solution Explorer で次のフォルダを作る。

- `Cli`
- `Capture`
- `Imaging`
- `Interop`

---

## 実装マイルストーン

## Milestone 0: 最小 PoC

目標: WGC で 1 枚キャプチャし、ローカル PNG として保存できることを確認する。

### 作業

- `Program.cs` に仮のエントリを書く
- `GraphicsCaptureSession.IsSupported()` を確認する
- 固定対象を 1 つキャプチャする PoC を作る
- 取得したフレームを PNG に変換してローカル保存する

### 完了条件

- Kindle や Kobo で `mss` が黒くなる条件でも、WGC 側で画像が取得できる
- 画像の保存に成功する

### この段階でやらないこと

- `stdout` 出力
- Python 連携
- crop 引数
- monitor 選択引数

PoC の目的は「WGC が成立するか」の確認だけに絞る。

---

## Milestone 1: monitor 指定対応

目標: 指定したモニター全体を helper 単体でキャプチャできるようにする。

### 作業

- `CaptureOptions` に `monitorIndex` を追加する
- `MonitorResolver` で有効なモニター一覧を解決する
- `--monitor-index` を受けて対象モニターを決定する
- 範囲外の index はエラー終了にする

### 完了条件

- `--monitor-index 1` などで対象モニターを切り替えられる
- 不正 index では JSON エラーを返して終了する

---

## Milestone 2: crop 対応

目標: Python 側で選択した物理ピクセル矩形を、そのまま helper に渡せるようにする。

### 作業

- `CaptureOptions` に `left`, `top`, `width`, `height` を追加する
- helper 側でモニター全体を取得し、指定矩形で crop する
- モニター境界をまたぐ場合の挙動を定義する

### 推奨ルール

- 矩形がモニター範囲外ならクリップせずエラーにする
- `width <= 0` または `height <= 0` はエラーにする
- DPI 変換は Python 側で済んでいる前提にし、helper 側では物理ピクセルとして扱う

### 完了条件

- 指定矩形だけを切り出した PNG を返せる
- 無効な矩形をきちんと拒否できる

---

## Milestone 3: CLI 契約の固定

目標: Python から安全に呼び出せる入出力仕様を固める。

### 推奨引数

```text
GemRead.CaptureHelper.exe \
  --monitor-index 1 \
  --left 120 \
  --top 240 \
  --width 900 \
  --height 500
```

### 推奨メタデータ JSON

```json
{
  "backend": "wgc",
  "imageWidth": 900,
  "imageHeight": 500,
  "monitorIndex": 1,
  "warning": null,
  "drmSuspected": false
}
```

### 推奨エラー JSON

```json
{
  "error": "invalid-args",
  "message": "width must be greater than zero"
}
```

### 終了コード案

- `0`: success
- `2`: unsupported-environment
- `3`: invalid-args
- `4`: capture-failed
- `5`: internal-error

### 実装ルール

- PNG バイト列は `Console.OpenStandardOutput()` へ書く
- JSON は `Console.Error.WriteLine(...)` に限定する
- ログ文字列を `stdout` に混ぜない

---

## Milestone 4: Python 連携前提の仕上げ

目標: helper が subprocess から安定して使える状態にする。

### 作業

- 例外をそのまま表示せず、JSON エラーへ正規化する
- 1 回の起動で 1 回だけキャプチャして終了する
- タイムアウトを意識して無限待機を避ける
- ファイル保存コードを削除する

### 完了条件

- Python から同期的に起動して結果を回収できる
- 失敗時もディスクにゴミファイルを残さない

---

## Visual Studio 上の具体作業メモ

### デバッグ設定

- `Debug > GemRead.CaptureHelper Properties > Debug` で command line arguments を設定する
- 例: `--monitor-index 1 --left 100 --top 100 --width 800 --height 600`

### Configuration Manager

- `Build > Configuration Manager` で `Active solution platform` を `x64` にする

### Publish

1. Solution Explorer でプロジェクトを右クリック
2. `Publish` を選ぶ
3. `Folder` を選ぶ
4. 出力先を `capture-helper\artifacts\publish\win-x64` にする
5. `Deployment mode` を `Self-contained` にする
6. `Target runtime` を `win-x64` にする

### Publish 後の確認

- `GemRead.CaptureHelper.exe` 単体で起動できる
- 開発機に .NET ランタイムがなくても実行できる

---

## 実装順序の推奨理由

最初に `stdout` / `stderr` 契約まで同時に作ると、問題の切り分けが難しくなる。次の順で進めると詰まりにくい。

1. WGC で取れるかだけ確認する
2. monitor 指定を足す
3. crop を足す
4. その後で CLI 契約を固める
5. 最後に Python から呼ぶ

この順序なら、失敗したときに `WGC 自体の問題` と `プロセス I/O の問題` を分離できる。

---

## Python 側との接続ポイント

helper 完成後、Python 側では次を進める。

- `src/desktop_capture/capture/wgc_backend.py` を追加する
- helper 実行パス、引数、タイムアウトを管理する
- `stdout` の PNG と `stderr` の JSON を読み分ける
- `CaptureGateway` 契約へ変換する

Python 側は既存の `MssCaptureGateway` と同じ責務に寄せる。helper 側の都合を presenter へ漏らさない。

---

## 想定リスク

### WinRT / WGC 周辺

- 開発機によって WGC の挙動差がある
- 対象アプリや GPU 構成で取得可否が変わる
- HDR やマルチモニター条件でフレームサイズの扱いがずれる可能性がある

### 実装境界

- helper 側で monitor 選択 UI を持つと Python 側と責務が衝突する
- helper 側で常駐や再利用を始めると Phase 1.5 の範囲を超えやすい
- `stdout` にログを書き出すと PNG が壊れる

---

## 受け入れチェックリスト

- [ ] Visual Studio 2022 で Solution を開いてビルドできる
- [ ] `x64` 構成で実行できる
- [ ] WGC で単発キャプチャが成功する
- [ ] `--monitor-index` が動作する
- [ ] crop 引数が動作する
- [ ] `stdout` に PNG、`stderr` に JSON を分離できる
- [ ] invalid args を JSON エラーで返せる
- [ ] self-contained publish した EXE が動作する
- [ ] Python 側の `subprocess` から起動できる

---

## 次の実装対象

この計画を開始するなら、最初の着手点は次の順がよい。

1. `capture-helper/` Solution 作成
2. `Milestone 0` の PNG 保存 PoC 作成
3. 実機で Kobo / Kindle 相当画面の取得可否確認
4. CLI 引数と `stdout` / `stderr` 契約の追加
5. Python 側の `wgc_backend.py` 統合