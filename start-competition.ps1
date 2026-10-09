param(
    [string]$DatabasePath = (Join-Path $PSScriptRoot "services\platform-api\ceair-competition.db")
)

$ErrorActionPreference = "Stop"
$competitionRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$competitionApi = Join-Path $competitionRoot "services\platform-api"

if (-not (Get-NetTCPConnection -LocalPort 8801 -State Listen -ErrorAction SilentlyContinue)) {
    $competitionDatabase = [System.IO.Path]::GetFullPath($DatabasePath)
    New-Item -ItemType Directory -Path (Split-Path -Parent $competitionDatabase) -Force | Out-Null
    $competitionEnvironment = @{
        SEED_DEMO_BUSINESS_DATA = "true"
        DATABASE_URL = "sqlite:///" + $competitionDatabase.Replace("\", "/")
        ENVIRONMENT = "development"
        INITIAL_ADMIN_USERNAME = "competition"
        INITIAL_ADMIN_PASSWORD = "Competition@2026"
    }
    $previousCompetitionEnvironment = @{}
    try {
        foreach ($competitionKey in $competitionEnvironment.Keys) {
            $previousCompetitionEnvironment[$competitionKey] = [Environment]::GetEnvironmentVariable($competitionKey, "Process")
            [Environment]::SetEnvironmentVariable($competitionKey, $competitionEnvironment[$competitionKey], "Process")
        }
        Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8801" -WorkingDirectory $competitionApi -WindowStyle Hidden -RedirectStandardOutput (Join-Path $competitionApi "competition-api.log") -RedirectStandardError (Join-Path $competitionApi "competition-api-error.log")
    } finally {
        foreach ($competitionKey in $previousCompetitionEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($competitionKey, $previousCompetitionEnvironment[$competitionKey], "Process")
        }
    }
}

$competitionReady = $false
$competitionDeadline = (Get-Date).AddSeconds(45)
do {
    try {
        $competitionHealth = Invoke-RestMethod "http://127.0.0.1:8801/health/ready" -TimeoutSec 2
        if ($competitionHealth.status -eq "ready") { $competitionReady = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $competitionDeadline)
if (-not $competitionReady) {
    throw "Competition API did not become ready. Check services/platform-api/competition-api-error.log."
}
if (-not (Get-NetTCPConnection -LocalPort 8781 -State Listen -ErrorAction SilentlyContinue)) {
    $oldCompetitionWebPort = $env:WEB_PORT
    $oldCompetitionApiPort = $env:API_PORT
    try {
        $env:WEB_PORT = "8781"
        $env:API_PORT = "8801"
        Start-Process -FilePath (Get-Command "node.exe").Source -ArgumentList "scripts/dev-web.mjs" -WorkingDirectory $competitionRoot -WindowStyle Hidden
    } finally {
        $env:WEB_PORT = $oldCompetitionWebPort
        $env:API_PORT = $oldCompetitionApiPort
    }
}
Write-Output "Competition Web: http://127.0.0.1:8781/"
Write-Output "API docs: http://127.0.0.1:8801/docs"
Write-Output "Local competition account: competition / Competition@2026"
Write-Output "Select CEA-COMPETITION (fictional aggregate data)."
