import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EntityTable } from '@/features/network/EntityTable'
import { GraphCanvas } from '@/features/network/GraphCanvas'
import { GraphInspector } from '@/features/network/GraphInspector'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorPanel } from '@/components/Button'
import type { GraphEdge, Node } from '@/api/types'

const nodes: Node[] = [
  { id: 'N_A', x: 0, y: 0, node_type: 'junction', name: 'West' },
  { id: 'N_B', x: 40, y: 0, node_type: 'junction', name: 'East' },
  { id: 'N_C', x: 40, y: 18, node_type: 'curb_interface', name: 'Curb' },
]

const edges: GraphEdge[] = [
  {
    id: 'E_AB',
    u: 'N_A',
    v: 'N_B',
    geometry: [
      [0, 0],
      [40, 0],
    ],
    length_m: 40,
    edge_type: 'sidewalk',
    name: 'Main footway',
    provenance_class: 'synthetic',
    evidence_ids: [],
  },
  {
    id: 'E_BC',
    u: 'N_B',
    v: 'N_C',
    geometry: [
      [40, 0],
      [40, 18],
    ],
    length_m: 18,
    edge_type: 'sidewalk',
    name: 'Curb link',
    provenance_class: 'synthetic',
    evidence_ids: [],
  },
  // Parallel edge: same endpoints as E_AB, different ID. It must stay selectable.
  {
    id: 'E_AB_ALT',
    u: 'N_A',
    v: 'N_B',
    geometry: [
      [0, 0],
      [40, 0],
    ],
    length_m: 40,
    edge_type: 'crossing',
    name: 'Parallel route',
    provenance_class: 'synthetic',
    evidence_ids: [],
  },
]

const emptyOverlays = {
  confirmedRouteEdgeIds: [],
  possibleRouteEdgeIds: [],
  closedEdgeIds: [],
  temporaryEdgeIds: [],
}

describe('GraphCanvas', () => {
  it('renders one hit target per edge, keyed by edge id', () => {
    render(<GraphCanvas nodes={nodes} edges={edges} crossings={[]} overlays={emptyOverlays} />)
    for (const edge of edges) {
      expect(screen.getByTestId(`edge-hit-${edge.id}`)).toBeInTheDocument()
    }
  })

  it('describes itself for assistive technology with counts and the crossing caveat', () => {
    render(
      <GraphCanvas
        nodes={nodes}
        edges={edges}
        crossings={[
          { edge_ids: ['E_AB', 'E_BC'], point: [40, 0], connected_via_shared_node: false, shared_node_ids: [] },
        ]}
        overlays={emptyOverlays}
      />,
    )
    const svg = screen.getByTestId('graph-canvas')
    expect(svg).toHaveAttribute('role', 'img')
    const label = svg.getAttribute('aria-label') ?? ''
    expect(label).toContain('3 directed edges')
    expect(label).toContain('3 nodes')
    expect(label).toContain('share a node')
    expect(screen.getAllByTestId('graph-crossing')).toHaveLength(1)
  })

  it('selects an edge by its id, not by its endpoints', async () => {
    const onSelectEdge = vi.fn()
    render(
      <GraphCanvas nodes={nodes} edges={edges} crossings={[]} overlays={emptyOverlays} onSelectEdge={onSelectEdge} />,
    )
    await userEvent.click(screen.getByTestId('edge-hit-E_AB_ALT'))
    expect(onSelectEdge).toHaveBeenCalledWith('E_AB_ALT')
  })

  it('selects a node from the canvas', async () => {
    const onSelectNode = vi.fn()
    render(
      <GraphCanvas
        nodes={nodes}
        edges={edges}
        crossings={[]}
        overlays={emptyOverlays}
        onSelectNode={onSelectNode}
      />,
    )
    await userEvent.click(screen.getByTestId('node-N_C'))
    expect(onSelectNode).toHaveBeenCalledWith('N_C')
  })

  it('renders an empty graph without crashing', () => {
    render(<GraphCanvas nodes={[]} edges={[]} crossings={[]} overlays={emptyOverlays} />)
    expect(screen.getByTestId('graph-canvas')).toBeInTheDocument()
  })

  it('renders a single-node graph', () => {
    render(<GraphCanvas nodes={[nodes[0]!]} edges={[]} crossings={[]} overlays={emptyOverlays} />)
    expect(screen.getByTestId('node-N_A')).toBeInTheDocument()
  })

  it('marks closed and temporary edges with testable classes', () => {
    const { container } = render(
      <GraphCanvas
        nodes={nodes}
        edges={edges}
        crossings={[]}
        overlays={{ ...emptyOverlays, closedEdgeIds: ['E_BC'], temporaryEdgeIds: ['E_AB'] }}
      />,
    )
    expect(container.querySelector('.graph-edge--closed')).not.toBeNull()
    expect(container.querySelector('.graph-edge--temporary')).not.toBeNull()
    expect(screen.getByTestId('closure-E_BC')).toBeInTheDocument()
  })

  it('distinguishes confirmed from possible-only routes by line style', () => {
    const { container } = render(
      <GraphCanvas
        nodes={nodes}
        edges={edges}
        crossings={[]}
        overlays={{ ...emptyOverlays, confirmedRouteEdgeIds: ['E_AB'], possibleRouteEdgeIds: ['E_BC'] }}
      />,
    )
    const confirmed = container.querySelector('.graph-edge--confirmed .graph-edge__line')
    const possible = container.querySelector('.graph-edge--possible .graph-edge__line')
    expect(confirmed).not.toBeNull()
    expect(possible).not.toBeNull()
    // Dash pattern encodes "possible" independently of colour.
    expect(window.getComputedStyle(possible!).strokeDasharray).not.toBe('')
  })

  it('exposes zoom controls that stay keyboard reachable', async () => {
    render(<GraphCanvas nodes={nodes} edges={edges} crossings={[]} overlays={emptyOverlays} />)
    await userEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    await userEvent.click(screen.getByRole('button', { name: 'Zoom out' }))
    await userEvent.click(screen.getByTestId('reset-view'))
  })
})

