import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { StatusBadge } from '@/components/StatusBadge'
import { formatHash } from '@/lib/format'

/**
 * Screen 1 — project dashboard.
 *
 * Reflects exactly what the backend exposes. When only the seeded synthetic
 * project exists, that is stated rather than padded with fabricated records.
 */
export function ProjectDashboard() {
  const { projects, projectId, selectProject, setView, graph, rulesets, scenarioSummary, current } =
    useWorkspace()

  if (projects.loading) return <Spinner label="Loading projects" />
  if (projects.error) {
    return (
      <ErrorPanel
        title="Cannot load projects"
        code={projects.error.code}
        message={projects.error.userMessage}
        action={<Button onClick={() => window.location.reload()}>Retry</Button>}
      />
    )
  }

  const items = projects.data?.projects ?? []
  if (items.length === 0) {
    return (
      <EmptyState
        title="No projects on the server"
        description="The backend returned an empty project list. Import a dataset through the API, then reload."
        action={
          <Button variant="primary" onClick={() => window.location.reload()}>
            Reload
          </Button>
        }
      />
    )
  }

  return (
    <div className="dashboard">
      <Panel
        title="Projects"
        subtitle={`${items.length} project(s) exposed by the analysis service`}
        flush
      >
        <table className="data-table" data-testid="project-table">
          <caption>Projects returned by GET /api/v1/projects</caption>
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">Study area</th>
              <th scope="col">Data provenance</th>
              <th scope="col">Jurisdiction</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((project) => {
              const isActive = project.id === projectId
              const isSynthetic = ['synthetic', 'synthetic_fixture'].includes(
                project.dataset_source?.provenance_class ?? '',
              )
              return (
                <tr key={project.id} aria-selected={isActive}>
                  <td>
                    <div className="dashboard__name">{project.name}</div>
                    <div className="dashboard__id mono">{project.id}</div>
                    {isSynthetic ? (
                      <StatusBadge
                        meta={{
                          label: 'Synthetic demo data',
                          glyph: '⚑',
                          tone: 'info',
                          description:
                            'Every geometry and measurement in this project is invented for demonstration. It is not a real place and not field-measured.',
                        }}
                        size="sm"
                      />
                    ) : null}
                  </td>
                  <td className="truncate">{project.study_area_description || '—'}</td>
                  <td>
                    <div className="mono">{project.dataset_source?.provenance_class ?? '—'}</div>
                    <div className="dashboard__license">{project.dataset_source?.license ?? '—'}</div>
                  </td>
                  <td className="mono">{project.jurisdiction ?? 'unspecified'}</td>
                  <td>
                    <Button
                      variant={isActive ? 'primary' : 'secondary'}
                      onClick={() => {
                        selectProject(project.id)
                        setView('network')
                      }}
                      data-testid={`open-project-${project.id}`}
                    >
                      {isActive ? 'Open workspace' : 'Open'}
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Panel>

      <div className="dashboard__grid">
        <Panel title="Active project" subtitle="Identities that make results traceable">
          {graph ? (
            <dl className="kv kv--cols-2">
              <div className="kv__row">
                <dt className="kv__term">Graph version</dt>
                <dd className="kv__value mono">{graph.graph_version_id}</dd>
              </div>
              <div className="kv__row">
                <dt className="kv__term">Content hash</dt>
                <dd className="kv__value mono">{formatHash(graph.content_hash, 16)}</dd>
              </div>
              <div className="kv__row">
                <dt className="kv__term">Coordinate basis</dt>
                <dd className="kv__value">
                  {graph.basis.kind === 'local_planar_meters'
                    ? 'Local planar metres (not geographic)'
                    : graph.basis.kind}
                </dd>
              </div>
              <div className="kv__row">
                <dt className="kv__term">Network size</dt>
                <dd className="kv__value numeric">
                  {graph.nodes.length} nodes · {graph.edges.length} directed edges ·{' '}
                  {graph.evidence.length} evidence records
                </dd>
              </div>
              <div className="kv__row">
                <dt className="kv__term">Unlinked crossings</dt>
                <dd className="kv__value numeric">
                  {graph.unlinked_crossings.filter((c) => !c.connected_via_shared_node).length}
                </dd>
              </div>
              <div className="kv__row">
                <dt className="kv__term">Active scenario</dt>
                <dd className="kv__value mono">
                  {scenarioSummary ? `${scenarioSummary.id} (revision ${scenarioSummary.revision})` : '—'}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="inspector__note">Select a project to load its network.</p>
          )}
        </Panel>

        <Panel title="Ruleset & profiles" subtitle="What every verdict is measured against">
          {rulesets ? (
            <div className="dashboard__ruleset">
              <StatusBadge
                meta={{
                  label: rulesets.rulepacks[0]?.legal_applicability === 'unverified'
                    ? 'Legal applicability unverified'
                    : String(rulesets.rulepacks[0]?.legal_applicability),
                  glyph: '⚖',
                  tone: 'unknown',
                  description:
                    rulesets.rulepacks[0]?.disclaimer ??
                    'This rulepack has not been reviewed against any legal standard.',
                }}
              />
              <ul className="dashboard__profiles">
                {rulesets.profiles.map((profile) => (
                  <li key={profile.id}>
                    <span className="mono">{profile.id}</span>
                    <span className="dashboard__profile-name">{profile.name}</span>
                  </li>
                ))}
              </ul>
              <p className="inspector__note">
                Profiles are demonstration configurations, not disability standards. Verdict wording is
                “Pass in modeled checks”, “Fail”, “Unknown” or “Not applicable”.
              </p>
            </div>
          ) : (
            <Spinner label="Loading ruleset" />
          )}
        </Panel>

        <Panel title="Latest analysis" subtitle="Stored run for this workspace">
          {current ? (
            <dl className="kv kv--cols-2">
              <div className="kv__row">
                <dt className="kv__term">Run</dt>
                <dd className="kv__value mono">{current.run.id}</dd>
              </div>
              <div className="kv__row">
                <dt className="kv__term">Semantic hash</dt>
                <dd className="kv__value mono">{formatHash(current.run.semantic_hash, 16)}</dd>
              </div>
              <div className="kv__row">
                <dt className="kv__term">Phase / profile</dt>
                <dd className="kv__value mono">
                  {current.result.phase_id} · {current.result.profile_id}
                </dd>
              </div>
              <div className="kv__row">
                <dt className="kv__term">Scenario revision</dt>
                <dd className="kv__value numeric">{current.run.scenario_revision}</dd>
              </div>
            </dl>
          ) : (
            <EmptyState
              title="No analysis run yet"
              description="Run an analysis in the Analysis workspace; the result and its hashes are stored on the server."
              icon="◷"
              action={
                <Button variant="primary" onClick={() => setView('analysis')}>
                  Go to analysis
                </Button>
              }
            />
          )}
        </Panel>
      </div>
    </div>
  )
}