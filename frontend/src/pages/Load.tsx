import { useState } from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { usePmc } from '../api'
import { Dot, Kpi, Panel, Q, Seg, Tip } from '../components/ui'
import { shortDate, signed } from '../lib/format'
import type { Pmc } from '../types'
import { formState } from '../lib/form'

type Row = { day: string; ctl: number; atl: number; tsb: number; tss: number; future?: boolean }

function rows(p: Pmc): Row[] {
  const hist: Row[] = p.series.map((d) => ({ ...d }))
  const fut: Row[] = (p.forecast?.days ?? []).map((d) => ({ ...d, future: true }))
  // split each line into a solid history series and a dashed forecast series
  return [...hist, ...fut].map((r, i) => ({
    ...r,
    ctlH: r.future ? undefined : r.ctl,
    atlH: r.future ? undefined : r.atl,
    tsbH: r.future ? undefined : r.tsb,
    ctlF: r.future || i === hist.length - 1 ? r.ctl : undefined,
    atlF: r.future || i === hist.length - 1 ? r.atl : undefined,
    tsbF: r.future || i === hist.length - 1 ? r.tsb : undefined,
  }))
}

export default function Load() {
  const [days, setDays] = useState(150)
  const pmc = usePmc(days)

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Training load & taper</h1>
          <p className="lede">
            Fitness is the 42-day average of training stress, fatigue the 7-day average, and form is the gap between
            them. The forecast runs the optimal taper forward to race day.
          </p>
        </div>
        <Seg
          label="Range"
          value={days}
          onChange={setDays}
          options={[
            [90, '3 mo'],
            [150, '5 mo'],
            [365, '1 yr'],
          ]}
        />
      </div>

      <Q q={pmc} height={110}>
        {(p) => {
          const now = p.series.at(-1)!
          const fc = p.forecast
          const [state, color] = formState(now.tsb)
          return (
            <div className="kpis">
              <Kpi label="Fitness (CTL)" value={Math.round(now.ctl)} detail={`${signed(now.ramp ?? 0, 1)} this week`} />
              <Kpi label="Fatigue (ATL)" value={Math.round(now.atl)} detail="7-day load" />
              <Kpi
                label="Form (TSB)"
                value={signed(now.tsb)}
                detail={
                  <span className="pill" style={{ color }}>
                    {state}
                  </span>
                }
              />
              <Kpi
                label="Acute : chronic"
                value={p.acwr ? p.acwr.toFixed(2) : '—'}
                detail={
                  p.acwr && p.acwr > 1.5 ? (
                    <span className="down">Above 1.5: injury risk zone</span>
                  ) : (
                    'Under 1.5 is the safer zone'
                  )
                }
              />
              {fc && (
                <Kpi
                  label={`Race-day form · ${shortDate(fc.race_date)}`}
                  value={signed(fc.race_day.tsb)}
                  detail={`fitness ${Math.round(fc.race_day.ctl)} after taper`}
                />
              )}
            </div>
          )
        }}
      </Q>

      <Panel
        title="Fitness, fatigue & form"
        aside={
          <div className="legend">
            <span>
              <Dot color="var(--accent)" />
              Fitness
            </span>
            <span>
              <Dot color="var(--run)" />
              Fatigue
            </span>
            <span>
              <Dot color="var(--bike)" />
              Form
            </span>
            <span>
              <Dot color="var(--muted)" />
              Daily TSS
            </span>
          </div>
        }
        note="Solid lines are history. Dashed lines are the forecast under the recommended taper."
      >
        <Q q={pmc} height={360}>
          {(p) => {
            const data = rows(p)
            return (
              <ResponsiveContainer width="100%" height={360}>
                <ComposedChart data={data} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="day" tickFormatter={shortDate} minTickGap={40} tickLine={false} axisLine={false} />
                  <YAxis yAxisId="l" tickLine={false} axisLine={false} width={36} />
                  <YAxis yAxisId="t" orientation="right" hide domain={[0, (max: number) => max * 3]} />
                  <Tooltip
                    content={({ payload }) => {
                      const r = payload?.[0]?.payload as Row | undefined
                      if (!r) return null
                      return (
                        <Tip
                          title={`${shortDate(r.day)}${r.future ? ' · forecast' : ''}`}
                          rows={[
                            ['Fitness', r.ctl.toFixed(0), 'var(--accent)'],
                            ['Fatigue', r.atl.toFixed(0), 'var(--run)'],
                            ['Form', signed(r.tsb), 'var(--bike)'],
                            [r.future ? 'Planned TSS' : 'TSS', r.tss.toFixed(0)],
                          ]}
                        />
                      )
                    }}
                  />
                  <Bar yAxisId="t" dataKey="tss" fill="var(--muted)" fillOpacity={0.22} />
                  <ReferenceLine yAxisId="l" y={0} stroke="var(--muted)" strokeOpacity={0.4} />
                  {p.forecast && (
                    <ReferenceLine
                      yAxisId="l"
                      x={p.forecast.race_date}
                      stroke="var(--ink)"
                      strokeDasharray="4 4"
                      label={{ value: 'Race', position: 'insideTopRight', fill: 'var(--ink)', fontSize: 11 }}
                    />
                  )}
                  <Area
                    yAxisId="l"
                    dataKey="ctlH"
                    stroke="var(--accent)"
                    strokeWidth={2.2}
                    fill="var(--accent)"
                    fillOpacity={0.1}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="l"
                    dataKey="atlH"
                    stroke="var(--run)"
                    strokeWidth={1.4}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="l"
                    dataKey="tsbH"
                    stroke="var(--bike)"
                    strokeWidth={1.4}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="l"
                    dataKey="ctlF"
                    stroke="var(--accent)"
                    strokeWidth={2.2}
                    strokeDasharray="5 4"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="l"
                    dataKey="atlF"
                    stroke="var(--run)"
                    strokeWidth={1.4}
                    strokeDasharray="5 4"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="l"
                    dataKey="tsbF"
                    stroke="var(--bike)"
                    strokeWidth={1.4}
                    strokeDasharray="5 4"
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            )
          }}
        </Q>
      </Panel>
    </>
  )
}
