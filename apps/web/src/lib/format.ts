/**
 * Presentation-only formatting helpers.
 *
 * Hard rule: the browser never reinterprets a measurement. Widths stay in
 * millimetres, lengths in metres, grades keep their sign, and an unknown value
 * renders as "Unknown" - never 0, never a dash that could read as a number.
 */

export const UNKNOWN_LABEL = 'Unknown'

export function isUnknown(value: number | null | undefined): boolean {
  return value === null || value === undefined || !Number.isFinite(value)
}

/** Metres, with a fixed decimal count so tables align. */
export function formatMetres(value: number | null | undefined, decimals = 1): string {
  return isUnknown(value) ? UNKNOWN_LABEL : `${(value as number).toFixed(decimals)} m`
}

/** Integer millimetres are canonical for widths; they must never be shown as metres. */
export function formatMillimetres(value: number | null | undefined): string {
  return isUnknown(value) ? UNKNOWN_LABEL : `${Math.round(value as number)} mm`
}

export function formatMetresFromMillimetres(value: number | null | undefined): string {
  return isUnknown(value) ? UNKNOWN_LABEL : `${((value as number) / 1000).toFixed(3)} m`
}

/** Signed percent grade along the direction of travel. */
export function formatGrade(value: number | null | undefined): string {
  if (isUnknown(value)) return UNKNOWN_LABEL
  const grade = value as number
  const direction = grade > 0 ? 'rise' : grade < 0 ? 'descent' : 'level'
  return `${grade > 0 ? '+' : ''}${grade.toFixed(1)}% (${direction} along u→v)`
}

export function formatShortGrade(value: number | null | undefined): string {
  return isUnknown(value) ? UNKNOWN_LABEL : `${(value as number).toFixed(1)}%`
}

/** A raw measurement keeps its source unit so nothing is silently converted. */
export function formatObservation(value: unknown, unit: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return UNKNOWN_LABEL
  if (typeof value === 'number') {
    return unit ? `${value} ${unit}` : String(value)
  }
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return unit ? `${String(value)} ${unit}` : String(value)
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return UNKNOWN_LABEL
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z')
}

export function formatHash(hash: string | null | undefined, length = 12): string {
  if (!hash) return UNKNOWN_LABEL
  const withoutPrefix = hash.replace(/^sha256:/, '')
  return withoutPrefix.slice(0, length)
}

export function formatDuration(ms: number | null | undefined): string {
  if (isUnknown(ms)) return UNKNOWN_LABEL
  const value = ms as number
  return value < 1000 ? `${value.toFixed(1)} ms` : `${(value / 1000).toFixed(2)} s`
}

export function pluralise(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}