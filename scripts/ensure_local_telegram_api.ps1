$ErrorActionPreference = 'Stop'

function Test-LocalApiPorts {
    $api = Test-NetConnection -ComputerName 127.0.0.1 -Port 8082 -InformationLevel Quiet -WarningAction SilentlyContinue
    $stats = Test-NetConnection -ComputerName 127.0.0.1 -Port 8083 -InformationLevel Quiet -WarningAction SilentlyContinue
    return ($api -and $stats)
}

if (Test-LocalApiPorts) { exit 0 }

$serverScript = Join-Path $PSScriptRoot 'run_local_telegram_api.ps1'
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$serverScript`""
Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WindowStyle Hidden | Out-Null

for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    if (Test-LocalApiPorts) { exit 0 }
}

throw 'Local Telegram Bot API did not start. Check the local .env settings and server files.'
