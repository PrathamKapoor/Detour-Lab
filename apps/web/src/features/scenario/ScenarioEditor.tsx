import { useMemo, useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel } from '@/components/Button'
import { Dialog } from '@/components/Dialog'
import { SelectField, TextField } from '@/components/Field'
import { StatusBadge } from '@/components/StatusBadge'
import type { ScenarioEdit } from '@/api/types'

/**
 * Screen 3 — construction scenario editor.
 *
 * Editing rules honoured here:
 *  - nothing is applied locally and then *displayed* as saved; the backend is
 *    the only writer, and a successful save is confirmed by re-reading it;
 *  - the immutable baseline graph is never touched (FR-005, INV-07);
 *  - edits are queued with their backend operation names and submitted in one
 *    optimistic-concurrency update;
 *  - a 409 is surfaced as a conflict with a reload action - the draft is never
 *    silently retried over newer work.
 */
export function ScenarioEditor() {
  const {
    scenario,
    scenarioSummary,
    scenarioLoading,
    scenarioError,
    reloadScenario,
    phaseId,
    setPhaseId,
    pendingEdits,
    isDirty,
    addEdit,
    removeEdit,
    discardEdits,
    saveEdits,
    saveError,
    saving,
    conflict,
    resolveConflictByReload,
    selectedEdgeId,
    createBranch,
    branchError,
    branching,
    setView,
    scenarios,
    selectScenario,
  } = useWorkspace()

  const [measurementOpen, setMeasurementOpen] = useState(false)
  const [field, setField] = useState('width_mm')
  const [value, setValue] = useState('')
  const [unit, setUnit] = useState('mm')
  const [fieldError, setFieldError] = useState<string | null>(null)

  const phases = useMemo(() => scenario?.phases ?? [], [scenario])
  const activePhase = useMemo(
    () => phases.find((phase) => phase.id === phaseId) ?? phases[0] ?? null,
    [phases, phaseId],
  )
  const closedEdgeIds = activePhase?.closed_edge_ids ?? []

  if (scenarioLoading) return <p className="inspector__note">Loading scenario…</p>
  if (scenarioError) {
    return (
      <ErrorPanel
        title="Cannot load the scenario"
        code={scenarioError.code}
        message={scenarioError.userMessage}
        action={<Button onClick={reloadScenario}>Retry</Button>}
      />
    )
  }
  if (!scenario) return <EmptyState title="No scenario selected" />

  const stageClosure = () => {
    if (!selectedEdgeId) return
    addEdit({
      op: 'close_edge',
      target_id: selectedEdgeId,
      params: { phases: [activePhase?.id ?? phaseId] },
      reason: 'Closed from the planning studio',
    })
    // Stay on the editor: the user must be able to see and review what they just
    // staged before applying it to the server.
  }

  const stageMeasurement = () => {
    const trimmed = value.trim()
    if (!trimmed) {
      setFieldError('Enter a measured value. An empty value would remain Unknown, not zero.')
      return
    }
    const numeric = Number(trimmed)
    if (!Number.isFinite(numeric)) {
      setFieldError('Enter a number. Text attributes such as surface must use a dropdown, not free text.')
      return
    }
    if (!selectedEdgeId) {
      setFieldError('Select an edge first (canvas or entity table).')
      return
    }
    addEdit({
      op: 'update_attribute',
      target_id: selectedEdgeId,
      params: {
        field,
        value: numeric,
        unit: unit.trim() || null,
        method: 'manual_entry',
        source: 'Planner entry in the DETOUR LAB studio',
        provenance_class: 'assumed',
        synthetic: false,
        observed_at: new Date().toISOString(),
      },
      reason: 'Manual measurement entered in the studio',
    })
    setMeasurementOpen(false)
    setValue('')
    setFieldError(null)
  }

  return (
    <div className="editor">
      <div className="editor__main">
        <Panel
          title="Construction scenario editor"
          subtitle={
            <>
              Scenario <code>{scenario.id}</code> · revision{' '}
              <strong data-testid="scenario-revision">{scenario.revision}</strong> ·{' '}
              {scenario.edits.length} committed edit(s)
            </>
          }
          actions={
            <>
              <SelectField
                label="Scenario"
                value={scenario.id}
                onChange={(event) => selectScenario(event.target.value)}
                hint="Switching scenarios never copies their edits."
                data-testid="scenario-select"
              >
                {scenarios.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.name} (r{entry.revision})
                  </option>
                ))}
              </SelectField>
              <Button onClick={() => setView('network')} disabled={!selectedEdgeId}>
                {selectedEdgeId ? `Selected: ${selectedEdgeId}` : 'Select an edge first'}
              </Button>
              <Button variant="primary" onClick={stageClosure} disabled={!selectedEdgeId}>
                Close selected edge in phase
              </Button>
            </>
          }
        >
          <div className="editor__controls">
            <SelectField
              label="Phase"
              value={activePhase?.id ?? ''}
              onChange={(event) => setPhaseId(event.target.value)}
              hint={activePhase?.notes || 'Logical phase order; no construction calendar is asserted.'}
            >
              {phases.map((phase) => (
                <option key={phase.id} value={phase.id}>
                  {phase.label || phase.id}
                </option>
              ))}
            </SelectField>

            <div className="editor__phase-state">
              <h3 className="inspector__heading">Closures in {activePhase?.id ?? '—'}</h3>
              {closedEdgeIds.length === 0 ? (
                <p className="inspector__note">No edges are closed in this phase.</p>
              ) : (
                <ul className="edit-list">
                  {closedEdgeIds.map((edgeId) => {
                    const removable = !(scenario.edits ?? []).some(
                      (edit) => edit.op === 'close_edge' && edit.target_id === edgeId,
                    )
                    return (
                      <li key={edgeId} className="edit-item">
                        <span className="edit-item__text">
                          {edgeId} — {removable ? 'declared with the phase' : 'added by an edit'}
                        </span>
                        {removable ? (
                          <Button
                            onClick={() =>
                              createBranch({
                                phaseId: activePhase?.id ?? phaseId,
                                reopenEdgeId: edgeId,
                              })
                            }
                            disabled={branching}
                            data-testid={`reopen-${edgeId}`}
                          >
                            Reopen via branch
                          </Button>
                        ) : (
                          <StatusBadge
                            meta={{
                              label: 'Reopen via branch',
                              glyph: '⑂',
                              tone: 'info',
                              description:
                                'The R0 API appends edits but never rewrites phase declarations. Reopening therefore creates an immutable branch scenario.',
                            }}
                            size="sm"
                          />
                        )}
                      </li>
                    )
                  })}
                </ul>
              )}
              {branchError ? (
                <ErrorPanel
                  title="Could not create the branch"
                  code={branchError.code}
                  message={branchError.userMessage}
                />
              ) : null}
            </div>
          </div>
        </Panel>

        <Panel
          title="Pending edits"
          subtitle="Submitted together through PATCH /scenarios/{id} with an optimistic revision check"
          actions={
            <>
              <Button onClick={discardEdits} disabled={!isDirty} data-testid="discard-edits">
                Discard
              </Button>
              <Button
                variant="primary"
                onClick={() => void saveEdits()}
                disabled={!isDirty || saving}
                busy={saving}
                data-testid="save-edits"
              >
                Apply {pendingEdits.length} edit(s)
              </Button>
            </>
          }
        >
          {isDirty ? (
            <p className="dirty-banner" role="status">
              <span className="dirty-banner__glyph" aria-hidden="true">
                ●
              </span>
              Unsaved edits: results below still describe the last committed revision
              {scenarioSummary?.revision ?? scenario.revision}.
            </p>
          ) : null}

          {pendingEdits.length === 0 ? (
            <EmptyState
              title="No pending edits"
              description="Select an edge on the network, then close it or record a measurement."
              icon="✎"
            />
          ) : (
            <ul className="edit-list" data-testid="pending-edits">
              {pendingEdits.map((edit: ScenarioEdit, index: number) => (
                <li key={`${edit.op}-${edit.target_id}-${index}`} className="edit-item edit-item--pending">
                  <div>
                    <div className="edit-item__text">
                      {edit.op} · {edit.target_id}
                    </div>
                    <div className="edit-item__text">
                      {JSON.stringify(edit.params).slice(0, 160)}
                    </div>
                  </div>
                  <Button variant="ghost" onClick={() => removeEdit(index)} aria-label={`Remove edit ${index + 1}`}>
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}

          {saveError ? (
            <ErrorPanel
              title="The scenario was not saved"
              code={saveError.code}
              message={saveError.userMessage}
              details={
                conflict ? (
                  <p className="inspector__note">
                    You submitted revision {conflict.expected}; the server is at revision{' '}
                    {conflict.actual}. Your draft edits are still listed above — copy anything you need,
                    then reload the server state.
                  </p>
                ) : undefined
              }
              action={
                <Button onClick={resolveConflictByReload} data-testid="reload-scenario">
                  Reload server state
                </Button>
              }
            />
          ) : null}
        </Panel>
      </div>

      <aside className="editor__side" aria-label="Scenario details">
        <Panel title="Committed edits" subtitle={`${scenario.edits.length} on revision ${scenario.revision}`} flush>
          {scenario.edits.length === 0 ? (
            <div className="panel__body">
              <p className="inspector__note">
                This scenario matches the immutable base graph: no closures or measurements have been
                committed yet.
              </p>
            </div>
          ) : (
            <ul className="edit-list panel__body">
              {scenario.edits.map((edit, index) => (
                <li key={`${edit.op}-${edit.target_id}-${index}`} className="edit-item">
                  <span className="edit-item__text">
                    {edit.op} · {edit.target_id}
                  </span>
                  <span className="inspector__note">rev {scenario.revision - scenario.edits.length + index + 1}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Record a measurement"
          subtitle="Adds an evidence record; existing history is never overwritten"
          actions={
            <Button onClick={() => setMeasurementOpen(true)} disabled={!selectedEdgeId}>
              Add measurement
            </Button>
          }
        >
          <p className="inspector__note">
            Measurements are appended as new evidence records with your entry as the source. If a new
            measurement disagrees with an existing one, the attribute becomes Unknown and both claims are
            retained until a reviewer decides.
          </p>
        </Panel>
      </aside>

      <Dialog
        open={measurementOpen}
        title={`Record a measurement for ${selectedEdgeId ?? '—'}`}
        description="The engine converts units exactly or rejects them. Unsupported units stay Unknown; nothing is guessed."
        onClose={() => setMeasurementOpen(false)}
        footer={
          <>
            <Button onClick={() => setMeasurementOpen(false)}>Cancel</Button>
            <Button variant="primary" onClick={stageMeasurement} data-testid="save-measurement">
              Stage measurement
            </Button>
          </>
        }
      >
        <SelectField
          label="Attribute"
          value={field}
          onChange={(event) => setField(event.target.value)}
          hint="Fields the demonstration rulepack evaluates"
        >
          <option value="width_mm">width_mm — clear width</option>
          <option value="slope_percent">slope_percent — signed grade along u→v</option>
        </SelectField>
        <TextField
          label="Measured value"
          value={value}
          onChange={setValue}
          inputMode="decimal"
          placeholder={field === 'width_mm' ? '1200' : '4.5'}
          error={fieldError ?? undefined}
        />
        <TextField
          label="Unit"
          value={unit}
          onChange={setUnit}
          hint="width_mm accepts mm, cm, m, in, ft; slope_percent accepts percent, %, ratio, degree"
        />
      </Dialog>
    </div>
  )
}