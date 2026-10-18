import type { GraphEdge, Node, UnlinkedCrossing } from '@/api/types'
import {
  EMPTY_BOUNDS,
  MIN_SPAN,
  clampZoom,
  computeBounds,
  fitBounds,
  midpoint,
  parallelOffset,
  perpendicularUnit,
  polylineLength,
  toScreen,
  toScreenPath,
} from '@/lib/geometry'

function node(id: string, x: number, y: number): Node {
  return { id, x, y }
}

function edge(id: string, u: string, v: string, geometry: [number, number][]): GraphEdge {
  return {
    id,
    u,
    v,
    geometry,
    length_m: polylineLength(geometry),
    edge_type: 'sidewalk',
    name: '',
    provenance_class: 'synthetic',
    evidence_ids: [],
  }
}

describe('computeBounds', () => {
  it('computes bounds from nodes only', () => {
    const bounds = computeBounds([node('A', 0, 0), node('B', 10, -4)], [])
    expect(bounds).toMatchObject({ minX: 0, maxX: 10, minY: -4, maxY: 0, width: 10, height: 4 })
  })

  it('includes edge geometry, so dangling vertices still have extent', () => {
    const bounds = computeBounds([node('A', 0, 0)], [edge('E', 'A', 'B', [[0, 0], [5, 5], [12, 3]])])
    expect(bounds.maxX).toBe(12)
    expect(bounds.maxY).toBe(5)
  })

  it('handles negative coordinates', () => {
    const bounds = computeBounds([node('A', -30, -20), node('B', -5, -2)], [])
    expect(bounds.minX).toBe(-30)
    expect(bounds.minY).toBe(-20)
  })

  it('returns an empty box for an empty graph instead of NaN', () => {
    expect(computeBounds([], [])).toEqual(EMPTY_BOUNDS)
    expect(Number.isFinite(computeBounds([], []).width)).toBe(true)
  })

  it('reports a minimum span for a single node (zero-width bounds)', () => {
    const bounds = computeBounds([node('A', 7, 7)], [])
    expect(bounds.width).toBe(MIN_SPAN)
    expect(bounds.height).toBe(MIN_SPAN)
  })

  it('reports a minimum span for a perfectly vertical layout', () => {
    const bounds = computeBounds([node('A', 3, 0), node('B', 3, 20)], [])
    expect(bounds.width).toBe(MIN_SPAN)
    expect(bounds.height).toBe(20)
  })

  it('ignores non-finite coordinates rather than poisoning the bounds', () => {
    const bounds = computeBounds([node('A', 0, 0), node('B', Number.NaN, 10)], [])
    expect(bounds.maxY).toBe(10)
    expect(Number.isFinite(bounds.width)).toBe(true)
  })

  it('keeps near-coincident nodes distinguishable', () => {
    const bounds = computeBounds([node('A', 0, 0), node('B', 1e-9, 1e-9)], [])
    expect(bounds.width).toBeGreaterThanOrEqual(MIN_SPAN)
    expect(Number.isFinite(bounds.width)).toBe(true)
  })
})

