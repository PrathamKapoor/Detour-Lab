import { useEffect, useId, useRef, type ReactNode } from 'react'
import './components.css'

interface DialogProps {
  open: boolean
  title: string
  description?: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  /** Disables backdrop/escape dismissal for destructive confirmations. */
  dismissible?: boolean
}

/**
 * Accessible modal dialog: focus is moved in on open, trapped while open and
 * restored to the trigger on close; Escape and backdrop clicks dismiss unless
 * the caller marks the dialog as non-dismissible.
 */
export function Dialog({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  dismissible = true,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    if (!open) return
    previouslyFocused.current = document.activeElement as HTMLElement | null
    const node = panelRef.current
    const focusable = node?.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    )
    ;(focusable ?? node)?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && dismissible) {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !node) return
      const items = Array.from(
        node.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.offsetParent !== null || element === document.activeElement)
      if (items.length === 0) return
      const first = items[0] as HTMLElement
      const last = items[items.length - 1] as HTMLElement
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previouslyFocused.current?.focus()
    }
  }, [open, dismissible, onClose])

  if (!open) return null

  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (dismissible && event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        ref={panelRef}
        tabIndex={-1}
      >
        <header className="dialog__header">
          <h2 id={titleId} className="dialog__title">
            {title}
          </h2>
          <button type="button" className="dialog__close" onClick={onClose} aria-label="Close dialog">
            ✕
          </button>
        </header>
        <div className="dialog__body">
          {description ? (
            <p id={descriptionId} className="dialog__description">
              {description}
            </p>
          ) : null}
          {children}
        </div>
        {footer ? <footer className="dialog__footer">{footer}</footer> : null}
      </div>
    </div>
  )
}

interface TabsProps {
  tabs: { id: string; label: string; badge?: ReactNode }[]
  active: string
  onChange: (id: string) => void
  label: string
}

/** Roving-tabindex tab list with arrow-key navigation (WAI-ARIA pattern). */
export function Tabs({ tabs, active, onChange, label }: TabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    let next: number | null = null
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
    if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = tabs.length - 1
    if (next === null) return
    event.preventDefault()
    const tab = tabs[next]
    if (!tab) return
    onChange(tab.id)
    refs.current[next]?.focus()
  }

  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          ref={(element) => {
            refs.current[index] = element
          }}
          type="button"
          role="tab"
          id={`tab-${tab.id}`}
          aria-selected={tab.id === active}
          aria-controls={`tabpanel-${tab.id}`}
          tabIndex={tab.id === active ? 0 : -1}
          className={`tabs__tab ${tab.id === active ? 'tabs__tab--active' : ''}`}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => onKeyDown(event, index)}
        >
          <span>{tab.label}</span>
          {tab.badge != null ? <span className="tabs__badge">{tab.badge}</span> : null}
        </button>
      ))}
    </div>
  )
}

export function TabPanel({ id, active, children }: { id: string; active: string; children: ReactNode }) {
  if (id !== active) return null
  return (
    <div role="tabpanel" id={`tabpanel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={0} className="tabpanel">
      {children}
    </div>
  )
}