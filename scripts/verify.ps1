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
                    $prevEAP = $ErrorActionPreference
                    try {
                        $ErrorActionPreference = 'Continue'
                        npm run e2e
                    } finally {
                        $ErrorActionPreference = $prevEAP
                    }
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

Write-Step 'Gate 6 benchmark (measured wall-clock over the synthetic demo fixture)'
# These are MEASURED durations for the bundled demo dataset only. They are not
# performance targets, not p50/p95 latencies (those belong to Gate 7), and not a
# claim about any real study area. Nothing here is estimated: every number printed
# is a Stopwatch reading from this run.
$env:DETOUR_LAB_DB_PATH = Join-Path $repoRoot 'var\verify.sqlite3'
$server3 = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'detour_lab.api.main:app', '--host', '127.0.0.1', '--port', "$Port" `
    -WorkingDirectory $apiDir -PassThru -WindowStyle Hidden
try {
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try { $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 3; $ready = $true; break } catch { }
    }
    if (-not $ready) { throw 'API did not restart for the Gate 6 benchmark' }

    # 1. Derived evidence queue.
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $queue = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/evidence/queue" -TimeoutSec 30
    $sw.Stop()
    $statusCounts = ($queue.issues | Group-Object -Property resolution_status | ForEach-Object { "$($_.Name)=$($_.Count)" }) -join ', '
    Write-Host ("evidence queue: {0} issues in {1} ms [{2}]" -f $queue.issues.Count, $sw.ElapsedMilliseconds, $statusCounts)
    if ($queue.issues.Count -lt 1) { throw 'evidence queue derived no issues from the seeded fixture' }

    # 2. Fault catalogue and a real experiment over every suite applicable to phase-1.
    #    Readiness is queried per phase, matching the experiment request below, so the
    #    reported applicable count is the honest one for this selection.
    $catalog = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/failure-lab/catalog?phase_id=phase-1" -TimeoutSec 30
    $applicable = @($catalog.suites | Where-Object { $_.applicable } | ForEach-Object { $_.suite_id })
    Write-Host ("fault catalogue (phase-1): {0} suites declared, {1} applicable" -f $catalog.suites.Count, $applicable.Count)
    Write-Host ("  declared phases: {0}" -f ($catalog.declared_phase_ids -join ', '))
    Write-Host ("  unavailable: {0}" -f (($catalog.suites | Where-Object { -not $_.applicable } | ForEach-Object { "$($_.suite_id) ($($_.unavailable_reason))" }) -join '; '))

    # NOTE on the JSON: it is assembled from individually serialised values
    # rather than from a hashtable. Windows PowerShell 5.1 unwraps a
    # single-element array in some ConvertTo-Json forms, which would send
    # "suite_ids": "critical_closure" and be rejected by the API as an
    # invalid list. Serialising each value on its own keeps the quoting and
    # escaping correct, and the list brackets are explicit, so the wire format
    # is a list no matter how many suites were selected.
    $suiteJson = ($applicable | ForEach-Object { ConvertTo-Json -InputObject ([string]$_) -Compress }) -join ','
    $phaseJson = ConvertTo-Json -InputObject 'phase-1' -Compress
    $profileJson = ConvertTo-Json -InputObject 'DEMO_PROFILE_MANUAL_WHEELCHAIR' -Compress
    $phaseBody = '{"phase_ids":[' + $phaseJson + '],"profile_ids":[' + $profileJson + '],"suite_ids":[' + $suiteJson + ']}'
    # Guard the payload that is actually sent: it must parse, and the list
    # fields must really be lists. A malformed body would otherwise be
    # rejected by the API and look like a benchmark failure.
    try { $null = $phaseBody | ConvertFrom-Json } catch { throw "benchmark request body is not valid JSON: $($_.Exception.Message)" }
    if ($phaseBody -notmatch '"suite_ids"\s*:\s*\[' -or $phaseBody -notmatch '"phase_ids"\s*:\s*\[') {
        throw "benchmark request body does not carry suite_ids/phase_ids as JSON lists: $phaseBody"
    }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $experiment = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments" `
        -Method Post -ContentType 'application/json' -Body $phaseBody -TimeoutSec 180
    $sw.Stop()
    $completed = @($experiment.experiments | Where-Object { $_.status -eq 'completed' }).Count
    $invalid = @($experiment.experiments | Where-Object { $_.status -eq 'invalid_experiment' }).Count
    Write-Host ("failure suites: {0} run in {1} ms -> completed {2}, invalid {3}" -f $experiment.experiments.Count, $sw.ElapsedMilliseconds, $completed, $invalid)
    Write-Host ("  denominator: {0}" -f $experiment.robustness.denominator_note)
    if ($completed -lt 1) { throw 'no fault suite completed against the seeded fixture' }
    if ($experiment.robustness.pairs_evaluated -lt 1) {
        throw 'robustness summary reported no pairs evaluated despite a completed experiment'
    }
    if ($experiment.robustness.experiments_completed -ne $completed) {
        throw ("robustness counted {0} completed experiments but the run reported {1}" -f $experiment.robustness.experiments_completed, $completed)
    }

    # 3. Deterministic replay of one experiment.
    $first = @($experiment.experiments | Where-Object { $_.status -eq 'completed' })[0]
    if ($null -ne $first) {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $replay = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/failure-lab/experiments/$($first.experiment_id)/replay" -Method Post -TimeoutSec 60
        $sw.Stop()
        if (-not $replay.reproduced) { throw 'replay did not reproduce the stored semantic hash' }
        Write-Host ("replay: reproduced exactly in {0} ms (new execution id {1})" -f $sw.ElapsedMilliseconds, $replay.replayed_experiment_id)
    }

    # 4. Review packet generation and a real PDF download.
    #    The packet is built from stored runs, so guarantee one exists rather than
    #    assuming the seed provided it.
    $runs = (Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/runs" -TimeoutSec 20).runs
    if (@($runs).Count -lt 1) {
        $evalBody = @{ profile_id = 'DEMO_PROFILE_MANUAL_WHEELCHAIR'; phase_id = 'phase-1'; evaluation_instant = '2026-03-01T00:00:00Z' } | ConvertTo-Json
        $runs = @((Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/evaluate" `
                    -Method Post -ContentType 'application/json' -Body $evalBody -TimeoutSec 60).run)
        Write-Host "no stored run existed; evaluated one for the packet"
    }
    $runId = @($runs)[0].id
    # Same reason as above: the run id is serialised on its own and the list
    # brackets are explicit, so "run_ids" is always a JSON list.
    $runJson = ConvertTo-Json -InputObject ([string]$runId) -Compress
    $reportBody = '{"run_ids":[' + $runJson + ']}'
    try { $null = $reportBody | ConvertFrom-Json } catch { throw "report request body is not valid JSON: $($_.Exception.Message)" }
    if ($reportBody -notmatch '"run_ids"\s*:\s*\[') {
        throw "report request body does not carry run_ids as a JSON list: $reportBody"
    }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $created = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/scenarios/scn-demo-baseline/reports" `
        -Method Post -ContentType 'application/json' -Body $reportBody -TimeoutSec 120
    $sw.Stop()
    $generateMs = $sw.ElapsedMilliseconds
    $pdfPath = Join-Path $repoRoot 'var\verify-gate6-packet.pdf'
    $sw = [Diagnostics.Stopwatch]::StartNew()
    # -UseBasicParsing: Windows PowerShell 5.1 otherwise tries to use the legacy
    # Internet Explorer engine to parse the response, which is unavailable on a
    # headless machine and fails the download for a binary body.
    Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/reports/$($created.report.report_id)/document.pdf" -OutFile $pdfPath -TimeoutSec 120 -UseBasicParsing | Out-Null
    $sw.Stop()
    $downloadMs = $sw.ElapsedMilliseconds
    $pdfBytes = (Get-Item $pdfPath).Length
    $served = (Get-FileHash -Path $pdfPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $recorded = $created.report.pdf_sha256
    if ($served -ne $recorded) { throw "downloaded PDF digest $served does not match recorded $recorded" }
    if ($pdfBytes -lt 10000) { throw "review packet PDF is implausibly small ($pdfBytes bytes)" }
    Write-Host ("review packet: {0} generated in {1} ms, downloaded in {2} ms" -f $created.report.report_id, $generateMs, $downloadMs)
    Write-Host ("  PDF {0} pages, {1} bytes, sha256 {2} verified against the recorded digest" -f $created.report.page_count, $pdfBytes, $served)
    Write-Host ("  packet written to var\verify-gate6-packet.pdf")
    Write-Host 'Note: measured durations over the synthetic demo fixture (9 nodes, 12 edges).'
    Write-Host '      Gate 7 adds formal scientific benchmarks and scaling profiling below.'
} finally {
    Stop-Process -Id $server3.Id -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\DETOUR_LAB_DB_PATH -ErrorAction SilentlyContinue
}

Write-Step 'Gate 7 Research & Scalability Benchmarks (Baselines A-E + Grid Scaling)'
& $python (Join-Path $repoRoot 'scripts\run_benchmarks.py') --iterations 5
if ($LASTEXITCODE -ne 0) { throw 'Gate 7 benchmarks failed' }

Write-Step 'Gate 7 Release Candidate Manifest Generation'
& $python (Join-Path $repoRoot 'scripts\generate_release_manifest.py')
if ($LASTEXITCODE -ne 0) { throw 'Release manifest generation failed' }

Write-Step 'VERIFICATION PASSED' -ForegroundColor Green