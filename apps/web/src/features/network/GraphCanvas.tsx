import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { GraphEdge, Node, UnlinkedCrossing } from '@/api/types'
import { clampZoom, computeBounds, crossingsToMarkers, fitBounds, midpoint, toScreen, toScreenPath } from '@/lib/geometry'
import './graph.css'

export interface GraphOverlays {
  confirmedRouteEdgeIds: readonly string[]
  possibleRouteEdgeIds: readonly string[]
  closedEdgeIds: readonly string[]
  temporaryEdgeIds: readonly string[]
}

interface GraphCanvasProps {
  nodes: readonly Node[]
  edges: readonly GraphEdge[]
  crossings: readonly UnlinkedCrossing[]
  overlays: GraphOverlays
  selectedNodeId?: string | null
  selectedEdgeId?: string | null
  hoveredEdgeId?: string | null
  onSelectNode?: (nodeId: string) => void
  onSelectEdge?: (edgeId: string) => void
  height?: number
  ariaLabel?: string
}

const ROUTE_WIDTH = 4
const BASE_EDGE_WIDTH = 2

/**
 * Offline SVG renderer for a local-planar pedestrian graph.
 *
 * Contract points that matter:
 *  - coordinates are the backend's own metres; no projection is applied;
 *  - edges are identified by **edge id**, never by endpoint coordinates, so
 *    parallel edges stay individually selectable;
 *  - a geometric crossing without a shared node is drawn as an explicit marker
 *    and never as a connection;
 *  - the canvas is a *visual* surface: the same information is available in a
 *    keyboard-navigable table, which is what screen-reader users operate.
 */