describe('EntityTable (keyboard-equivalent control surface)', () => {
  it('lists every edge with its id, direction and length', () => {
    render(
      <EntityTable
        nodes={nodes}
        edges={edges}
        edgeStates={[]}
        onSelectEdge={() => {}}
        onSelectNode={() => {}}
      />,
    )
    const table = screen.getByTestId('edge-table')
    expect(within(table).getByTestId('edge-row-E_AB')).toBeInTheDocument()
    expect(within(table).getByTestId('edge-row-E_AB_ALT')).toBeInTheDocument()
    expect(within(table).getAllByText('N_A → N_B')).toHaveLength(2) // the parallel edge shares endpoints
    expect(within(table).getAllByText('40.0 m')).toHaveLength(2)
  })

  it('selects an edge with the keyboard alone', async () => {
    const onSelectEdge = vi.fn()
    render(
      <EntityTable nodes={nodes} edges={edges} edgeStates={[]} onSelectEdge={onSelectEdge} onSelectNode={() => {}} />,
    )
    const button = screen.getByTestId('edge-row-E_BC')
    button.focus()
    await userEvent.keyboard('{Enter}')
    expect(onSelectEdge).toHaveBeenCalledWith('E_BC')
    await userEvent.keyboard(' ')
    expect(onSelectEdge).toHaveBeenCalledTimes(2)
  })

  it('filters by identifier without losing the keyboard path', async () => {
    render(
      <EntityTable nodes={nodes} edges={edges} edgeStates={[]} onSelectEdge={() => {}} onSelectNode={() => {}} />,
    )
    await userEvent.type(screen.getByRole('searchbox', { name: /filter/i }), 'E_BC')
    expect(screen.queryByTestId('edge-row-E_AB')).not.toBeInTheDocument()
    expect(screen.getByTestId('edge-row-E_BC')).toBeInTheDocument()
  })

  it('shows the modeled state and closure badge per edge', () => {
    render(
      <EntityTable
        nodes={nodes}
        edges={edges}
        edgeStates={[
          { edgeId: 'E_AB', state: 'PASS', closed: false, temporary: false, onConfirmedRoute: true, onPossibleRoute: false },
          { edgeId: 'E_BC', state: 'FAIL', closed: true, temporary: false, onConfirmedRoute: false, onPossibleRoute: false },
        ]}
        onSelectEdge={() => {}}
        onSelectNode={() => {}}
      />,
    )
    expect(screen.getAllByText(/Closed/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Pass in modeled checks/).length).toBeGreaterThan(0)
  })

  it('switches to a node-only view', async () => {
    render(
      <EntityTable nodes={nodes} edges={edges} edgeStates={[]} onSelectEdge={() => {}} onSelectNode={() => {}} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Nodes' }))
    expect(screen.getByTestId('node-table')).toBeInTheDocument()
    expect(screen.getByTestId('node-row-N_C')).toBeInTheDocument()
  })
})

describe('GraphInspector', () => {
  const evidence = [
    {
      id: 'EV-W',
      element_id: 'E_AB',
      field: 'width_mm',
      value: 1200,
      unit: 'mm',
      method: 'survey',
      source: 'test survey',
      observed_at: '2026-02-01T10:00:00Z',
      verification_status: 'unverified' as const,
      provenance_class: 'synthetic' as const,
      synthetic: true,
    },
  ]

  it('prompts for a selection when nothing is selected', () => {
    render(
      <GraphInspector
        edge={null}
        node={null}
        evidence={[]}
        verdicts={[]}
        findings={[]}
        edgeState={null}
        isClosed={false}
        isTemporary={false}
        result={null}
        originLabel={() => '—'}
      />,
    )
    expect(screen.getByText(/Select an edge or node/i)).toBeInTheDocument()
  })

  it('shows edge attributes in their physical units', () => {
    render(
      <GraphInspector
        edge={edges[0]!}
        node={null}
        evidence={evidence}
        verdicts={[]}
        findings={[]}
        edgeState={{ state: 'PASS', reasonCodes: [], relevantChecks: 3, confirmedEligible: true, possiblyEligible: true }}
        isClosed={false}
        isTemporary={false}
        result={null}
        originLabel={() => '—'}
      />,
    )
    expect(screen.getByText('40.000 m')).toBeInTheDocument()
    expect(screen.getByText('N_A → N_B')).toBeInTheDocument()
    expect(screen.getByText('1200 mm')).toBeInTheDocument()
  })

  it('says explicitly when no evidence exists instead of showing a blank', () => {
    render(
      <GraphInspector
        edge={edges[0]!}
        node={null}
        evidence={[]}
        verdicts={[]}
        findings={[]}
        edgeState={null}
        isClosed={false}
        isTemporary={false}
        result={null}
        originLabel={() => '—'}
      />,
    )
    expect(screen.getByText(/No observation exists for this element/i)).toBeInTheDocument()
  })

  it('labels a node as an origin/destination using the scenario data', () => {
    render(
      <GraphInspector
        edge={null}
        node={nodes[0]!}
        evidence={[]}
        verdicts={[]}
        findings={[]}
        edgeState={null}
        isClosed={false}
        isTemporary={false}
        result={null}
        originLabel={(nodeId) => (nodeId === 'N_A' ? 'West transit stop (origin)' : '—')}
      />,
    )
    expect(screen.getByText('West transit stop (origin)')).toBeInTheDocument()
    expect(screen.getByText(/0\.00, 0\.00 \(metres\)/)).toBeInTheDocument()
  })
})

describe('shared components', () => {
  it('renders a status badge with its text label, not colour alone', () => {
    render(
      <StatusBadge
        meta={{ label: 'Possible only', glyph: '◐', tone: 'unknown', description: 'Hypothetical route' }}
      />,
    )
    expect(screen.getByText('Possible only')).toBeInTheDocument()
    expect(screen.getByText(/Hypothetical route/)).toBeInTheDocument()
  })

  it('renders an error panel with the backend code and a retry action', async () => {
    const onClick = vi.fn()
    render(
      <ErrorPanel
        title="Cannot load the network"
        code="NETWORK_UNREACHABLE"
        message="Cannot reach the analysis service."
        action={
          <button type="button" onClick={onClick}>
            Retry
          </button>
        }
      />,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('NETWORK_UNREACHABLE')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(onClick).toHaveBeenCalled())
  })
})