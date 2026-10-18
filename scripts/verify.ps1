<#
.SYNOPSIS
    One-command verification for DETOUR LAB (Windows PowerShell).

.DESCRIPTION
    Runs the real checks and prints their raw output:
      * backend unit / property / integration tests (pytest)
      * static analysis (ruff)
      * frontend type-check, lint, unit/integration tests and production build
      * Playwright end-to-end tests against the real backend (skipped with an
        explicit SKIPPED line when the browser runtime is unavailable)
      * an actual HTTP smoke test against a live uvicorn process
      * a deterministic replay check

    Exits non-zero on the first real failure so CI can rely on it.

    -SkipFrontend skips every frontend check and states that clearly; a skipped
    check is never reported as passing.
#>
[CmdletBinding()]
param(
    [int]$Port = 8077,
    [switch]$SkipFrontend,
    [switch]$SkipE2E
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

if ($SkipFrontend) {
    Write-Host '--- SKIPPED: frontend checks (-SkipFrontend). Not verified in this run. ---' -ForegroundColor Yellow
} else {
    $webDir = Join-Path $repoRoot 'apps\web'
    if (-not (Test-Path (Join-Path $webDir 'package.json'))) {
        Write-Host '--- SKIPPED: no apps/web/package.json found. Not verified in this run. ---' -ForegroundColor Yellow
    } else {
        Push-Location $webDir
        try {
            if (-not (Test-Path (Join-Path $webDir 'node_modules'))) {
                Write-Step 'Installing frontend dependencies (npm ci)'
                npm ci --no-audit --no-fund
                if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
            }

            Write-Step 'Frontend type-check (tsc)'
            npm run typecheck
            if ($LASTEXITCODE -ne 0) { throw 'Frontend type-check failed' }

            Write-Step 'Frontend lint (eslint)'
            npm run lint
            if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed' }

            Write-Step 'Frontend unit and integration tests (vitest)'
            npm run test
            if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' }

            Write-Step 'Frontend production build (vite)'
            npm run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend production build failed' }

            if ($SkipE2E) {
                Write-Host '--- SKIPPED: Playwright end-to-end tests (-SkipE2E). Not verified in this run. ---' -ForegroundColor Yellow
            } else {
                # A missing browser runtime is reported as SKIPPED, never as a pass.
                $browserProbe = Join-Path $env:LOCALAPPDATA 'ms-playwright'
                if (-not (Test-Path $browserProbe)) {
                    Write-Host '--- SKIPPED: Playwright browsers not installed. Run "npm run e2e:install" in apps\web. Not verified in this run. ---' -ForegroundColor Yellow
                } else {
                    Write-Step 'End-to-end tests against the real backend (playwright)'
                    npm run e2e
                    if ($LASTEXITCODE -ne 0) { throw 'End-to-end tests failed' }
                }
            }
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
    Write-Host "schema version: $($health.database_schema_version) | rows: $($health.row_counts | ConvertTo-Json -Compress)"

    $graph = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/projects/demo-project-synthetic/graph" -TimeoutSec 20
    Write-Host "dataset: $($graph.graph_version_id) | provenance $($graph.source.provenance_class) | $($graph.nodes.Count) nodes, $($graph.edges.Count) edges, $($graph.evidence.Count) evidence records"
    $unlinked = @($graph.unlinked_crossings | Where-Object { -not $_.connected_via_shared_node })
    Write-Host "topology QA: $($unlinked.Count) geometric crossing(s) that are NOT graph connections"

    $body = @{ profile_id = 'DEMO_PROFILE_MANUAL_WHEELCHAIR'; phase_id = 'phase-1'; evaluation_instant = '2026-03-01T00:00:00Z' } | ConvertTo-Json
    $first = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/evaluate" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20
    $second = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/evaluate" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20

    Write-Host "OD matrix ($($first.result.profile_id) / $($first.result.phase_id)):"
    foreach ($od in $first.result.od_results) {
        Write-Host ("  {0} -> {1}: confirmed={2} possible={3} distance_m={4}" -f `
            $od.origin_id, $od.destination_id, $od.confirmed_reachable, $od.possibly_reachable, $od.confirmed_distance_m)
    }
    Write-Host "counts: $($first.result.counts | ConvertTo-Json -Compress)"

    # The run envelope deliberately carries volatile metadata (run id, created_at),
    # so determinism is asserted on the semantic payload and its hash.
    $a = $first.result | ConvertTo-Json -Depth 20 -Compress
    $b = $second.result | ConvertTo-Json -Depth 20 -Compress
    if ($a -ne $b) { throw 'Replay over HTTP was not deterministic' }
    if ($first.run.semantic_hash -ne $second.run.semantic_hash) { throw 'Semantic hashes differ between identical runs' }
    if ($first.run.id -eq $second.run.id) { throw 'Each evaluation must produce its own run record' }
    Write-Host "deterministic replay over HTTP: identical result payload, semantic hash $($first.run.semantic_hash)" -ForegroundColor Green

    # Gate 2: canonical manifest from a stored run
    $runId = $first.run.id
    $manifest = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/runs/$runId/manifest" -TimeoutSec 20
    Write-Host ("manifest: schema {0} | rulepack {1} | unknowns {2} | known failures {3}" -f `
        $manifest.schema_version, $manifest.ruleset.id, $manifest.results.unknowns.Count, $manifest.results.known_failures.Count)
    Write-Host ("manifest disclaimer: {0}" -f $manifest.disclaimer)
    if ($manifest.ruleset.legal_applicability -ne 'unverified') { throw 'Rulepack legal applicability must remain unverified' }
    if (-not $manifest.semantic_hash.StartsWith('sha256:')) { throw 'Manifest semantic hash missing' }

    $replayed = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/evaluate" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20
    if ($replayed.run.semantic_hash -ne $first.run.semantic_hash) { throw 'Stored run semantic hash did not reproduce' }
    Write-Host "stored run replay: semantic hash $($first.run.semantic_hash)" -ForegroundColor Green
} finally {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}

Write-Step 'Restart persistence check (fresh process over the same database)'
$env:DETOUR_LAB_DB_PATH = Join-Path $repoRoot 'var\verify.sqlite3'
$server2 = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'detour_lab.api.main:app', '--host', '127.0.0.1', '--port', "$Port" `
    -WorkingDirectory $apiDir -PassThru -WindowStyle Hidden
try {
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try { $health2 = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 3; $ready = $true; break } catch { }
    }
    if (-not $ready) { throw 'API did not restart cleanly' }
    Write-Host ("after restart: rows {0}" -f ($health2.row_counts | ConvertTo-Json -Compress))
    $body2 = @{ profile_id = 'DEMO_PROFILE_MANUAL_WHEELCHAIR'; phase_id = 'phase-1'; evaluation_instant = '2026-03-01T00:00:00Z' } | ConvertTo-Json
    $after = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/evaluate" -Method Post -ContentType 'application/json' -Body $body2 -TimeoutSec 20
    Write-Host "after restart, same inputs -> semantic hash $($after.run.semantic_hash)" -ForegroundColor Green
} finally {
    Stop-Process -Id $server2.Id -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\DETOUR_LAB_DB_PATH -ErrorAction SilentlyContinue
}

Write-Step 'Contract generation determinism'
Push-Location $repoRoot
try {
    & $python -W ignore -c "from detour_lab.reporting.contracts import generate_contracts as g; import pathlib, shutil; a=pathlib.Path('var/contracts-a'); b=pathlib.Path('var/contracts-b'); [shutil.rmtree(p, ignore_errors=True) for p in (a,b)]; g(a); g(b); import sys; ok=all((a/n).read_bytes()==(b/n).read_bytes() for n in ('openapi.json','types.ts','domain-schema.json')); print('contract artefacts identical:', ok); sys.exit(0 if ok else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Contract generation was not deterministic' }
} finally { Pop-Location }

Write-Step 'VERIFICATION PASSED' -ForegroundColor Green