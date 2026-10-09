import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useDashboard, usePmc, useTrainingStatus } from '../api'
import { Dot, Kpi, Panel, Q, Tip } from '../components/ui'
import type { Units } from '../lib/format'
import { distance, distanceValue, hms, pace, shortDate, signed } from '../lib/format'
import { formState } from '../lib/form'
import { HRV_STATUS, LOAD_STATUS, statusOf } from '../lib/status'
import type { TrainingStatus, Week } from '../types'

const total = (w: Week) => w.swim_s + w.bike_s + w.run_s

export default function Overview({ units }: { units: Units }) {
  const dash = useDashboard(16)
  const pmc = usePmc(60)

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Training overview</h1>
          <p className="lede">Volume, load and training status across swim, bike and run.</p>
        </div>
      </div>

      <Q q={dash} height={110}>
        {(d) => {
          const weeks = d.weeks
          const last = weeks[weeks.length - 2]
          const prev = weeks[weeks.length - 3]
          const delta = (total(last) - total(prev)) / 3600
          const now = pmc.data?.series.at(-1)
          const [state, color] = now ? formState(now.tsb) : ['—', 'var(--muted)']
          return (
            <div className="kpis">
              <Kpi
                label={`Last week · ${shortDate(last.week)}`}
                value={hms(total(last))}
                unit="h"
                detail={
                  <>
                    <span className={delta >= 0 ? 'up' : 'down'}>
                      {delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}h
                    </span>{' '}
                    vs prior · {Math.round(last.tss)} TSS
                  </>
                }
              />
              {(['swim', 'bike', 'run'] as const).map((s) => {
                const dv = distanceValue(last[`${s}_m`], s, units)
                return (
                  <Kpi
                    key={s}
                    label={
                      <>
                        <Dot sport={s} />
                        {s}
                      </>
                    }
                    value={dv.value}
                    unit={dv.unit}
                    detail={`${hms(last[`${s}_s`])} h`}
                  />
                )
              })}
              <Kpi
                label="Form today"
                value={now ? signed(now.tsb) : '—'}
                detail={
                  <>
                    <span className="pill" style={{ color }}>
                      {state}
                    </span>{' '}
                    fitness {now ? Math.round(now.ctl) : '—'}
                  </>
                }
              />
            </div>
          )
        }}
      </Q>

      <div className="grid">
        <Panel
          className="span-8"
          title="Weekly volume"
          aside={
            <div className="legend">
              {(['swim', 'bike', 'run'] as const).map((s) => (
                <span key={s}>
                  <Dot sport={s} />
                  {s[0].toUpperCase() + s.slice(1)}
                </span>
              ))}
            </div>
          }
          note="Moving time. The last bar is the current week so far."
        >
          <Q q={dash} height={280}>
            {(d) => (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={d.weeks.map((w) => ({
                    ...w,
                    swim: w.swim_s / 3600,
                    bike: w.bike_s / 3600,
                    run: w.run_s / 3600,
                  }))}
                >
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="week" tickFormatter={shortDate} tickLine={false} axisLine={false} interval={1} />
                  <YAxis tickFormatter={(v) => `${v}h`} tickLine={false} axisLine={false} width={36} />
                  <Tooltip
                    cursor={{ fill: 'var(--grid)', opacity: 0.6 }}
                    content={({ payload }) => {
                      const w = payload?.[0]?.payload as Week | undefined
                      if (!w) return null
                      return (
                        <Tip
                          title={`Week of ${shortDate(w.week)}`}
                          rows={[
                            ['Swim', `${hms(w.swim_s)} · ${distance(w.swim_m, 'swim', units)}`, 'var(--swim)'],
                            ['Bike', `${hms(w.bike_s)} · ${distance(w.bike_m, 'bike', units)}`, 'var(--bike)'],
                            ['Run', `${hms(w.run_s)} · ${distance(w.run_m, 'run', units)}`, 'var(--run)'],
                            ['Total', `${hms(total(w))} · ${Math.round(w.tss)} TSS`],
                          ]}
                        />
                      )
                    }}
                  />
                  <Bar dataKey="swim" stackId="v" fill="var(--swim)" />
                  <Bar dataKey="bike" stackId="v" fill="var(--bike)" />
                  <Bar dataKey="run" stackId="v" fill="var(--run)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Q>
        </Panel>

        <Panel className="span-4" title="Longest sessions" note="Last 12 weeks.">
          <Q q={dash} height={280}>
            {(d) => (
              <div style={{ display: 'grid', gap: 16 }}>
                {(['bike', 'run', 'swim'] as const).map((s) => {
                  const a = d.records[s]
                  if (!a) return null
                  return (
                    <div key={s} className="leg" style={{ borderLeftColor: `var(--${s})` }}>
                      <div className="label">Longest {s === 'bike' ? 'ride' : s}</div>
                      <div className="t">{distance(a.distance_m, s, units)}</div>
                      <div className="r">
                        {shortDate(a.day)} · {hms(a.moving_s)} h · {pace(a.avg_speed, s, units)}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Q>
        </Panel>

        <TrainingStatusPanel />
      </div>
    </>
  )
}

const TREND: Record<string, [string, string]> = {
  INCREASING: ['▲ Fitness rising', 'var(--good)'],
  DECREASING: ['▼ Fitness falling', 'var(--bad)'],
  STABLE: ['● Fitness steady', 'var(--muted)'],
}

function Factor({
  label,
  value,
  detail,
  pill,
}: {
  label: string
  value: string
  detail: string
  pill?: [string, string]
}) {
  return (
    <div className="leg" style={{ borderLeftColor: pill?.[1] ?? 'var(--line)' }}>
      <div className="label">{label}</div>
      <div className="t">
        {value}{' '}
        {pill && (
          <span className="pill" style={{ color: pill[1], verticalAlign: 'middle' }}>
            {pill[0]}
          </span>
        )}
      </div>
      <div className="r">{detail}</div>
    </div>
  )
}

function factors(t: TrainingStatus) {
  const out: { label: string; value: string; detail: string; pill?: [string, string] }[] = []
  if (t.vo2max) {
    const c = t.vo2max.change_28d
    out.push({
      label: 'VO2 max',
      value: t.vo2max.value.toFixed(0),
      detail: c == null ? 'ml/kg/min' : `${signed(c, 0)} over 4 weeks`,
    })
  } else if (t.fitness) {
    out.push({
      label: 'Fitness (CTL)',
      value: t.fitness.ctl.toFixed(0),
      detail: `${signed(t.fitness.change_28d, 0)} over 4 weeks`,
    })
  }
  if (t.load) {
    const l = t.load
    out.push({
      label: l.units === 'garmin' ? '7-day load' : 'Fatigue (ATL)',
      value: Math.round(l.acute).toLocaleString(),
      detail:
        l.chronic != null
          ? `vs ${Math.round(l.chronic).toLocaleString()} usual${l.ratio != null ? ` · ratio ${l.ratio.toFixed(2)}` : ''}`
          : '',
      pill: l.status ? LOAD_STATUS[l.status] : undefined,
    })
  }
  if (t.hrv) {
    out.push({
      label: 'HRV · 7-night avg',
      value: `${Math.round(t.hrv.weekly_avg)} ms`,
      detail: `normal range ${Math.round(t.hrv.low)}–${Math.round(t.hrv.high)} ms`,
      pill: HRV_STATUS[t.hrv.status],
    })
  }
  if (t.readiness != null) {
    out.push({ label: 'Readiness', value: String(Math.round(t.readiness)), detail: 'Garmin, this morning' })
  }
  return out
}

function TrainingStatusPanel() {
  const ts = useTrainingStatus()
  return (
    <Panel
      title="Training status"
      aside={
        ts.data && (
          <span className="label">
            {ts.data.source === 'garmin' ? 'From Garmin' : 'Estimated from your training'}
            {ts.data.as_of && ` · ${shortDate(ts.data.as_of)}`}
          </span>
        )
      }
      note={
        ts.data?.source === 'garmin'
          ? 'Garmin weighs your VO2 max trend, recent load against your usual load, and HRV.'
          : "Estimated the way Garmin does it, from your fitness trend, recent load against your usual load, and HRV when Garmin data is imported. Import a Garmin export on the Recovery page to use Garmin's own status."
      }
    >
      <Q q={ts} height={200}>
        {(t) => {
          const s = statusOf(t.status)
          const trend = t.fitness_trend ? TREND[t.fitness_trend] : undefined
          const seen = [...new Set(t.timeline.map((d) => d.status).filter(Boolean))] as string[]
          return (
            <div style={{ display: 'grid', gap: 18 }}>
              <div className="grid" style={{ alignItems: 'start' }}>
                <div className="span-4">
                  <div className="finish" style={{ color: s.color }}>
                    {s.label}
                  </div>
                  {trend && (
                    <div className="mono" style={{ color: trend[1], fontSize: '.8rem', margin: '4px 0 8px' }}>
                      {trend[0]}
                    </div>
                  )}
                  <p style={{ margin: 0 }}>{s.meaning}</p>
                </div>
                <div className="span-8 legs">
                  {factors(t).map((f) => (
                    <Factor key={f.label} {...f} />
                  ))}
                </div>
              </div>

              {t.timeline.length > 0 && (
                <div>
                  <div className="label" style={{ marginBottom: 6 }}>
                    Last 12 weeks
                  </div>
                  <div
                    role="img"
                    aria-label="Training status by day over the last 12 weeks"
                    style={{ display: 'flex', gap: 2, height: 22 }}
                  >
                    {t.timeline.map((d) => {
                      const x = d.status ? statusOf(d.status) : null
                      return (
                        <span
                          key={d.day}
                          title={`${shortDate(d.day)}: ${x?.label ?? 'no data'}`}
                          style={{ flex: 1, borderRadius: 2, background: x?.color ?? 'var(--grid)' }}
                        />
                      )
                    })}
                  </div>
                  <div
                    className="mono"
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '.7rem',
                      color: 'var(--muted)',
                      marginTop: 4,
                    }}
                  >
                    <span>{shortDate(t.timeline[0].day)}</span>
                    <span>{shortDate(t.timeline.at(-1)!.day)}</span>
                  </div>
                  <div className="legend" style={{ marginTop: 8 }}>
                    {seen.map((k) => (
                      <span key={k}>
                        <Dot color={statusOf(k).color} />
                        {statusOf(k).label}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        }}
      </Q>
    </Panel>
  )
}