export function GraphCanvas({
  nodes,
  edges,
  crossings,
  overlays,
  selectedNodeId,
  selectedEdgeId,
  hoveredEdgeId,
  onSelectNode,
  onSelectEdge,
  height = 520,
  ariaLabel = 'Pedestrian network graph',
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 900, height })
  const [view, setView] = useState({ zoom: 1, panX: 0, panY: 0 })

  const bounds = useMemo(() => computeBounds(nodes, edges), [nodes, edges])
  const base = useMemo(
    () => fitBounds(bounds, { width: size.width, height, padding: 48 }),
    [bounds, size.width, height],
  )

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      setSize({ width: Math.max(entry.contentRect.width, 320), height })
    })
    observer.observe(element)
    setSize({ width: Math.max(element.clientWidth, 320), height })
    return () => observer.disconnect()
  }, [height])

  const transform = useMemo(
    () => ({
      scale: base.transform.scale * view.zoom,
      offsetX: base.transform.offsetX + view.panX,
      offsetY: base.transform.offsetY + view.panY,
    }),
    [base, view],
  )

  const confirmed = useMemo(() => new Set(overlays.confirmedRouteEdgeIds), [overlays.confirmedRouteEdgeIds])
  const possible = useMemo(
    () => new Set(overlays.possibleRouteEdgeIds.filter((id) => !confirmed.has(id))),
    [overlays.possibleRouteEdgeIds, confirmed],
  )
  const closed = useMemo(() => new Set(overlays.closedEdgeIds), [overlays.closedEdgeIds])
  const temporary = useMemo(() => new Set(overlays.temporaryEdgeIds), [overlays.temporaryEdgeIds])

  const onWheel = useCallback((event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault()
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12
    setView((previous) => ({ ...previous, zoom: clampZoom(previous.zoom * factor) }))
  }, [])

  const startDrag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null)
  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return
    startDrag.current = { x: event.clientX, y: event.clientY, panX: view.panX, panY: view.panY }
    // Pointer capture is unavailable in jsdom and older browsers; panning still works.
    if (typeof event.currentTarget.setPointerCapture === 'function') {
      event.currentTarget.setPointerCapture(event.pointerId)
    }
  }
  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!startDrag.current) return
    setView((previous) => ({
      ...previous,
      panX: startDrag.current!.panX + (event.clientX - startDrag.current!.x),
      panY: startDrag.current!.panY + (event.clientY - startDrag.current!.y),
    }))
  }
  const endDrag = () => {
    startDrag.current = null
  }

  const markerPoints = useMemo(() => crossingsToMarkers(crossings, transform), [crossings, transform])

  const summary = `${edges.length} directed edges, ${nodes.length} nodes. ${markerPoints.length} geometric crossings detected; a crossing is only a connection when both edges share a node ID.`

  return (
    <div className="graph-canvas" ref={containerRef}>
      <svg
        className="graph-canvas__svg"
        viewBox={`0 0 ${size.width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={`${ariaLabel}. ${summary}`}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        data-testid="graph-canvas"
      >
        <defs>
          <marker
            id="arrowhead"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--line-strong)" />
          </marker>
          <marker
            id="arrowhead-confirmed"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--status-pass)" />
          </marker>
          <marker
            id="arrowhead-possible"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--status-unknown)" />
          </marker>
        </defs>

        <g className="graph-canvas__edges">
          {edges.map((edge) => {
            const onRoute = confirmed.has(edge.id) || possible.has(edge.id)
            const isClosed = closed.has(edge.id)
            const isTemporary = temporary.has(edge.id) || edge.id.startsWith('TMP::')
            const isSelected = edge.id === selectedEdgeId
            const isHovered = edge.id === hoveredEdgeId
            const mid = midpoint(edge.geometry, transform)
            const classes = [
              'graph-edge',
              onRoute ? 'graph-edge--route' : '',
              confirmed.has(edge.id) ? 'graph-edge--confirmed' : '',
              possible.has(edge.id) ? 'graph-edge--possible' : '',
              isClosed ? 'graph-edge--closed' : '',
              isTemporary ? 'graph-edge--temporary' : '',
              isSelected ? 'graph-edge--selected' : '',
              isHovered ? 'graph-edge--hovered' : '',
            ]
              .filter(Boolean)
              .join(' ')
            return (
              <g key={edge.id} className={classes}>
                <path
                  d={toScreenPathLocal(edge.geometry, transform)}
                  className="graph-edge__hit"
                  data-testid={`edge-hit-${edge.id}`}
                  onClick={(event) => {
                    event.stopPropagation()
                    onSelectEdge?.(edge.id)
                  }}
                >
                  <title>{`${edge.id}: ${edge.name || edge.edge_type} (${edge.u} → ${edge.v})`}</title>
                </path>
                <path
                  d={toScreenPathLocal(edge.geometry, transform)}
                  className="graph-edge__line"
                  strokeWidth={isSelected ? ROUTE_WIDTH + 2 : onRoute ? ROUTE_WIDTH : BASE_EDGE_WIDTH}
                  markerEnd={`url(#${
                    confirmed.has(edge.id) ? 'arrowhead-confirmed' : possible.has(edge.id) ? 'arrowhead-possible' : 'arrowhead'
                  })`}
                />
                {mid && (onRoute || isSelected) ? (
                  <circle cx={mid[0]} cy={mid[1]} r={3} className="graph-edge__marker" />
                ) : null}
                {isClosed && mid ? (
                  <g className="graph-edge__closure" data-testid={`closure-${edge.id}`}>
                    <line x1={mid[0] - 6} y1={mid[1] - 6} x2={mid[0] + 6} y2={mid[1] + 6} />
                    <line x1={mid[0] - 6} y1={mid[1] + 6} x2={mid[0] + 6} y2={mid[1] - 6} />
                  </g>
                ) : null}
              </g>
            )
          })}
        </g>

        <g className="graph-canvas__crossings">
          {markerPoints.map((marker, index) => (
            <circle
              key={`crossing-${index}`}
              cx={marker.x}
              cy={marker.y}
              r={6}
              className="graph-crossing"
              data-testid="graph-crossing"
            >
              <title>{`Geometric crossing of ${marker.edges[0]} and ${marker.edges[1]} — not a connection without a shared node`}</title>
            </circle>
          ))}
        </g>

        <g className="graph-canvas__nodes">
          {nodes.map((node) => {
            const [x, y] = toScreen([node.x, node.y], transform)
            const isSelected = node.id === selectedNodeId
            return (
              <g
                key={node.id}
                className={`graph-node ${isSelected ? 'graph-node--selected' : ''}`}
                onClick={(event) => {
                  event.stopPropagation()
                  onSelectNode?.(node.id)
                }}
                data-testid={`node-${node.id}`}
              >
                <circle cx={x} cy={y} r={isSelected ? 8 : 6} className="graph-node__dot" />
                <circle cx={x} cy={y} r={13} className="graph-node__hit" />
                <text x={x} y={y - 12} className="graph-node__label">
                  {node.id}
                </text>
                <title>{`${node.id} (${node.node_type ?? 'node'})${node.name ? `: ${node.name}` : ''}`}</title>
              </g>
            )
          })}
        </g>
      </svg>

      <div className="graph-canvas__controls">
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => setView((previous) => ({ ...previous, zoom: clampZoom(previous.zoom * 1.2) }))}
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => setView((previous) => ({ ...previous, zoom: clampZoom(previous.zoom / 1.2) }))}
          aria-label="Zoom out"
        >
          −
        </button>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => setView({ zoom: 1, panX: 0, panY: 0 })}
          data-testid="reset-view"
        >
          Reset view
        </button>
      </div>
    </div>
  )
}

function toScreenPathLocal(
  geometry: readonly [number, number][],
  t: { scale: number; offsetX: number; offsetY: number },
): string {
  return toScreenPath(geometry, t)
}

export type { GraphEdge }