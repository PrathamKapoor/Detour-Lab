import { useMemo, useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { EntityTable, type EdgeRowState } from '@/features/network/EntityTable'
import { GraphCanvas } from '@/features/network/GraphCanvas'
import { GraphInspector } from '@/features/network/GraphInspector'
import { TabPanel, Tabs } from '@/components/Dialog'

/**
 * Screen 2 — network & map studio.
 *
 * The canvas and the entity table are two views of the same backend data. The
 * table is the accessible control surface; the canvas is the spatial view. No
 * verdict is computed here.
 */
export function NetworkStudio() {
  const {
    graph,
    graphLoading,
    graphError,
    reloadGraph,
    selectedEdgeId,
    selectedNodeId,
    selectEdge,
    selectNode,
    current,
    scenario,
  } = useWorkspace()
  const [tab, setTab] = useState('canvas')

  const edgeStates = useMemo<EdgeRowState[]>(() => {
    const evaluations = current?.result.edge_evaluations ?? []
    const closedIds = new Set(
      (scenario?.phases ?? [])
        .filter((phase) => phase.id === (current?.result.phase_id ?? ''))
        .flatMap((phase) => phase.closed_edge_ids),
    )
    const temporaryIds = new Set(
      (scenario?.temporary_edges ?? []).map((temporary) => `TMP::${temporary.id}`),
    )
    const confirmed = new Set(
      (current?.result.od_results ?? []).flatMap((od) => od.confirmed_path_edge_ids),
    )
    const possible = new Set((current?.result.od_results ?? []).flatMap((od) => od.possible_path_edge_ids))
    return evaluations.map((evaluation) => ({
      edgeId: evaluation.edge_id,
      state: evaluation.state,
      closed: closedIds.has(evaluation.edge_id),
      temporary: temporaryIds.has(evaluation.edge_id),
      onConfirmedRoute: confirmed.has(evaluation.edge_id),
      onPossibleRoute: possible.has(evaluation.edge_id),
    }))
  }, [current, scenario])

  const overlays = useMemo(
    () => ({
      confirmedRouteEdgeIds: (current?.result.od_results ?? []).flatMap((od) => od.confirmed_path_edge_ids ?? []),
      possibleRouteEdgeIds: (current?.result.od_results ?? []).flatMap((od) => od.possible_path_edge_ids ?? []),
      closedEdgeIds: (scenario?.phases ?? [])
        .filter((phase) => phase.id === (current?.result.phase_id ?? ''))
        .flatMap((phase) => phase.closed_edge_ids ?? []),
      temporaryEdgeIds: (current?.result.edge_evaluations ?? [])
        .map((evaluation) => evaluation.edge_id)
        .filter((id) => id.startsWith('TMP::')),
    }),
    [current, scenario],
  )

  const selectedEdge = useMemo(
    () => graph?.edges.find((edge) => edge.id === selectedEdgeId) ?? null,
    [graph, selectedEdgeId],
  )
  const selectedNode = useMemo(
    () => graph?.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [graph, selectedNodeId],
  )
  const selectedEvaluation = useMemo(
    () => current?.result.edge_evaluations.find((evaluation) => evaluation.edge_id === selectedEdgeId) ?? null,
    [current, selectedEdgeId],
  )

  if (graphLoading) return <Spinner label="Loading network" />
  if (graphError) {
    return (
      <ErrorPanel
        title="Cannot load the network"
        code={graphError.code}
        message={graphError.userMessage}
        action={<Button onClick={reloadGraph}>Retry</Button>}
      />
    )
  }
  if (!graph) return <EmptyState title="No project selected" description="Open a project first." />

  const originLabel = (nodeId: string) => {
    const od = (scenario?.origins_destinations ?? []).find((entry) => entry.node_id === nodeId)
    return od ? `${od.label} (${od.kind})` : '—'
  }

  return (
    <div className="studio">
      <div className="studio__main">
        <Panel
          title="Network studio"
          subtitle={
            <>
              {graph.basis.kind === 'local_planar_meters'
                ? 'Local planar metres — not geographic coordinates'
                : graph.basis.kind}
              . Directed edges are identified by edge ID, never by endpoint position.
            </>
          }
          actions={
            <span className="app-context">
              <span className="app-context__label">Phase overlay</span>
              <span className="mono">
                {current ? current.result.phase_id : 'Run an analysis to overlay results'}
              </span>
            </span>
          }
          flush
        >
          <Tabs
            label="Network view"
            active={tab}
            onChange={setTab}
            tabs={[
              { id: 'canvas', label: 'Canvas' },
              { id: 'table', label: 'Entity table' },
              { id: 'legend', label: 'Legend' },
            ]}
          />
          <div className="studio__canvas-wrap">
            <TabPanel id="canvas" active={tab}>
              {graph.nodes.length === 0 ? (
                <EmptyState title="This graph has no nodes" description="Nothing to render." />
              ) : (
                <GraphCanvas
                  nodes={graph.nodes}
                  edges={graph.edges}
                  crossings={graph.unlinked_crossings}
                  overlays={overlays}
                  selectedEdgeId={selectedEdgeId}
                  selectedNodeId={selectedNodeId}
                  onSelectEdge={selectEdge}
                  onSelectNode={selectNode}
                />
              )}
            </TabPanel>

            <TabPanel id="table" active={tab}>
              <EntityTable
                nodes={graph.nodes}
                edges={graph.edges}
                edgeStates={edgeStates}
                selectedEdgeId={selectedEdgeId}
                selectedNodeId={selectedNodeId}
                onSelectEdge={selectEdge}
                onSelectNode={selectNode}
              />
            </TabPanel>

            <TabPanel id="legend" active={tab}>
              <GraphLegend />
            </TabPanel>
          </div>
        </Panel>
      </div>

      <aside className="studio__inspector" aria-label="Selected element inspector">
        <Panel title="Inspector" subtitle="Attributes, evidence and modeled results">
          <GraphInspector
            edge={selectedEdge}
            node={selectedNode}
            evidence={graph.evidence}
            verdicts={current?.result.verdicts ?? []}
            findings={selectedEvaluation?.findings ?? []}
            edgeState={
              selectedEvaluation
                ? {
                    state: selectedEvaluation.state,
                    reasonCodes: selectedEvaluation.reason_codes ?? [],
                    relevantChecks: selectedEvaluation.relevant_check_count,
                    confirmedEligible: selectedEvaluation.confirmed_eligible,
                    possiblyEligible: selectedEvaluation.possibly_eligible,
                  }
                : null
            }
            isClosed={overlays.closedEdgeIds.includes(selectedEdgeId ?? '')}
            isTemporary={overlays.temporaryEdgeIds.includes(selectedEdgeId ?? '')}
            result={current?.result ?? null}
            originLabel={originLabel}
          />
        </Panel>
      </aside>
    </div>
  )
}

function GraphLegend() {
  const items: { glyph: string; label: string; description: string }[] = [
    { glyph: '━', label: 'Confirmed route', description: 'Every modeled check passed with adequate evidence.' },
    { glyph: '┄', label: 'Possible-only route', description: 'Uses at least one UNKNOWN edge. Not confirmed.' },
    { glyph: '╳', label: 'Closed for construction', description: 'Excluded from routing in the active phase.' },
    { glyph: '◇', label: 'Temporary connection', description: 'Modelled temporary path, not field-confirmed constructible.' },
    { glyph: '◌', label: 'Geometric crossing, not a connection', description: 'Edges that cross in space share no node ID.' },
    { glyph: '▣', label: 'Selected element', description: 'Currently under inspection.' },
  ]
  return (
    <ul className="legend">
      {items.map((item) => (
        <li key={item.label} className="legend__item">
          <span className="legend__glyph" aria-hidden="true">
            {item.glyph}
          </span>
          <span>
            <strong>{item.label}</strong>
            <span className="legend__description">{item.description}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}