#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
& $VenvPy -m black app tests scripts
& $VenvPy -m ruff check app tests scripts
& $VenvPy -m mypy app scripts
& $VenvPy -m pytest -q
