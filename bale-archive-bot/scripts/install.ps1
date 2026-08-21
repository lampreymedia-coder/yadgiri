#Requires -Version 5.1
# Install Python venv, dependencies, create folders, run Alembic.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Get-Command python -ErrorAction SilentlyContinue
if (-not $Py) {
    Write-Error "Python 3.12+ is not on PATH. Install it from python.org and tick 'Add python.exe to PATH'."
}

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 3.12 or newer is required."
}

if (-not (Test-Path (Join-Path $Root ".venv"))) {
    python -m venv .venv
}

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install -e ".[dev]"

foreach ($Rel in @("data", "data\media", "data\backups", "data\spool")) {
    $Dir = Join-Path $Root $Rel
    if (-not (Test-Path $Dir)) {
        New-Item -ItemType Directory -Path $Dir | Out-Null
    }
}

$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Root ".env.example") $EnvFile
    Write-Host "Created .env from .env.example — edit BALE_BOT_TOKEN and DATABASE_URL."
}

Get-Content -Path $EnvFile -Encoding UTF8 | ForEach-Object {
    $Line = $_.Trim()
    if (-not $Line -or $Line.StartsWith("#") -or $Line.IndexOf("=") -lt 1) { return }
    $Idx = $Line.IndexOf("=")
    $Name = $Line.Substring(0, $Idx).Trim()
    $Value = $Line.Substring($Idx + 1).Trim()
    Set-Item -Path ("Env:" + $Name) -Value $Value
}

Write-Host "Applying database migrations..."
& $VenvPy -m alembic upgrade head
& $VenvPy scripts\seed_tags.py

Write-Host "Install finished. Next: edit .env then run scripts\run.ps1"
