import { useId, type ChangeEvent, type ReactNode, type SelectHTMLAttributes } from 'react'
import './components.css'

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  hint?: ReactNode
  error?: string
}

export function SelectField({ label, hint, error, children, ...rest }: SelectFieldProps) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className={`field__control ${error ? 'field__control--error' : ''}`}
        aria-describedby={[hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined}
        aria-invalid={error ? true : undefined}
        {...rest}
      >
        {children}
      </select>
      {hint ? (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="field__error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

interface TextFieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: ReactNode | undefined
  error?: string | undefined
  placeholder?: string | undefined
  disabled?: boolean | undefined
  inputMode?: 'text' | 'numeric' | 'decimal'
}

export function TextField({
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
  disabled,
  inputMode = 'text',
}: TextFieldProps) {
  const id = useId()
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className={`field__control ${error ? 'field__control--error' : ''}`}
        type="text"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        inputMode={inputMode}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
        aria-describedby={hint || error ? `${id}-desc` : undefined}
        aria-invalid={error ? true : undefined}
      />
      {hint || error ? (
        <p className={error ? 'field__error' : 'field__hint'} id={`${id}-desc`} role={error ? 'alert' : undefined}>
          {error ?? hint}
        </p>
      ) : null}
    </div>
  )
}

export function SearchField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  const id = useId()
  return (
    <div className="field field--inline">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type="search"
        className="field__control"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}