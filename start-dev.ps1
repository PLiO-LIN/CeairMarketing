$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$api = Join-Path $root "services\platform-api"
$web = Join-Path $root "apps\web-v32"

if (-not (Get-NetTCPConnection -LocalPort 8800 -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8800" `
    -WorkingDirectory $api -WindowStyle Hidden
}

if (-not (Get-NetTCPConnection -LocalPort 8780 -ErrorAction SilentlyContinue)) {
  $pnpm = (Get-Command "pnpm.cmd").Source
  Start-Process -FilePath $pnpm `
    -ArgumentList "dev", "--host", "127.0.0.1", "--port", "8780" `
    -WorkingDirectory $web -WindowStyle Hidden
}

Write-Output "Web: http://127.0.0.1:8780/"
Write-Output "API: http://127.0.0.1:8800/docs"
