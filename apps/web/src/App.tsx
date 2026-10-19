import { WorkspaceProvider, useWorkspace, type ViewId } from '@/app/workspace'
import type { ApiClient } from '@/api/client'
import { AnalysisWorkspace } from '@/features/analysis/AnalysisWorkspace'
import { ComparisonView } from '@/features/analysis/ComparisonView'
import { EvidenceQueue } from '@/features/evidence/EvidenceQueue'
import { FailureLab } from '@/features/failure-lab/FailureLab'
import { NetworkStudio } from '@/features/network/NetworkStudio'
import { ProjectDashboard } from '@/features/projects/ProjectDashboard'
import { ReportsPanel } from '@/features/reports/ReportsPanel'
import { ScenarioEditor } from '@/features/scenario/ScenarioEditor'
import { PhaseExplorer } from '@/features/phases/PhaseExplorer'
import { BranchExplorer } from '@/features/branches/BranchExplorer'
import { OptimizationStudio } from '@/features/optimization/OptimizationStudio'
import '@/features/network/graph.css'
import '@/features/phases/phases.css'
import '@/styles/app.css'

const NAV: { id: ViewId; label: string; hint: string }[] = [
  { id: 'projects', label: 'Projects', hint: 'Datasets and identities' },
  { id: 'network', label: 'Network', hint: 'Graph, attributes, evidence' },
  { id: 'scenario', label: 'Scenario', hint: 'Closures and measurements' },
  { id: 'analysis', label: 'Analysis', hint: 'Profile, phase, findings' },
  { id: 'phases', label: 'Phases', hint: 'Timeline and continuity' },
  { id: 'optimization', label: 'Fix This Plan', hint: 'Interventions and verification' },
  { id: 'failure-lab', label: 'Failure Lab', hint: 'Break the plan on purpose' },
  { id: 'evidence', label: 'Evidence', hint: 'Verification queue' },
  { id: 'branches', label: 'Branches', hint: 'Alternative plans' },
  { id: 'compare', label: 'Compare', hint: 'Baseline against modified' },
  { id: 'reports', label: 'Reports', hint: 'Manifest and PDF packet' },
]

function Shell() {
  const { view, setView, projects, scenarioSummary, current, stale, isDirty, rulesets } = useWorkspace()

  const projectId = projects.data?.projects[0]?.id
  const offline = projects.error !== null

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-brand">
          <span className="app-brand__mark" aria-hidden="true">
            ⬡
          </span>
          <div>
            <h1 className="app-brand__name">DETOUR LAB</h1>
            <p className="app-brand__tag">Pedestrian detour planning &amp; model verification</p>
          </div>
        </div>

        <div className="app-header__context">
          <span className="app-context">
            <span className="app-context__label">Project</span>
            <span className="mono">{projectId ?? '—'}</span>
          </span>
          <span className="app-context">
            <span className="app-context__label">Scenario</span>
            <span className="mono" data-testid="context-scenario">
              {scenarioSummary ? `${scenarioSummary.id} r${scenarioSummary.revision}` : '—'}
            </span>
          </span>
          <span className="app-context">
            <span className="app-context__label">Rulepack</span>
            <span className="mono">{rulesets?.rulepacks[0]?.id ?? '—'}</span>
          </span>
        </div>

        <div className="app-header__status" role="status" aria-live="polite">
          {offline ? (
            <span className="app-flag app-flag--fail">API unreachable</span>
          ) : current ? (
            <span className={`app-flag ${stale ? 'app-flag--unknown' : 'app-flag--pass'}`}>
              {stale ? 'Result is stale' : `Result ${current.result.phase_id}`}
            </span>
          ) : (
            <span className="app-flag">No analysis yet</span>
          )}
          {isDirty ? <span className="app-flag app-flag--unknown">Unsaved edits</span> : null}
        </div>
      </header>

      <nav className="app-sidebar" aria-label="Workspace sections">
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`app-nav__item ${view === item.id ? 'app-nav__item--active' : ''}`}
            aria-current={view === item.id ? 'page' : undefined}
            onClick={() => setView(item.id)}
            data-testid={`nav-${item.id}`}
          >
            <span className="app-nav__label">{item.label}</span>
            <span className="app-nav__hint">{item.hint}</span>
          </button>
        ))}

        <div className="app-sidebar__footer">
          <p className="app-disclaimer">
            Planning analysis — <strong>not certified</strong>. Synthetic demonstration data; the rulepack
            has not been reviewed against any legal standard.
          </p>
        </div>
      </nav>

      <main className="app-main" id="main">
        <div className="app-main__inner">
          {view === 'projects' ? <ProjectDashboard /> : null}
          {view === 'network' ? <NetworkStudio /> : null}
          {view === 'scenario' ? <ScenarioEditor /> : null}
          {view === 'analysis' ? <AnalysisWorkspace /> : null}
          {view === 'phases' ? <PhaseExplorer /> : null}
          {view === 'optimization' ? <OptimizationStudio /> : null}
          {view === 'failure-lab' ? <FailureLab /> : null}
          {view === 'compare' ? <ComparisonView /> : null}
          {view === 'reports' ? <ReportsPanel /> : null}
          {view === 'evidence' ? <EvidenceQueue /> : null}
          {view === 'branches' ? <BranchExplorer /> : null}
        </div>
      </main>
    </div>
  )
}

export default function App({ api }: { api: ApiClient }) {
  return (
    <WorkspaceProvider api={api}>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <Shell />
    </WorkspaceProvider>
  )
}