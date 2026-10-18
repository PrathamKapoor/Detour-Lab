import { useMemo, useState } from 'react'
import type { GraphEdge, Node } from '@/api/types'
import { SearchField } from '@/components/Field'
import { StatusBadge } from '@/components/StatusBadge'
import type { VerdictState } from '@contracts/types'
import { verdictMeta } from '@/lib/status'

export interface EdgeRowState {
  edgeId: string
  state: VerdictState | null
  closed: boolean
  temporary: boolean
  onConfirmedRoute: boolean
  onPossibleRoute: boolean
}

interface EntityTableProps {
  nodes: readonly Node[]
  edges: readonly GraphEdge[]
  edgeStates: readonly EdgeRowState[]
  selectedEdgeId?: string | null
  selectedNodeId?: string | null
  onSelectEdge: (edgeId: string) => void
  onSelectNode: (nodeId: string) => void
}

/**
 * Keyboard-operable equivalent of the graph canvas.
 *
 * The canvas is a *visual* surface; this table is the accessible control. Every
 * row is a real button, reachable by Tab, operable with Enter/Space, and it
 * exposes the same identifiers the backend uses.
 */
export function EntityTable({
  nodes,
  edges,
  edgeStates,
  selectedEdgeId,
  selectedNodeId,
  onSelectEdge,
  onSelectNode,
}: EntityTableProps) {
  const [filter, setFilter] = useState('')
  const [kind, setKind] = useState<'all' | 'edges' | 'nodes'>('all')

  const stateByEdge = useMemo(
    () => new Map(edgeStates.map((row) => [row.edgeId, row])),
    [edgeStates],
  )

  const needle = filter.trim().toLowerCase()
  const visibleEdges = useMemo(
    () =>
      edges.filter(
        (edge) =>
          needle.length === 0 ||
          edge.id.toLowerCase().includes(needle) ||
          (edge.name ?? '').toLowerCase().includes(needle) ||
          edge.u.toLowerCase().includes(needle) ||
          edge.v.toLowerCase().includes(needle),
      ),
    [edges, needle],
  )
  const visibleNodes = useMemo(
    () =>
      nodes.filter(
        (node) =>
          needle.length === 0 ||
          node.id.toLowerCase().includes(needle) ||
          (node.name ?? '').toLowerCase().includes(needle),
      ),
    [nodes, needle],
  )

  return (
    <div className="entity-table">
      <div className="entity-table__controls">
        <SearchField
          label="Filter"
          value={filter}
          onChange={setFilter}
          placeholder="Edge or node id…"
        />
        <div className="entity-table__kinds" role="group" aria-label="Entity kind">
          {(['all', 'edges', 'nodes'] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={`btn btn--sm ${kind === option ? 'btn--primary' : 'btn--ghost'}`}
              aria-pressed={kind === option}
              onClick={() => setKind(option)}
            >
              {option === 'all' ? 'All' : option === 'edges' ? 'Edges' : 'Nodes'}
            </button>
          ))}
        </div>
      </div>

      {kind !== 'nodes' ? (
        <table className="data-table" data-testid="edge-table">
          <caption>
            Directed edges ({visibleEdges.length} of {edges.length}). Activate a row to inspect it.
          </caption>
          <thead>
            <tr>
              <th scope="col">Edge ID</th>
              <th scope="col">Direction</th>
              <th scope="col">Type</th>
              <th scope="col">Length</th>
              <th scope="col">Model state</th>
            </tr>
          </thead>
          <tbody>
            {visibleEdges.map((edge) => {
              const row = stateByEdge.get(edge.id)
              const isSelected = edge.id === selectedEdgeId
              return (
                <tr
                  key={edge.id}
                  aria-selected={isSelected}
                  className="is-clickable"
                  onClick={() => onSelectEdge(edge.id)}
                >
                  <td>
                    <button
                      type="button"
                      className="row-button"
                      onClick={(event) => {
                        event.stopPropagation()
                        onSelectEdge(edge.id)
                      }}
                      data-testid={`edge-row-${edge.id}`}
                      aria-pressed={isSelected}
                    >
                      <span className="mono">{edge.id}</span>
                    </button>
                    {edge.name ? <div className="entity-table__sub truncate">{edge.name}</div> : null}
                  </td>
                  <td className="data-table__mono">
                    {edge.u} → {edge.v}
                  </td>
                  <td className="data-table__mono">{edge.edge_type ?? '—'}</td>
                  <td className="numeric">{edge.length_m.toFixed(1)} m</td>
                  <td>
                    {row ? (
                      <span className="entity-table__state">
                        {row.closed ? (
                          <StatusBadge
                            meta={{ label: 'Closed', glyph: '╳', tone: 'fail', description: 'Closed for construction in this phase.' }}
                            size="sm"
                          />
                        ) : row.state ? (
                          <StatusBadge meta={verdictMeta(row.state)} size="sm" />
                        ) : (
                          <span className="entity-table__muted">Not evaluated</span>
                        )}
                        {row.temporary ? (
                          <StatusBadge
                            meta={{ label: 'Temporary', glyph: '◇', tone: 'temp', description: 'Temporary connection.' }}
                            size="sm"
                          />
                        ) : null}
                      </span>
                    ) : (
                      <span className="entity-table__muted">Not evaluated</span>
                    )}
                  </td>
                </tr>
              )
            })}
            {visibleEdges.length === 0 ? (
              <tr>
                <td colSpan={5} className="entity-table__muted">
                  No edges match “{filter}”.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      ) : null}

      {kind !== 'edges' ? (
        <table className="data-table" data-testid="node-table">
          <caption>Nodes ({visibleNodes.length} of {nodes.length}). Activate a row to inspect it.</caption>
          <thead>
            <tr>
              <th scope="col">Node ID</th>
              <th scope="col">Type</th>
              <th scope="col">Planar position</th>
              <th scope="col">Name</th>
            </tr>
          </thead>
          <tbody>
            {visibleNodes.map((node) => (
              <tr
                key={node.id}
                aria-selected={node.id === selectedNodeId}
                className="is-clickable"
                onClick={() => onSelectNode(node.id)}
              >
                <td>
                  <button
                    type="button"
                    className="row-button"
                    onClick={(event) => {
                      event.stopPropagation()
                      onSelectNode(node.id)
                    }}
                    data-testid={`node-row-${node.id}`}
                    aria-pressed={node.id === selectedNodeId}
                  >
                    <span className="mono">{node.id}</span>
                  </button>
                </td>
                <td className="data-table__mono">{node.node_type ?? 'node'}</td>
                <td className="numeric">
                  {node.x.toFixed(1)}, {node.y.toFixed(1)}
                </td>
                <td className="truncate">{node.name ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  )
}