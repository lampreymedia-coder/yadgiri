#Requires -Version 5.1
# Register the bot as a Windows service via NSSM.
# Download NSSM from https://nssm.cc/download and unzip so nssm.exe is on PATH
# or pass -NssmPath.
param(
    [string]$ServiceName = "BaleArchiveBot",
    [string]$NssmPath = "nssm.exe"
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
$RunPs1 = Join-Path $Root "scripts\run.ps1"
$Pwsh = (Get-Command powershell.exe).Source

if (-not (Test-Path $RunPs1)) {
    Write-Error "run.ps1 not found"
}

& $NssmPath install $ServiceName $Pwsh "-NoProfile -ExecutionPolicy Bypass -File `"$RunPs1`""
& $NssmPath set $ServiceName AppDirectory $Root
& $NssmPath set $ServiceName AppEnvironmentExtra "PYTHONUTF8=1"
& $NssmPath set $ServiceName AppStdout (Join-Path $Root "data\bot-stdout.log")
& $NssmPath set $ServiceName AppStderr (Join-Path $Root "data\bot-stderr.log")
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateBytes 2000000
& $NssmPath set $ServiceName Start SERVICE_AUTO_START
& $NssmPath start $ServiceName

Write-Host "Service $ServiceName installed and started."
Write-Host "Logs: data\bot-stdout.log  and  data\bot-stderr.log"
