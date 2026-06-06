$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendEnvPath = Join-Path $repoRoot "backend\.env"
$backendEnvExamplePath = Join-Path $repoRoot "backend\.env.example"

if (-not (Test-Path $backendEnvPath) -and (Test-Path $backendEnvExamplePath)) {
  Copy-Item $backendEnvExamplePath $backendEnvPath
  Write-Host "Created backend/.env from backend/.env.example"
}

$backendPort = "8000"
if (Test-Path $backendEnvPath) {
  $portLine = Get-Content $backendEnvPath | Where-Object { $_ -match "^\s*BACKEND_PORT\s*=" } | Select-Object -First 1
  if ($portLine) {
    $backendPort = ($portLine -split "=", 2)[1].Trim()
  }
}

$backendCommand = @"
Set-Location '$repoRoot'
if (Test-Path '.\.venv\Scripts\Activate.ps1') {
  . '.\.venv\Scripts\Activate.ps1'
}
uvicorn app.main:app --reload --app-dir backend --env-file backend/.env --port $backendPort
"@

$frontendPath = Join-Path $repoRoot "frontend"
$frontendCommand = @"
Set-Location '$frontendPath'
npm run dev
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand
Write-Host "Started backend and frontend dev servers in separate PowerShell windows."
