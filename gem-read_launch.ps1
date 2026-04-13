[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $scriptDir
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv is not installed or not available on PATH. Install uv and run 'uv sync --dev' before launching Gem Read."
    }

    & uv run python -m pdf_epub_reader @AppArgs

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
