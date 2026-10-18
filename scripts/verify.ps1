<#
.SYNOPSIS
    One-command verification for DETOUR LAB (Windows PowerShell).

.DESCRIPTION
    Runs the real checks and prints their raw output:
      * backend unit / property / integration tests (pytest)
      * static analysis (ruff)
      * an actual HTTP smoke test against a live uvicorn process
      * a deterministic replay check

    Exits non-zero on the first real failure so CI can rely on it.
#>
[CmdletBinding()]
param(
    [int]$Port = 8077,
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repoRoot '.venv'
$apiDir = Join-Path $repoRoot 'apps\api'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path $python)) { throw "Run scripts/setup.ps1 first (missing $python)" }
$env:PYTHONPATH = $apiDir

function Write-Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }

Write-Step 'Static analysis (ruff)'
& $python -m ruff check $apiDir --config (Join-Path $apiDir 'pyproject.toml')
if ($LASTEXITCODE -ne 0) { throw 'ruff reported problems' }

Write-Step 'Backend test suite (pytest)'
& $python -m pytest (Join-Path $apiDir 'tests') -q
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }

if (-not $SkipFrontend) {
    $webDir = Join-Path $repoRoot 'apps\web'
    if (Test-Path (Join-Path $webDir 'package.json')) {
        Write-Step 'Frontend type-check and unit tests'
        Push-Location $webDir
        try {
            npm run typecheck
            if ($LASTEXITCODE -ne 0) { throw 'Frontend type-check failed' }
            npm run test
            if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' }
        } finally { Pop-Location }
    }
}

Write-Step "Live HTTP smoke test on http://127.0.0.1:$Port"
$server = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'detour_lab.api.main:app', '--host', '127.0.0.1', '--port', "$Port" `
    -WorkingDirectory $apiDir -PassThru -WindowStyle Hidden
try {
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 3
            $ready = $true
            break
        } catch { }
    }
    if (-not $ready) { throw 'API did not become healthy in time' }
    Write-Host "health: $($health.status) | engine $($health.engine_version) | rulepack $($health.rulepack_id) $($health.rulepack_hash)"
    Write-Host "dataset: $($health.dataset_id) | provenance $($health.dataset_provenance) | synthetic: $($health.synthetic_data)"

    $body = @{ profile_id = 'DEMO_PROFILE_MANUAL_WHEELCHAIR'; phase_id = 'phase-1' } | ConvertTo-Json
    $first = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/demo/evaluate" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20
    $second = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/demo/evaluate" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20

    Write-Host "OD matrix ($($first.profile_id) / $($first.phase_id)):"
    foreach ($od in $first.od_results) {
        Write-Host ("  {0} -> {1}: confirmed={2} possible={3} distance_m={4}" -f `
            $od.origin_id, $od.destination_id, $od.confirmed_reachable, $od.possibly_reachable, $od.confirmed_distance_m)
    }

    $a = $first | ConvertTo-Json -Depth 20 -Compress
    $b = $second | ConvertTo-Json -Depth 20 -Compress
    if ($a -ne $b) { throw 'Replay over HTTP was not deterministic' }
    Write-Host 'deterministic replay over HTTP: identical payload' -ForegroundColor Green
} finally {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}

Write-Step 'VERIFICATION PASSED' -ForegroundColor Green