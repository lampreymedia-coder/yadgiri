#Requires -Version 5.1
# Run the bot in the foreground (used by NSSM and for a first manual test).
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Error "venv is missing. Run scripts\install.ps1 first."
}

& $VenvPy -m app.main
