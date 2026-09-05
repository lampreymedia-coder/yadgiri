#Requires -Version 5.1
# Nightly pg_dump to BACKUP_DIR. Keeps 30 days. Schedule with Task Scheduler.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Read-DotEnv {
    param([string]$Path)
    $Map = @{}
    if (-not (Test-Path $Path)) { return $Map }
    Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
        $Line = $_.Trim()
        if (-not $Line -or $Line.StartsWith("#")) { return }
        $Idx = $Line.IndexOf("=")
        if ($Idx -lt 1) { return }
        $Map[$Line.Substring(0, $Idx).Trim()] = $Line.Substring($Idx + 1).Trim()
    }
    return $Map
}

$EnvMap = Read-DotEnv (Join-Path $Root ".env")
$BackupDirRel = if ($EnvMap["BACKUP_DIR"]) { $EnvMap["BACKUP_DIR"] } else { "data\backups" }
$BackupDir = if ([System.IO.Path]::IsPathRooted($BackupDirRel)) { $BackupDirRel } else { Join-Path $Root $BackupDirRel }
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

$DatabaseUrl = $EnvMap["DATABASE_URL"]
if (-not $DatabaseUrl) {
    Write-Error "DATABASE_URL is missing from .env"
}

if ($DatabaseUrl -like "mssql*") {
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutFile = Join-Path $BackupDir ("backup-{0}.bak" -f $Stamp)
    if ($DatabaseUrl -notmatch "mssql(?:\+aioodbc)?://(?:([^:]+):([^@]+)@)?([^:/?,]+)(?::(\d+))?/([^?]+)") {
        Write-Error "Could not parse SQL Server DATABASE_URL. Back up bale_archive from SSMS instead."
    }
    $MsUser = $Matches[1]
    $MsPass = $Matches[2]
    $MsHost = $Matches[3]
    $MsPort = $Matches[4]
    $MsDb = $Matches[5]
    $Server = if ($MsPort) { "{0},{1}" -f $MsHost, $MsPort } else { $MsHost }
    $SqlCmd = Get-Command sqlcmd.exe -ErrorAction SilentlyContinue
    if (-not $SqlCmd) {
        Write-Error "sqlcmd.exe not found. In SSMS: right-click $MsDb → Tasks → Back Up."
    }
    $SqlCmdExe = if ($SqlCmd.Source) { $SqlCmd.Source } else { $SqlCmd.FullName }
    $Query = "BACKUP DATABASE [$MsDb] TO DISK = N'$OutFile' WITH INIT"
    if ($MsUser) {
        & $SqlCmdExe -S $Server -U $MsUser -P $MsPass -Q $Query
    } else {
        & $SqlCmdExe -S $Server -E -Q $Query
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "sqlcmd backup failed with exit $LASTEXITCODE"
    }
    Write-Host "Backup written to $OutFile"
    exit 0
}

# postgresql+asyncpg://user:pass@localhost:5432/db  ->  user, pass, host, port, db
if ($DatabaseUrl -notmatch "postgresql(?:\+asyncpg)?://([^:]+):([^@]+)@([^:]+):(\d+)/([^?]+)") {
    Write-Error "Could not parse DATABASE_URL. For SQL Server use an mssql+aioodbc URL or back up from SSMS."
}
$PgUser = $Matches[1]
$PgPass = $Matches[2]
$PgHost = $Matches[3]
$PgPort = $Matches[4]
$PgDb = $Matches[5]

$PgDump = Get-Command pg_dump.exe -ErrorAction SilentlyContinue
if (-not $PgDump) {
    $Guess = "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
    if (Test-Path $Guess) {
        $PgDump = Get-Item $Guess
    } else {
        Write-Error "pg_dump.exe not found. Add PostgreSQL bin to PATH."
    }
}

$PgDumpExe = if ($PgDump.Source) { $PgDump.Source } else { $PgDump.FullName }
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$OutFile = Join-Path $BackupDir ("backup-{0}.dump" -f $Stamp)
$env:PGPASSWORD = $PgPass
try {
    & $PgDumpExe --format=custom --no-owner --file=$OutFile -h $PgHost -p $PgPort -U $PgUser $PgDb
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pg_dump failed with exit $LASTEXITCODE"
    }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

$Cutoff = (Get-Date).AddDays(-30)
Get-ChildItem -Path $BackupDir -Filter "backup-*.dump" | Where-Object { $_.LastWriteTime -lt $Cutoff } | ForEach-Object {
    Write-Host "Deleting old backup $($_.FullName)"
    Remove-Item -LiteralPath $_.FullName -Force
}

Write-Host "Backup written to $OutFile"
