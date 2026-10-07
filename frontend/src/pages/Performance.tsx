import { useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { useEfficiency, usePowerCurve } from '../api'
import { Dot, Kpi, Panel, Q, Seg, Tip } from '../components/ui'
import type { Units } from '../lib/format'
import { shortDate, signed } from '../lib/format'

const dur = (s: number) => (s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${s / 3600}h`)
const TICKS = [5, 30, 60, 300, 1200, 3600, 7200]

export default function Performance({ units }: { units: Units }) {
  const [days, setDays] = useState(90)
  const pc = usePowerCurve(days)
  const eff = useEfficiency()
  void units

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Performance</h1>
          <p className="lede">
            How much power you can hold for every duration, and whether you're getting more output per heartbeat.
          </p>
        </div>
        <Seg
          label="Range"
          value={days}
          onChange={setDays}
          options={[
            [42, '6 wk'],
            [90, '90 d'],
            [365, '1 yr'],
          ]}
        />
      </div>

      <Q q={pc} height={110}>
        {(p) => {
          const at = (s: number) => p.recent.find((x) => x.s === s)?.w
          return (
            <div className="kpis">
              <Kpi
                label="Critical power"
                value={p.cp ? Math.round(p.cp.cp) : '—'}
                unit="W"
                detail={p.cp ? `${(p.cp.cp / p.weight_kg).toFixed(2)} W/kg` : 'needs 2–20 min efforts'}
              />
              <Kpi
                label="W′ (anaerobic capacity)"
                value={p.cp ? (p.cp.w_prime / 1000).toFixed(1) : '—'}
                unit="kJ"
                detail="energy above CP"
              />
              <Kpi
                label="Best 20 min"
                value={at(1200) ? Math.round(at(1200)!) : '—'}
                unit="W"
                detail={p.cp ? `FTP ≈ ${Math.round(p.cp.ftp_estimate)} W` : ''}
              />
              <Kpi
                label="Best 5 min"
                value={at(300) ? Math.round(at(300)!) : '—'}
                unit="W"
                detail="VO2max-range effort"
              />
            </div>
          )
        }}
      </Q>

      <Panel
        title="Power-duration curve"
        aside={
          <div className="legend">
            <span>
              <Dot color="var(--bike)" />
              Selected range
            </span>
            <span>
              <Dot color="var(--muted)" />
              All time
            </span>
            <span>
              <Dot color="var(--accent)" />
              Critical Power model
            </span>
          </div>
        }
        note="Best average power for each duration, on a log time axis, from rides with a power meter or smart trainer. The model line is P = W′/t + CP, fitted by least squares to the 2–20 minute bests. Curves built from steady training rides understate true CP; a maximal test effort sharpens them."
      >
        <Q q={pc} height={340}>
          {(p) => {
            const byS = new Map<number, Record<string, number>>()
            p.all_time.forEach((x) => byS.set(x.s, { s: x.s, all: x.w }))
            p.recent.forEach((x) => byS.set(x.s, { ...(byS.get(x.s) ?? { s: x.s }), recent: x.w }))
            const data = [...byS.values()]
              .sort((a, b) => a.s - b.s)
              .map((r) => ({
                ...r,
                model: p.cp && r.s >= 120 && r.s <= 3600 ? p.cp.w_prime / r.s + p.cp.cp : undefined,
              }))
            return (
              <ResponsiveContainer width="100%" height={340}>
                <ComposedChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis
                    dataKey="s"
                    type="number"
                    scale="log"
                    domain={[5, 7200]}
                    ticks={TICKS}
                    tickFormatter={dur}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis tickFormatter={(v) => `${v}W`} tickLine={false} axisLine={false} width={44} />
                  <Tooltip
                    content={({ payload }) => {
                      const r = payload?.[0]?.payload as
                        { s: number; all?: number; recent?: number; model?: number } | undefined
                      if (!r) return null
                      return (
                        <Tip
                          title={`Best ${dur(r.s)}`}
                          rows={[
                            ['Selected', r.recent ? `${Math.round(r.recent)} W` : '—', 'var(--bike)'],
                            ['All time', r.all ? `${Math.round(r.all)} W` : '—', 'var(--muted)'],
                            ...(r.model
                              ? [['Model', `${Math.round(r.model)} W`, 'var(--accent)'] as [string, string, string]]
                              : []),
                          ]}
                        />
                      )
                    }}
                  />
                  {p.cp && (
                    <ReferenceLine y={p.cp.cp} stroke="var(--accent)" strokeOpacity={0.4} strokeDasharray="3 3" />
                  )}
                  <Line dataKey="all" stroke="var(--muted)" strokeWidth={1.4} dot={false} isAnimationActive={false} />
                  <Line
                    dataKey="recent"
                    stroke="var(--bike)"
                    strokeWidth={2.4}
                    dot={{ r: 2.5, fill: 'var(--bike)' }}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="model"
                    stroke="var(--accent)"
                    strokeWidth={1.6}
                    strokeDasharray="5 4"
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            )
          }}
        </Q>
      </Panel>

      <div className="grid">
        <Panel
          className="span-7"
          title="Aerobic efficiency"
          aside={
            <div className="legend">
              <span>
                <Dot sport="bike" />
                Bike (W per bpm)
              </span>
              <span>
                <Dot sport="run" />
                Run (m/min per bpm)
              </span>
            </div>
          }
          note="Efficiency Factor from steady sessions of 30 minutes or more. Rising values mean more output at the same heart rate."
        >
          <Q q={eff} height={300}>
            {(e) => (
              <>
                <p style={{ marginTop: 0 }}>
                  {(['bike', 'run'] as const).map((s) =>
                    e.trend[s] ? (
                      <span key={s} style={{ marginRight: 18 }}>
                        <Dot sport={s} />
                        {s === 'bike' ? 'Bike' : 'Run'}{' '}
                        <b className={e.trend[s]!.pct_per_4wk >= 0 ? 'up' : 'down'}>
                          {signed(e.trend[s]!.pct_per_4wk, 1)}%
                        </b>{' '}
                        per 4 weeks
                      </span>
                    ) : null,
                  )}
                </p>
                <div className="grid" style={{ gap: 8 }}>
                  {(['bike', 'run'] as const).map((s) => (
                    <div key={s} className="span-6">
                      <ResponsiveContainer width="100%" height={240}>
                        <ScatterChart margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
                          <CartesianGrid vertical={false} />
                          <XAxis
                            dataKey="t"
                            type="number"
                            domain={['dataMin', 'dataMax']}
                            tickFormatter={(t) => shortDate(new Date(t).toISOString().slice(0, 10))}
                            tickLine={false}
                            axisLine={false}
                            minTickGap={30}
                          />
                          <YAxis
                            dataKey="ef"
                            domain={['auto', 'auto']}
                            tickFormatter={(v) => v.toFixed(2)}
                            tickLine={false}
                            axisLine={false}
                            width={40}
                          />
                          <ZAxis range={[28, 28]} />
                          <Tooltip
                            content={({ payload }) => {
                              const r = payload?.[0]?.payload as
                                { day: string; ef: number; name: string; decoupling: number | null } | undefined
                              if (!r) return null
                              return (
                                <Tip
                                  title={`${shortDate(r.day)} · ${r.name}`}
                                  rows={[
                                    ['Efficiency', r.ef.toFixed(3)],
                                    ['Decoupling', r.decoupling != null ? `${r.decoupling.toFixed(1)}%` : '—'],
                                  ]}
                                />
                              )
                            }}
                          />
                          <Scatter
                            data={e.points
                              .filter((x) => x.sport === s)
                              .map((x) => ({ ...x, t: Date.parse(x.day + 'T12:00:00') }))}
                            fill={`var(--${s})`}
                            fillOpacity={0.75}
                            isAnimationActive={false}
                          />
                        </ScatterChart>
                      </ResponsiveContainer>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Q>
        </Panel>

        <Panel
          className="span-5"
          title="Aerobic decoupling"
          note="How much heart rate drifted relative to output between the first and second half of long sessions. Under 5% suggests aerobic endurance is in place for that duration."
        >
          <Q q={eff} height={300}>
            {(e) => {
              const pts = e.points
                .filter((x) => x.decoupling != null)
                .map((x) => ({ ...x, t: Date.parse(x.day + 'T12:00:00') }))
              const under = pts.filter((x) => x.decoupling! < 5).length
              return (
                <>
                  <p style={{ marginTop: 0 }}>
                    <b>{under}</b> of {pts.length} long sessions under 5%
                  </p>
                  <ResponsiveContainer width="100%" height={240}>
                    <ScatterChart margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
                      <CartesianGrid vertical={false} />
                      <XAxis
                        dataKey="t"
                        type="number"
                        domain={['dataMin', 'dataMax']}
                        tickFormatter={(t) => shortDate(new Date(t).toISOString().slice(0, 10))}
                        tickLine={false}
                        axisLine={false}
                        minTickGap={30}
                      />
                      <YAxis
                        dataKey="decoupling"
                        tickFormatter={(v) => `${v}%`}
                        tickLine={false}
                        axisLine={false}
                        width={40}
                      />
                      <ZAxis range={[30, 30]} />
                      <ReferenceLine
                        y={5}
                        stroke="var(--warn)"
                        strokeDasharray="4 3"
                        label={{ value: '5%', fill: 'var(--warn)', fontSize: 10, position: 'insideTopRight' }}
                      />
                      <Tooltip
                        content={({ payload }) => {
                          const r = payload?.[0]?.payload as
                            { day: string; decoupling: number; name: string } | undefined
                          return r ? (
                            <Tip
                              title={`${shortDate(r.day)} · ${r.name}`}
                              rows={[['Decoupling', `${r.decoupling.toFixed(1)}%`]]}
                            />
                          ) : null
                        }}
                      />
                      {(['bike', 'run'] as const).map((s) => (
                        <Scatter
                          key={s}
                          data={pts.filter((x) => x.sport === s)}
                          fill={`var(--${s})`}
                          isAnimationActive={false}
                        />
                      ))}
                    </ScatterChart>
                  </ResponsiveContainer>
                </>
              )
            }}
          </Q>
        </Panel>
      </div>
    </>
  )
}
