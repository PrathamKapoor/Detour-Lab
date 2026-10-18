<#
.SYNOPSIS
    Regenerate the shared API/TypeScript contracts from the Pydantic models.

.DESCRIPTION
    Writes packages/contracts/{openapi.json,types.ts,domain-schema.json}.
    Running it twice must produce byte-identical output; the test-suite asserts that.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Run scripts/setup.ps1 first (missing $python)" }
$env:PYTHONPATH = Join-Path $repoRoot 'apps\api'

Push-Location $repoRoot
try {
    & $python -W ignore -c "from detour_lab.reporting.contracts import generate_contracts; print(generate_contracts('packages/contracts'))"
    if ($LASTEXITCODE -ne 0) { throw 'Contract generation failed' }
} finally { Pop-Location }