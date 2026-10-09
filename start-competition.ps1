param(
    [string]$DatabasePath = (Join-Path $PSScriptRoot "services\platform-api\ceair-competition.db"),
    [ValidateRange(1024, 65535)][int]$ApiPort = 8801,
    [ValidateRange(1024, 65535)][int]$WebPort = 8781,
    [switch]$NewRehearsal
)

$ErrorActionPreference = "Stop"
$competitionRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$competitionApi = Join-Path $competitionRoot "services\platform-api"

if ($ApiPort -eq $WebPort) { throw "API and Web ports must be different." }
if ($NewRehearsal) {
    $DatabasePath = Join-Path $competitionApi ("ceair-competition-rehearsal-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
}
$competitionApiRunning = Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue
$competitionWebRunning = Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue
if ($competitionWebRunning -and ($NewRehearsal -or $PSBoundParameters.ContainsKey("DatabasePath"))) {
    throw "Web port $WebPort is occupied. Choose another ApiPort and WebPort for a fresh rehearsal."
}
if ($competitionApiRunning -and ($NewRehearsal -or $PSBoundParameters.ContainsKey("DatabasePath"))) {
    throw "API port $ApiPort is occupied. Choose another ApiPort and WebPort for a fresh rehearsal."
}
if (-not $competitionApiRunning) {
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
        Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$ApiPort" -WorkingDirectory $competitionApi -WindowStyle Hidden -RedirectStandardOutput (Join-Path $competitionApi "competition-api-$ApiPort.log") -RedirectStandardError (Join-Path $competitionApi "competition-api-$ApiPort-error.log")
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
        $competitionHealth = Invoke-RestMethod "http://127.0.0.1:$ApiPort/health/ready" -TimeoutSec 2
        if ($competitionHealth.status -eq "ready") { $competitionReady = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $competitionDeadline)
if (-not $competitionReady) {
    throw "Competition API did not become ready. Check services/platform-api/competition-api-$ApiPort-error.log."
}
if (-not $competitionWebRunning) {
    $oldCompetitionWebPort = $env:WEB_PORT
    $oldCompetitionApiPort = $env:API_PORT
    try {
        $env:WEB_PORT = "$WebPort"
        $env:API_PORT = "$ApiPort"
        Start-Process -FilePath (Get-Command "node.exe").Source -ArgumentList "scripts/dev-web.mjs" -WorkingDirectory $competitionRoot -WindowStyle Hidden
    } finally {
        $env:WEB_PORT = $oldCompetitionWebPort
        $env:API_PORT = $oldCompetitionApiPort
    }
}
$competitionWebReady = $false
$competitionWebDeadline = (Get-Date).AddSeconds(15)
do {
    try {
        $competitionWebHealth = Invoke-WebRequest "http://127.0.0.1:$WebPort/" -UseBasicParsing -TimeoutSec 2
        if ($competitionWebHealth.StatusCode -eq 200) { $competitionWebReady = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $competitionWebDeadline)
if (-not $competitionWebReady) { throw "Competition Web did not become ready on port $WebPort." }
Write-Output "Competition Web: http://127.0.0.1:$WebPort/"
Write-Output "API docs: http://127.0.0.1:$ApiPort/docs"
Write-Output "Rehearsal database: $DatabasePath"
Write-Output "Local competition account: competition / Competition@2026"
Write-Output "Select CEA-COMPETITION (fictional aggregate data)."
