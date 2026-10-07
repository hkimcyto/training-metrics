import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useCalendar, useDashboard, usePmc } from '../api'
import { Dot, Kpi, Panel, Q, Tip } from '../components/ui'
import type { Units } from '../lib/format'
import { distance, distanceValue, hms, pace, shortDate, signed } from '../lib/format'
import { formState } from '../lib/form'
import type { Week } from '../types'

const total = (w: Week) => w.swim_s + w.bike_s + w.run_s

export default function Overview({ units }: { units: Units }) {
  const dash = useDashboard(16)
  const pmc = usePmc(60)
  const cal = useCalendar()

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Training overview</h1>
          <p className="lede">Volume, load and consistency across swim, bike and run.</p>
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

        <Panel
          title="Consistency"
          aside={<span className="label">Daily training stress · last 12 months</span>}
          note="Each square is a day. Darker means more training stress. Rows run Monday to Sunday."
        >
          <Q q={cal} height={110}>
            {(days) => {
              const max = Math.max(...days.map((d) => d.tss), 1)
              const first = new Date(days[0].day + 'T12:00:00')
              const pad = (first.getDay() + 6) % 7
              const active = days.filter((d) => d.tss > 0).length
              return (
                <>
                  <div className="cal" role="img" aria-label={`${active} training days in the last year`}>
                    {Array.from({ length: pad }, (_, i) => (
                      <i key={`p${i}`} style={{ visibility: 'hidden' }} />
                    ))}
                    {days.map((d) => (
                      <i
                        key={d.day}
                        title={`${shortDate(d.day)}: ${Math.round(d.tss)} TSS`}
                        style={
                          d.tss > 0
                            ? {
                                background: `color-mix(in srgb, var(--accent) ${20 + Math.min(80, (d.tss / max) * 100)}%, var(--grid))`,
                              }
                            : undefined
                        }
                      />
                    ))}
                  </div>
                  <p className="note">
                    {active} training days in the last 365 · longest streak{' '}
                    {
                      days.reduce(
                        (acc, d) => {
                          const cur = d.tss > 0 ? acc.cur + 1 : 0
                          return { cur, best: Math.max(acc.best, cur) }
                        },
                        { cur: 0, best: 0 },
                      ).best
                    }{' '}
                    days
                  </p>
                </>
              )
            }}
          </Q>
        </Panel>
      </div>
    </>
  )
}
