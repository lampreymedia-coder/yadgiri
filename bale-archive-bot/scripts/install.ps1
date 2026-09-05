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

function Install-WithIranMirrors {
    param([string[]]$PipArgs)
    # pypi.org is often filtered in Iran; try Iranian mirrors next.
    $Indexes = @(
        @{ Url = "https://pypi.org/simple"; Host = "pypi.org" },
        @{ Url = "https://mirror-pypi.runflare.com/simple"; Host = "mirror-pypi.runflare.com" },
        @{ Url = "https://pypi.iranrepo.ir/simple"; Host = "pypi.iranrepo.ir" },
        @{ Url = "https://mirror.arvancloud.ir/pypi/simple"; Host = "mirror.arvancloud.ir" }
    )
    $last = 1
    foreach ($Index in $Indexes) {
        Write-Host "Installing packages from $($Index.Url)"
        & $VenvPy -m pip @PipArgs -i $Index.Url --trusted-host $Index.Host
        $last = $LASTEXITCODE
        if ($last -eq 0) { return }
    }
    Write-Error "pip install failed. pypi.org may be filtered; Iranian mirrors also failed."
}

Install-WithIranMirrors @("install", "--upgrade", "pip")
Install-WithIranMirrors @("install", "-e", ".[dev,mssql]")

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

$DatabaseUrl = $env:DATABASE_URL
if ($DatabaseUrl -like "mssql*") {
    $odbc = Get-OdbcDriver -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "ODBC Driver (17|18) for SQL Server"
    }
    if (-not $odbc) {
        Write-Warning "Microsoft ODBC Driver 17 or 18 for SQL Server was not found. Install it, then re-run install.ps1."
    }
}

Write-Host "Applying database migrations..."
& $VenvPy -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Error "Alembic failed. For SQL Server check ODBC Driver 18, DATABASE_URL, and that database bale_archive exists."
}
& $VenvPy scripts\seed_tags.py

Write-Host "Install finished. Next: edit .env then run scripts\run.ps1"