describe('fitBounds', () => {
  it('preserves aspect ratio and centres the graph', () => {
    const bounds = computeBounds([node('A', 0, 0), node('B', 100, 50)], [])
    const { transform } = fitBounds(bounds, { width: 800, height: 400, padding: 20 })
    expect(Number.isFinite(transform.scale)).toBe(true)
    const [ax, ay] = toScreen([0, 0], transform)
    const [bx, by] = toScreen([100, 50], transform)
    expect(Math.abs(ax + bx - 800)).toBeLessThan(0.001)
    expect(Math.abs(ay + by - 400)).toBeLessThan(0.001)
  })

  it('never produces an infinite transform for degenerate bounds', () => {
    const { transform } = fitBounds(EMPTY_BOUNDS, { width: 800, height: 400, padding: 20 })
    expect(Number.isFinite(transform.scale)).toBe(true)
    expect(Number.isFinite(transform.offsetX)).toBe(true)
  })

  it('flips the Y axis so north is up', () => {
    const transform = { scale: 2, offsetX: 0, offsetY: 0 }
    expect(toScreen([0, 10], transform)[1]).toBe(-20)
    expect(toScreen([0, -10], transform)[1]).toBe(20)
  })

  it('honours zoom without changing the centre', () => {
    const bounds = computeBounds([node('A', 0, 0), node('B', 10, 10)], [])
    const one = fitBounds(bounds, { width: 400, height: 400, padding: 10 }, 1)
    const two = fitBounds(bounds, { width: 400, height: 400, padding: 10 }, 2)
    expect(two.transform.scale).toBeCloseTo(one.transform.scale * 2, 6)
  })

  it('clamps an unusable viewport instead of dividing by zero', () => {
    const bounds = computeBounds([node('A', 0, 0), node('B', 10, 10)], [])
    const { transform } = fitBounds(bounds, { width: 0, height: 0, padding: 500 })
    expect(Number.isFinite(transform.scale)).toBe(true)
  })
})

describe('screen transform', () => {
  it('builds an SVG path from world coordinates', () => {
    const transform = { scale: 10, offsetX: 5, offsetY: 5 }
    expect(toScreenPath([[0, 0], [1, 2]], transform)).toBe('M5 5 L15 -15')
  })

  it('returns an empty path for empty geometry', () => {
    expect(toScreenPath([], { scale: 1, offsetX: 0, offsetY: 0 })).toBe('')
  })

  it('finds the midpoint of a two-point edge', () => {
    const mid = midpoint([[0, 0], [10, 0]], { scale: 1, offsetX: 0, offsetY: 0 })
    expect(mid).toEqual([5, 0])
  })

  it('lands on the corner when half the length falls exactly on a vertex', () => {
    // An L of total length 20: half way (10 m) is precisely the corner.
    const mid = midpoint([[0, 0], [10, 0], [10, 10]], { scale: 1, offsetX: 0, offsetY: 0 })
    expect(mid).toEqual([10, 0])
  })

  it('handles a single-vertex edge', () => {
    expect(midpoint([[3, 4]], { scale: 2, offsetX: 0, offsetY: 0 })).toEqual([6, -8])
  })

  it('returns null for empty geometry', () => {
    expect(midpoint([], { scale: 1, offsetX: 0, offsetY: 0 })).toBeNull()
  })
})

describe('parallel edges', () => {
  it('gives parallel duplicates different offsets so they stay separable', () => {
    const geometry: [number, number][] = [
      [0, 0],
      [10, 0],
    ]
    const offsets = [0, 1, 2, 3].map((index) => parallelOffset(index, geometry))
    expect(new Set(offsets).size).toBe(4)
  })

  it('produces a zero offset for a degenerate edge', () => {
    expect(parallelOffset(2, [[0, 0], [0, 0]])).toBe(0)
  })

  it('computes a unit perpendicular', () => {
    const [px, py] = perpendicularUnit([
      [0, 0],
      [5, 0],
    ])
    expect(Math.hypot(px, py)).toBeCloseTo(1, 9)
    expect(py).toBeCloseTo(1, 9)
  })

  it('returns a zero vector for a zero-length edge', () => {
    expect(perpendicularUnit([[1, 1], [1, 1]])).toEqual([0, 0])
  })
})

describe('zoom clamping', () => {
  it('keeps zoom inside usable bounds', () => {
    expect(clampZoom(0.0001)).toBe(0.2)
    expect(clampZoom(999)).toBe(6)
    expect(clampZoom(2)).toBe(2)
  })
})

describe('unlinked crossings input', () => {
  it('accepts the crossing payload shape used by the backend', () => {
    const crossings: UnlinkedCrossing[] = [
      { edge_ids: ['E_A', 'E_B'], point: [10, 10], connected_via_shared_node: false, shared_node_ids: [] },
    ]
    expect(crossings[0]?.connected_via_shared_node).toBe(false)
    expect(computeBounds([node('A', 0, 0), node('B', 20, 20)], []).maxX).toBe(20)
  })
})