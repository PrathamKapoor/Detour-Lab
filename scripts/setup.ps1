<#
.SYNOPSIS
    One-command setup for DETOUR LAB (Windows PowerShell).

.DESCRIPTION
    Creates the backend virtual environment, installs pinned dependencies and
    verifies that every import resolves. Requires network access to PyPI.

    No secrets, no external services and no API keys are required.

.EXAMPLE
    pwsh -File scripts/setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repoRoot '.venv'
$apiDir = Join-Path $repoRoot 'apps\api'
$webDir = Join-Path $repoRoot 'apps\web'

function Write-Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }

Write-Step "Repository root: $repoRoot"

if (-not (Test-Path $venv)) {
    Write-Step 'Creating Python virtual environment'
    python -m venv $venv
} else {
    Write-Step 'Reusing existing virtual environment'
}

$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Virtual environment interpreter missing at $python" }

Write-Step 'Upgrading pip'
& $python -m pip install --upgrade pip | Out-Null

Write-Step 'Installing pinned backend dependencies'
& $python -m pip install -r (Join-Path $apiDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed' }

Write-Step 'Verifying backend imports'
$env:PYTHONPATH = $apiDir
& $python -c @"
from detour_lab.api.main import app
from detour_lab.ingestion.schema import load_local_planar_dataset
from detour_lab.rules.engine import load_rulepack
print('backend imports resolved; routes:', len(app.routes))
"@
if ($LASTEXITCODE -ne 0) { throw 'Backend import verification failed' }

if (-not $SkipFrontend) {
    if (Test-Path (Join-Path $webDir 'package.json')) {
        Write-Step 'Installing frontend dependencies'
        Push-Location $webDir
        try { npm install } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    } else {
        Write-Step 'Frontend package.json not present yet - skipping (Gate 3 work)'
    }
}

Write-Step 'Setup complete. Next: pwsh -File scripts/verify.ps1' -ForegroundColor Green