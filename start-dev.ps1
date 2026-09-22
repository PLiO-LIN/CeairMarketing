$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$api = Join-Path $root "services\platform-api"

if (-not (Get-NetTCPConnection -LocalPort 8800 -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8800" `
    -WorkingDirectory $api -WindowStyle Hidden
}

if (-not (Get-NetTCPConnection -LocalPort 8780 -ErrorAction SilentlyContinue)) {
  $node = (Get-Command "node.exe").Source
  Start-Process -FilePath $node `
    -ArgumentList "scripts/dev-web.mjs" `
    -WorkingDirectory $root -WindowStyle Hidden
}

Write-Output "Web: http://127.0.0.1:8780/"
Write-Output "API: http://127.0.0.1:8800/docs"
