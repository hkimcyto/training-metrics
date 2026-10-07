import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { SPORT_COLOR } from '../lib/form'

export function Dot({ sport, color }: { sport?: string; color?: string }) {
  return <i className="dot" style={{ background: color ?? SPORT_COLOR[sport ?? 'other'] }} />
}

export function Panel({
  title,
  aside,
  children,
  className = 'span-12',
  note,
}: {
  title?: ReactNode
  aside?: ReactNode
  children: ReactNode
  className?: string
  note?: ReactNode
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || aside) && (
        <div className="panel-head">
          {title && <h2>{title}</h2>}
          {aside}
        </div>
      )}
      {children}
      {note && <p className="note">{note}</p>}
    </section>
  )
}

export function Kpi({
  label,
  value,
  unit,
  detail,
}: {
  label: ReactNode
  value: ReactNode
  unit?: string
  detail?: ReactNode
}) {
  return (
    <div className="panel kpi">
      <div className="label">{label}</div>
      <div className="v">
        {value}
        {unit && <small>{unit}</small>}
      </div>
      {detail && <div className="d">{detail}</div>}
    </div>
  )
}

/** Render a query's loading and error states consistently, then the content. */
export function Q<T>({
  q,
  children,
  height = 240,
}: {
  q: UseQueryResult<T>
  children: (d: T) => ReactNode
  height?: number
}) {
  if (q.isPending) return <div className="skeleton" style={{ height }} aria-label="Loading" />
  if (q.isError) return <p className="error">Couldn't load this: {q.error.message}</p>
  return <>{children(q.data)}</>
}

export function Tip({ title, rows }: { title: ReactNode; rows: [ReactNode, ReactNode, string?][] }) {
  return (
    <div className="tip">
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
      {rows.map(([k, v, c], i) => (
        <div className="row" key={i}>
          <span>
            {c && <Dot color={c} />}
            {k}
          </span>
          <span>{v}</span>
        </div>
      ))}
    </div>
  )
}

export function Seg<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: [T, string][]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, l]) => (
        <button key={String(v)} aria-pressed={v === value} onClick={() => onChange(v)}>
          {l}
        </button>
      ))}
    </div>
  )
}
