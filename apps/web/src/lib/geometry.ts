/**
 * Graph geometry helpers.
 *
 * The seeded dataset is **local planar metres**, not longitude/latitude, so this
 * module never applies a geographic projection. It computes bounds, an affine
 * world→screen transform (uniform scale + translate, so topology is never
 * distorted) and route overlays, and it is written to survive the degenerate
 * cases the domain allows: empty graphs, single points, zero-span bounds,
 * negative coordinates and near-coincident nodes.
 */

import type { EdgeGeometry, Node, UnlinkedCrossing } from '@/api/types'

export interface Bounds {
  minX: number
  minY: number
  maxX: number
  maxY: number
  width: number
  height: number
}

export interface Viewport {
  width: number
  height: number
  padding: number
}

export interface Transform {
  /** Scale applied uniformly to both axes. */
  scale: number
  offsetX: number
  offsetY: number
}

/** Minimum on-screen separation so coincident points stay clickable. */
export const MIN_SPAN = 1e-6

export const EMPTY_BOUNDS: Bounds = {
  minX: 0,
  minY: 0,
  maxX: 0,
  maxY: 0,
  width: MIN_SPAN,
  height: MIN_SPAN,
}

export function computeBounds(nodes: readonly Node[], edges: readonly { geometry: readonly [number, number][] }[]): Bounds {
  const xs: number[] = []
  const ys: number[] = []
  // Each coordinate is judged independently: one malformed value must not discard
  // otherwise valid extent on the other axis.
  for (const node of nodes) {
    if (Number.isFinite(node.x)) xs.push(node.x)
    if (Number.isFinite(node.y)) ys.push(node.y)
  }
  for (const edge of edges) {
    for (const [x, y] of edge.geometry ?? []) {
      if (Number.isFinite(x)) xs.push(x)
      if (Number.isFinite(y)) ys.push(y)
    }
  }
  if (xs.length === 0 || ys.length === 0) return { ...EMPTY_BOUNDS }
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  return {
    minX,
    maxX,
    minY,
    maxY,
    // A single node or a perfectly vertical/horizontal layout has a zero span on
    // one axis; report a minimum so the viewport maths stays finite.
    width: Math.max(maxX - minX, MIN_SPAN),
    height: Math.max(maxY - minY, MIN_SPAN),
  }
}

export interface FitResult {
  transform: Transform
  /** World-space rectangle actually visible, used for culling and tests. */
  visible: Bounds
}

/** Uniform-scale fit of world bounds into a viewport, preserving aspect ratio. */
export function fitBounds(bounds: Bounds, viewport: Viewport, zoom = 1): FitResult {
  const safeWidth = Math.max(viewport.width - viewport.padding * 2, 1)
  const safeHeight = Math.max(viewport.height - viewport.padding * 2, 1)
  // A degenerate bound (empty or single-point graph) must not divide by zero.
  const worldWidth = Math.max(bounds.width, MIN_SPAN)
  const worldHeight = Math.max(bounds.height, MIN_SPAN)
  const scale = Math.min(safeWidth / worldWidth, safeHeight / worldHeight) * Math.max(zoom, 0.01)
  const centreX = bounds.minX + bounds.width / 2
  const centreY = bounds.minY + bounds.height / 2
  return {
    transform: {
      scale,
      offsetX: viewport.width / 2 - centreX * scale,
      offsetY: viewport.height / 2 + centreY * scale, // SVG y grows downward
    },
    visible: {
      minX: centreX - safeWidth / (2 * scale),
      maxX: centreX + safeWidth / (2 * scale),
      minY: centreY - safeHeight / (2 * scale),
      maxY: centreY + safeHeight / (2 * scale),
      width: safeWidth / scale,
      height: safeHeight / scale,
    },
  }
}

export function toScreen(point: readonly [number, number], t: Transform): [number, number] {
  return [point[0] * t.scale + t.offsetX, -point[1] * t.scale + t.offsetY]
}

export function toScreenPath(geometry: readonly [number, number][], t: Transform): string {
  if (!geometry || geometry.length === 0) return ''
  return geometry
    .map(([x, y], index) => {
      const [sx, sy] = toScreen([x, y], t)
      return `${index === 0 ? 'M' : 'L'}${round(sx)} ${round(sy)}`
    })
    .join(' ')
}

/** Midpoint of an edge in screen space - used to place route markers. */
export function midpoint(geometry: readonly [number, number][], t: Transform): [number, number] | null {
  if (!geometry || geometry.length === 0) return null
  if (geometry.length === 1) return toScreen(geometry[0] as [number, number], t)
  const total = polylineLength(geometry)
  let walked = 0
  for (let i = 0; i < geometry.length - 1; i += 1) {
    const a = geometry[i] as [number, number]
    const b = geometry[i + 1] as [number, number]
    const segment = distance(a, b)
    if (segment === 0) continue
    if (walked + segment >= total / 2) {
      const ratio = (total / 2 - walked) / segment
      return toScreen([a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio], t)
    }
    walked += segment
  }
  return toScreen(geometry[Math.floor(geometry.length / 2)] as [number, number], t)
}

export function distance(a: readonly [number, number], b: readonly [number, number]): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1])
}

export function polylineLength(geometry: readonly [number, number][]): number {
  let total = 0
  for (let i = 0; i < geometry.length - 1; i += 1) {
    total += distance(geometry[i] as [number, number], geometry[i + 1] as [number, number])
  }
  return total
}

/** Places along a directed edge where a parallel duplicate would overlap exactly. */
export function parallelOffset(edgeIndex: number, geometry: EdgeGeometry): number {
  const dx = (geometry[geometry.length - 1]?.[0] ?? 0) - (geometry[0]?.[0] ?? 0)
  const dy = (geometry[geometry.length - 1]?.[1] ?? 0) - (geometry[0]?.[1] ?? 0)
  const length = Math.hypot(dx, dy)
  if (length < MIN_SPAN) return 0
  // Perpendicular magnitude by index so parallel edges stay visually separable.
  return ((edgeIndex % 3) - 1) * 2.5 + (edgeIndex >= 3 ? 4 : 0)
}

export function perpendicularUnit(geometry: readonly [number, number][]): [number, number] {
  const a = geometry[0] ?? [0, 0]
  const b = geometry[geometry.length - 1] ?? a
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const length = Math.hypot(dx, dy)
  if (length < MIN_SPAN) return [0, 0]
  return [-dy / length, dx / length]
}

export function crossingsToMarkers(
  crossings: readonly UnlinkedCrossing[],
  t: Transform,
): { x: number; y: number; edges: [string, string] }[] {
  return crossings.map((crossing) => {
    const [x, y] = toScreen(crossing.point, t)
    return { x, y, edges: crossing.edge_ids }
  })
}

function round(value: number): number {
  return Math.round(value * 100) / 100
}

export function clampZoom(zoom: number): number {
  return Math.min(Math.max(zoom, 0.2), 6)
}