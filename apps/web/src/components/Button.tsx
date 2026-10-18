import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './components.css'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  busy?: boolean
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  busy = false,
  icon,
  children,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`btn btn--${variant} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <span className="btn__spinner" aria-hidden="true" /> : icon}
      <span>{children}</span>
    </button>
  )
}

interface PanelProps {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  /** Removes internal padding for tables that manage their own. */
  flush?: boolean
}

export function Panel({ title, subtitle, actions, children, className = '', flush = false }: PanelProps) {
  return (
    <section className={`panel ${className}`} aria-label={title}>
      <header className="panel__header">
        <div className="panel__titles">
          <h2 className="panel__title">{title}</h2>
          {subtitle ? <p className="panel__subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      <div className={flush ? 'panel__body panel__body--flush' : 'panel__body'}>{children}</div>
    </section>
  )
}

interface EmptyStateProps {
  title: string
  description?: string
  action?: ReactNode
  icon?: string
}

export function EmptyState({ title, description, action, icon = '∅' }: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      <span className="empty-state__icon" aria-hidden="true">
        {icon}
      </span>
      <p className="empty-state__title">{title}</p>
      {description ? <p className="empty-state__description">{description}</p> : null}
      {action}
    </div>
  )
}

interface ErrorPanelProps {
  title?: string
  message: string
  code?: string
  action?: ReactNode
  details?: ReactNode
}

export function ErrorPanel({ title = 'Request failed', message, code, action, details }: ErrorPanelProps) {
  return (
    <div className="error-panel" role="alert">
      <div className="error-panel__head">
        <span className="error-panel__glyph" aria-hidden="true">
          !
        </span>
        <div>
          <p className="error-panel__title">{title}</p>
          {code ? <code className="error-panel__code">{code}</code> : null}
        </div>
      </div>
      <p className="error-panel__message">{message}</p>
      {details}
      {action ? <div className="error-panel__actions">{action}</div> : null}
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="spinner-row" role="status">
      <span className="btn__spinner" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  )
}