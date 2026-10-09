import { useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
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
import { minSec, shortDate } from '../lib/format'
import { WorkoutCard } from '../components/WorkoutCard'
import type { EfficiencyPoint } from '../types'

const dur = (s: number) => (s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${s / 3600}h`)
const TICKS = [5, 30, 60, 300, 1200, 3600, 7200]

export default function Performance({ units }: { units: Units }) {
  const [days, setDays] = useState(90)
  const pc = usePowerCurve(days)
  const eff = useEfficiency()

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

      <Panel
        title="Aerobic efficiency"
        aside={<span className="label">Steady sessions of 30 min or more</span>}
        note="Your output at the same heart rate, from steady workouts. If the same heartbeat buys you a faster pace or more power, your aerobic engine is improving. The line is the trend; hover any dot for the workout."
      >
        <Q q={eff} height={300}>
          {(e) => (
            <div className="grid" style={{ gap: 16 }}>
              {(['run', 'bike'] as const).map((s) => (
                <div key={s} className="span-6">
                  <SportEfficiency sport={s} points={e.points.filter((x) => x.sport === s)} units={units} />
                </div>
              ))}
            </div>
          )}
        </Q>
      </Panel>

      <Panel
        title="Heart-rate drift (aerobic decoupling)"
        aside={
          <div className="legend">
            <span>
              <Dot sport="run" />
              Run
            </span>
            <span>
              <Dot sport="bike" />
              Bike
            </span>
          </div>
        }
        note="On a long steady session, how much more heart rate the second half cost for the same pace or power. Under 5% means your endurance comfortably covers that duration; over 10% means you were fading. Hover any dot for the workout."
      >
        <Q q={eff} height={300}>
          {(e) => <Decoupling points={e.points} units={units} />}
        </Q>
      </Panel>
    </>
  )
}

const MI = 1609.344
const dayT = (day: string) => Date.parse(day + 'T12:00:00')
const tickDate = (t: number) => shortDate(new Date(t).toISOString().slice(0, 10))
const month = (t: number) => new Date(t).toLocaleDateString('en-US', { month: 'long' })

function median(xs: number[]) {
  const s = [...xs].sort((a, b) => a - b)
  return s.length ? s[Math.floor(s.length / 2)] : 0
}

/** Least-squares line through the points, returned as its two end points. */
function trendLine(pts: { t: number; y: number }[]) {
  const n = pts.length
  const mt = pts.reduce((s, p) => s + p.t, 0) / n
  const my = pts.reduce((s, p) => s + p.y, 0) / n
  const sxx = pts.reduce((s, p) => s + (p.t - mt) ** 2, 0)
  const slope = sxx ? pts.reduce((s, p) => s + (p.t - mt) * (p.y - my), 0) / sxx : 0
  const ts = pts.map((p) => p.t)
  return [Math.min(...ts), Math.max(...ts)].map((t) => ({ t, y: my + slope * (t - mt) }))
}

function SportEfficiency({ sport, points, units }: { sport: 'run' | 'bike'; points: EfficiencyPoint[]; units: Units }) {
  const run = sport === 'run'
  const per = units === 'imperial' ? MI : 1000
  const perLabel = units === 'imperial' ? '/mi' : '/km'
  // compare every workout at one heart rate: the athlete's typical steady HR
  const ref = Math.round(median(points.map((p) => p.avg_hr ?? 0).filter(Boolean)) / 5) * 5 || (run ? 150 : 135)
  const toY = (ef: number) => (run ? per / ((ef * ref) / 60) : ef * ref)
  const fmt = (y: number) => (run ? `${minSec(y)} ${perLabel}` : `${Math.round(y)} W`)
  const data = points.map((p) => ({ ...p, t: dayT(p.day), y: toY(p.ef) }))
  const title = (
    <div className="label" style={{ marginBottom: 6 }}>
      <Dot sport={sport} />
      {run ? `Run pace at ${ref} bpm` : `Bike power at ${ref} bpm`}
    </div>
  )
  if (data.length < 3)
    return (
      <>
        {title}
        <p className="note">Not enough steady {run ? 'runs' : 'rides'} with heart rate yet.</p>
      </>
    )

  const [from, to] = trendLine(data)
  // whole-number watt ticks; pace ticks are left to the chart
  const ys = data.map((d) => d.y)
  const lo = Math.floor(Math.min(...ys) / 10) * 10
  const hi = Math.ceil(Math.max(...ys) / 10) * 10
  const step = hi - lo > 60 ? 20 : 10
  const bikeTicks = run ? undefined : Array.from({ length: Math.ceil((hi - lo) / step) + 1 }, (_, i) => lo + i * step)
  const diff = Math.abs(to.y - from.y)
  const better = run ? to.y < from.y : to.y > from.y
  const flat = diff < 2
  const headline = flat ? (
    <>about the same as in {month(from.t)}</>
  ) : (
    <>
      <b className={better ? 'up' : 'down'}>
        {run
          ? `${minSec(diff)} ${perLabel} ${better ? 'faster' : 'slower'}`
          : `${Math.round(diff)} W ${better ? 'more' : 'less'}`}
      </b>{' '}
      than in {month(from.t)}
    </>
  )

  return (
    <>
      {title}
      <p style={{ margin: '0 0 8px' }}>
        At {ref} bpm you now {run ? 'run' : 'hold'} <b>{fmt(to.y)}</b>, {headline}.
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <ScatterChart margin={{ top: 6, right: 18, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={tickDate}
            tickLine={false}
            axisLine={false}
            minTickGap={30}
          />
          <YAxis
            dataKey="y"
            type="number"
            domain={bikeTicks ? [bikeTicks[0], bikeTicks[bikeTicks.length - 1]] : ['auto', 'auto']}
            ticks={bikeTicks}
            reversed={run}
            tickFormatter={(v: number) => (run ? minSec(v) : `${Math.round(v)}`)}
            tickLine={false}
            axisLine={false}
            width={44}
            label={{
              value: run ? `${perLabel.slice(1)} pace ↑ faster` : 'watts ↑ more',
              angle: -90,
              position: 'insideLeft',
              fill: 'var(--muted)',
              fontSize: 10,
              dy: 40,
            }}
          />
          <ZAxis range={[34, 34]} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ payload }) => {
              const r = payload?.[0]?.payload as (EfficiencyPoint & { y: number }) | undefined
              if (!r || !('id' in r)) return null
              return <WorkoutCard a={r} units={units} efficiency={`${fmt(r.y)} at ${ref} bpm`} />
            }}
          />
          <Scatter data={data} fill={`var(--${sport})`} fillOpacity={0.7} isAnimationActive={false} />
          <Scatter
            data={[from, to]}
            line={{ stroke: `var(--${sport})`, strokeWidth: 2 }}
            shape={() => <g />}
            legendType="none"
            isAnimationActive={false}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </>
  )
}

function Decoupling({ points, units }: { points: EfficiencyPoint[]; units: Units }) {
  const pts = points.filter((x) => x.decoupling != null).map((x) => ({ ...x, t: dayT(x.day) }))
  if (!pts.length) return <p className="note">No long steady sessions with heart rate yet.</p>
  const vals = pts.map((x) => x.decoupling!)
  const lo = Math.min(-5, Math.floor(Math.min(...vals) / 5) * 5)
  const hi = Math.max(15, Math.ceil(Math.max(...vals) / 5) * 5)
  const ticks = Array.from({ length: (hi - lo) / 5 + 1 }, (_, i) => lo + i * 5)
  const steady = vals.filter((v) => v < 5).length
  const zone = (y1: number, y2: number, fill: string, label: string) => (
    <ReferenceArea
      y1={y1}
      y2={y2}
      fill={fill}
      fillOpacity={0.09}
      stroke="none"
      ifOverflow="hidden"
      label={{ value: label, position: 'insideTopLeft', fill, fontSize: 10 }}
    />
  )
  return (
    <>
      <p style={{ marginTop: 0 }}>
        <b>{steady}</b> of {pts.length} long sessions held steady (drift under 5%)
        {pts.length - steady > 0 && (
          <>
            ; <b>{vals.filter((v) => v >= 10).length}</b> faded past 10%
          </>
        )}
        .
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 6, right: 18, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} />
          {zone(lo, 5, 'var(--good)', 'steady')}
          {zone(5, 10, 'var(--warn)', 'some drift')}
          {zone(10, hi, 'var(--bad)', 'fading')}
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={tickDate}
            tickLine={false}
            axisLine={false}
            minTickGap={30}
          />
          <YAxis
            dataKey="decoupling"
            type="number"
            domain={[lo, hi]}
            ticks={ticks}
            tickFormatter={(v: number) => `${v}%`}
            tickLine={false}
            axisLine={false}
            width={40}
          />
          <ZAxis range={[34, 34]} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ payload }) => {
              const r = payload?.[0]?.payload as EfficiencyPoint | undefined
              return r ? <WorkoutCard a={r} units={units} /> : null
            }}
          />
          {(['run', 'bike'] as const).map((s) => (
            <Scatter
              key={s}
              data={pts.filter((x) => x.sport === s)}
              fill={`var(--${s})`}
              fillOpacity={0.8}
              isAnimationActive={false}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </>
  )
}
