import type { ReactNode } from 'react'
import type { StatusMeta, Tone } from '@/lib/status'
import './components.css'

interface StatusBadgeProps {
  meta: StatusMeta
  size?: 'sm' | 'md'
  showLabel?: boolean
  /** Extra context rendered after the label, e.g. an element id. */
  detail?: string
}

export function StatusBadge({ meta, size = 'md', showLabel = true, detail }: StatusBadgeProps) {
  return (
    <span className={`badge badge--${meta.tone} badge--${size}`} title={meta.description}>
      <span className="badge__glyph" aria-hidden="true">
        {meta.glyph}
      </span>
      {showLabel ? <span className="badge__label">{meta.label}</span> : null}
      <span className="visually-hidden">. {meta.description}</span>
      {detail ? <span className="badge__detail mono">{detail}</span> : null}
    </span>
  )
}

export function ToneBadge({
  tone,
  glyph,
  children,
  title,
}: {
  tone: Tone
  glyph: string
  children: ReactNode
  title?: string
}) {
  return (
    <span className={`badge badge--${tone} badge--md`} title={title}>
      <span className="badge__glyph" aria-hidden="true">
        {glyph}
      </span>
      <span className="badge__label">{children}</span>
    </span>
  )
}

interface KeyValueProps {
  items: { term: string; value: ReactNode; wide?: boolean }[]
  columns?: 1 | 2
}

export function KeyValueList({ items, columns = 2 }: KeyValueProps) {
  return (
    <dl className={`kv kv--cols-${columns}`}>
      {items.map((item) => (
        <div key={item.term} className={item.wide ? 'kv__row kv__row--wide' : 'kv__row'}>
          <dt className="kv__term">{item.term}</dt>
          <dd className="kv__value">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}