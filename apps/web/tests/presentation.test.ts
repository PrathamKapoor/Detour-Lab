import { describe, expect, it } from 'vitest'
import {
  formatGrade,
  formatHash,
  formatMetres,
  formatMillimetres,
  formatObservation,
  formatShortGrade,
  formatTimestamp,
  isUnknown,
  pluralise,
} from '@/lib/format'
import { EDGE_ROLE_META, REACHABILITY_META, evidenceProblemMeta, reachabilityOf, verdictMeta } from '@/lib/status'

describe('measurement formatting', () => {
  it('never turns an unknown into zero', () => {
    expect(isUnknown(null)).toBe(true)
    expect(isUnknown(undefined)).toBe(true)
    expect(isUnknown(Number.NaN)).toBe(true)
    expect(isUnknown(0)).toBe(false)
    expect(formatMetres(null)).toBe('Unknown')
    expect(formatMetres(undefined)).toBe('Unknown')
    expect(formatMillimetres(null)).toBe('Unknown')
    expect(formatMetres(0)).toBe('0.0 m')
  })

  it('keeps millimetres as millimetres', () => {
    expect(formatMillimetres(1200)).toBe('1200 mm')
    expect(formatMillimetres(900.4)).toBe('900 mm')
  })

  it('preserves the sign and direction of a grade', () => {
    expect(formatGrade(5)).toBe('+5.0% (rise along u→v)')
    expect(formatGrade(-3.25)).toBe('-3.3% (descent along u→v)')
    expect(formatGrade(0)).toBe('0.0% (level along u→v)')
    expect(formatShortGrade(-3.25)).toBe('-3.3%')
    expect(formatGrade(null)).toBe('Unknown')
  })

  it('keeps the source unit of a raw observation', () => {
    expect(formatObservation(150, 'cm')).toBe('150 cm')
    expect(formatObservation('asphalt', null)).toBe('asphalt')
    expect(formatObservation(null, 'mm')).toBe('Unknown')
    expect(formatObservation(true, null)).toBe('yes')
  })

  it('renders timestamps in UTC and marks unknown times', () => {
    expect(formatTimestamp('2026-03-01T09:00:00Z')).toBe('2026-03-01 09:00:00Z')
    expect(formatTimestamp(null)).toBe('Unknown')
    expect(formatTimestamp('not-a-date')).toBe('not-a-date')
  })

  it('shortens hashes without losing the prefix meaning', () => {
    expect(formatHash('sha256:abcdef0123456789', 8)).toBe('abcdef01')
    expect(formatHash(null)).toBe('Unknown')
  })

  it('pluralises counts', () => {
    expect(pluralise(1, 'finding')).toBe('1 finding')
    expect(pluralise(3, 'finding')).toBe('3 findings')
  })
})

describe('verdict presentation', () => {
  it('keeps the four states distinct in label, glyph and tone', () => {
    const states = ['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE'] as const
    const metas = states.map((state) => verdictMeta(state))
    expect(new Set(metas.map((m) => m.label)).size).toBe(4)
    expect(new Set(metas.map((m) => m.glyph)).size).toBe(4)
    expect(metas.map((m) => m.tone)).toEqual(['pass', 'fail', 'unknown', 'neutral'])
  })

  it('never describes a pass as a certification', () => {
    const description = verdictMeta('PASS').description.toLowerCase()
    expect(description).toContain('not a certification')
    expect(description).not.toContain('compliant')
    expect(description).not.toContain('approved')
  })

  it('states that Unknown is not a confirmed route', () => {
    expect(verdictMeta('UNKNOWN').description.toLowerCase()).toContain('never reported as passing')
  })

  it('explains that Not applicable cannot clear missing evidence', () => {
    expect(verdictMeta('NOT_APPLICABLE').description.toLowerCase()).toContain('never used to clear')
  })
})

describe('evidence problem presentation', () => {
  const codes = [
    'NO_EVIDENCE',
    'CONFLICTING_EVIDENCE',
    'UNSUPPORTED_UNIT',
    'EVIDENCE_EXPIRED',
    'EVIDENCE_NOT_VERIFIED',
  ] as const

  it('gives each condition its own label, glyph and action', () => {
    const metas = codes.map((code) => evidenceProblemMeta(code))
    expect(new Set(metas.map((m) => m.label)).size).toBe(codes.length)
    expect(new Set(metas.map((m) => m.glyph)).size).toBe(codes.length)
    for (const meta of metas) {
      expect(meta.action.length).toBeGreaterThan(10)
    }
  })

  it('does not collapse an unknown reason code into a generic label', () => {
    const meta = evidenceProblemMeta('SOME_FUTURE_CODE')
    expect(meta.label).toBe('some future code')
  })

  it('falls back safely for a missing reason code', () => {
    expect(evidenceProblemMeta(null).label).toBe('Unresolved')
  })
})

describe('reachability presentation', () => {
  it('maps confirmed/possible pairs to distinct states', () => {
    expect(reachabilityOf(true, true)).toBe('confirmed')
    expect(reachabilityOf(false, true)).toBe('possible')
    expect(reachabilityOf(false, false)).toBe('none')
  })

  it('never describes a possible-only route as confirmed', () => {
    expect(REACHABILITY_META.possible.label).toBe('Possible only')
    expect(REACHABILITY_META.possible.description.toLowerCase()).toContain('not confirmed')
  })

  it('gives edge roles distinct glyphs', () => {
    const glyphs = Object.values(EDGE_ROLE_META).map((meta) => meta.glyph)
    expect(new Set(glyphs).size).toBe(glyphs.length)
  })
})