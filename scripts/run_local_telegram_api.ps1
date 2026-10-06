 param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.env'
$serverExe = 'F:\TelegramBotApiBuild\install\bin\telegram-bot-api.exe'

if (-not (Test-Path -LiteralPath $envFile)) { throw 'Project .env file was not found.' }
if (-not (Test-Path -LiteralPath $serverExe)) { throw 'Telegram Bot API server is not built or installed.' }

foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^\s*(TELEGRAM_API_ID|TELEGRAM_API_HASH)\s*=\s*(.*?)\s*$') {
        $name = $Matches[1]
        $value = $Matches[2].Trim('"', "'")
        if ($value) { [Environment]::SetEnvironmentVariable($name, $value, 'Process') }
    }
}

if (-not $env:TELEGRAM_API_ID -or -not $env:TELEGRAM_API_HASH) {
    throw 'Add TELEGRAM_API_ID and TELEGRAM_API_HASH to the local .env file. Do not share these values.'
}

$dataDir = Join-Path $env:LOCALAPPDATA 'InstagramBot\telegram-bot-api'
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
& $serverExe '--local' '--http-port=8082' '--http-stat-port=8083' '--http-ip-address=127.0.0.1' '--http-stat-ip-address=127.0.0.1' "--dir=$dataDir"
exit $LASTEXITCODE
