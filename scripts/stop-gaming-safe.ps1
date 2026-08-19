[CmdletBinding()]
param(
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path (Join-Path $Root ".runtime") "server.pid"

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Output "No ERRM managed server PID file was found; no process was changed."
    exit 0
}

$managedPid = [int](Get-Content -LiteralPath $PidFile -Raw).Trim()
$listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listener -or $listener.OwningProcess -ne $managedPid) {
    Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
    throw "PID file does not own 127.0.0.1:$Port; no process was stopped."
}

Stop-Process -Id $managedPid
Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
Write-Output "ERRM server stopped: PID $managedPid; no other process was changed."
