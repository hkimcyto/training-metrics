import type { ReactNode } from 'react'
import type { Units } from '../lib/format'
import { distance, hms, pace, weekday } from '../lib/format'
import { decodePolyline } from '../lib/polyline'
import type { EfficiencyPoint } from '../types'
import { Dot } from './ui'

/** A small outline of the route, drawn straight from the polyline (no map tiles). */
export function RouteSketch({ polyline, color, size = 116 }: { polyline: string; color: string; size?: number }) {
  const pts = decodePolyline(polyline)
  if (pts.length < 2) return null
  const midLat = (pts.reduce((s, [la]) => s + la, 0) / pts.length) * (Math.PI / 180)
  const xy = pts.map(([la, lo]) => [lo * Math.cos(midLat), -la] as const)
  const xs = xy.map((p) => p[0])
  const ys = xy.map((p) => p[1])
  const [x0, y0] = [Math.min(...xs), Math.min(...ys)]
  const span = Math.max(Math.max(...xs) - x0, Math.max(...ys) - y0) || 1
  const pad = 6
  const k = (size - pad * 2) / span
  const d = xy.map(
    ([x, y], i) => `${i ? 'L' : 'M'}${(pad + (x - x0) * k).toFixed(1)},${(pad + (y - y0) * k).toFixed(1)}`,
  )
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-label="Route outline" style={{ flex: 'none' }}>
      <rect width={size} height={size} rx={6} fill="var(--grid)" />
      <path d={d.join('')} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function driftVerdict(pct: number): [string, string] {
  if (pct < 5) return ['steady', 'var(--good)']
  if (pct < 10) return ['some drift', 'var(--warn)']
  return ['fading', 'var(--bad)']
}

/** Everything stored about one workout, sized to sit in a chart tooltip. */
export function WorkoutCard({ a, units, efficiency }: { a: EfficiencyPoint; units: Units; efficiency?: ReactNode }) {
  const color = `var(--${a.sport})`
  const rows: [string, ReactNode][] = [
    ['Time', `${hms(a.moving_s, true)}`],
    ['Distance', a.distance_m ? distance(a.distance_m, a.sport, units) : '—'],
    [a.sport === 'run' ? 'Avg pace' : 'Avg speed', pace(a.avg_speed, a.sport, units)],
  ]
  if (a.elev_gain_m > 0)
    rows.push([
      'Climbing',
      units === 'imperial' ? `${Math.round(a.elev_gain_m * 3.281)} ft` : `${Math.round(a.elev_gain_m)} m`,
    ])
  if (a.avg_hr)
    rows.push(['Heart rate', `${Math.round(a.avg_hr)} avg${a.max_hr ? ` · ${Math.round(a.max_hr)} max` : ''} bpm`])
  if (a.np_watts || a.avg_watts)
    rows.push([
      'Power',
      [
        a.avg_watts && `${Math.round(a.avg_watts)} W avg`,
        a.np_watts && a.np_watts !== a.avg_watts && `${Math.round(a.np_watts)} W NP`,
      ]
        .filter(Boolean)
        .join(' · '),
    ])
  rows.push(['Training load', `${Math.round(a.tss)} TSS${a.intensity ? ` · IF ${a.intensity.toFixed(2)}` : ''}`])
  if (efficiency) rows.push(['Efficiency', efficiency])
  if (a.decoupling != null) {
    const [v, c] = driftVerdict(a.decoupling)
    rows.push([
      'HR drift',
      <span key="d">
        {a.decoupling.toFixed(1)}% <span style={{ color: c }}>{v}</span>
      </span>,
    ])
  }

  return (
    <div className="tip" style={{ maxWidth: 460 }}>
      <div style={{ fontWeight: 600 }}>
        <Dot color={color} />
        {a.name}
      </div>
      <div className="mono" style={{ color: 'var(--muted)', fontSize: '.72rem', margin: '2px 0 8px' }}>
        {weekday(a.day)} · {a.sport_type.replace(/([a-z])([A-Z])/g, '$1 $2')}
        {a.trainer ? ' · indoor' : ''}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        {a.polyline && !a.trainer && <RouteSketch polyline={a.polyline} color={color} />}
        <div style={{ display: 'grid', gap: 2, minWidth: 250, flex: 1, whiteSpace: 'nowrap' }}>
          {rows.map(([k, v]) => (
            <div className="row" key={k}>
              <span style={{ color: 'var(--muted)' }}>{k}</span>
              <span>{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
