[CmdletBinding()]
param(
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root ".runtime"
$PidFile = Join-Path $Runtime "server.pid"

$existing = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    throw "127.0.0.1:$Port is already occupied by PID $($existing[0].OwningProcess); no process was changed."
}

$python = (Get-Command python.exe -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
$server = Start-Process `
    -FilePath $python `
    -ArgumentList @("server.py", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

try {
    $deadline = (Get-Date).AddSeconds(5)
    do {
        Start-Sleep -Milliseconds 200
        $listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($listener -and $listener.OwningProcess -eq $server.Id) { break }
        if ($server.HasExited) { throw "ERRM server exited before binding 127.0.0.1:$Port." }
    } while ((Get-Date) -lt $deadline)

    if (-not $listener -or $listener.OwningProcess -ne $server.Id) {
        throw "ERRM server did not bind 127.0.0.1:$Port within 5 seconds."
    }
    Set-Content -LiteralPath $PidFile -Value $server.Id -Encoding ASCII
    Write-Output "ERRM server started in hidden mode: http://127.0.0.1:$Port (PID $($server.Id))."
    Write-Output "No browser was opened; no game process, game file, save, overlay, or input hook is accessed."
}
catch {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $PidFile) { Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue }
    throw
}
