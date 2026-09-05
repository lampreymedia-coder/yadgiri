#Requires -Version 5.1
# Restore a .dump produced by backup.ps1.
# Usage:  .\scripts\restore.ps1 -DumpPath data\backups\backup-20260821-010000.dump
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpPath
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path $DumpPath)) {
    Write-Error "Dump file not found: $DumpPath"
}

function Read-DotEnv {
    param([string]$Path)
    $Map = @{}
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
$DatabaseUrl = $EnvMap["DATABASE_URL"]
if ($DatabaseUrl -like "mssql*") {
    Write-Error "SQL Server restore is done in SSMS: right-click the database → Tasks → Restore → Database, and pick the .bak file."
}
if ($DatabaseUrl -notmatch "postgresql(?:\+asyncpg)?://([^:]+):([^@]+)@([^:]+):(\d+)/([^?]+)") {
    Write-Error "Could not parse DATABASE_URL"
}
$PgUser = $Matches[1]
$PgPass = $Matches[2]
$PgHost = $Matches[3]
$PgPort = $Matches[4]
$PgDb = $Matches[5]

$Confirm = Read-Host "This overwrites database $PgDb. Type RESTORE to continue"
if ($Confirm -ne "RESTORE") {
    Write-Host "Aborted"
    exit 1
}

$PgRestore = Get-Command pg_restore.exe -ErrorAction SilentlyContinue
if (-not $PgRestore) {
    $Guess = "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe"
    if (Test-Path $Guess) { $PgRestore = Get-Item $Guess } else { Write-Error "pg_restore.exe not found" }
}

$PgRestoreExe = if ($PgRestore.Source) { $PgRestore.Source } else { $PgRestore.FullName }
$env:PGPASSWORD = $PgPass
try {
    & $PgRestoreExe --clean --if-exists --no-owner -h $PgHost -p $PgPort -U $PgUser -d $PgDb $DumpPath
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host "Restore finished"
