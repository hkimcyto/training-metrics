import { useState } from 'react'
import { Area, Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useGarminImport, useMe, usePmc, useWellness } from '../api'
import { Dot, Kpi, Panel, Q, Tip } from '../components/ui'
import { shortDate } from '../lib/format'
import type { WellnessDay } from '../types'

const STATUS: Record<string, [string, string]> = {
  low: ['Below baseline', 'var(--bad)'],
  balanced: ['Balanced', 'var(--good)'],
  high: ['Above baseline', 'var(--swim)'],
}

function describe(r: number | null): string {
  if (r == null) return 'Not enough nights yet'
  const a = Math.abs(r)
  const s = a > 0.5 ? 'strong' : a > 0.3 ? 'moderate' : a > 0.1 ? 'weak' : 'no clear'
  return `${s} ${r < 0 ? 'negative' : 'positive'} (r = ${r.toFixed(2)})`
}

function Importer() {
  const imp = useGarminImport()
  const me = useMe()
  const [over, setOver] = useState(false)
  if (me.data?.is_demo)
    return (
      <p className="note">
        This is a read-only demo. Sign in with Strava on your own deployment to import a Garmin export.
      </p>
    )
  const pick = (f?: File | null) => f && imp.mutate(f)
  return (
    <>
      <label
        className={`drop${over ? ' over' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          pick(e.dataTransfer.files[0])
        }}
      >
        <input id="garmin-file" type="file" accept=".zip,.json" hidden onChange={(e) => pick(e.target.files?.[0])} />
        <b>Drop your Garmin export here</b> or click to choose a file
        <br />
        <small>The full ZIP from Garmin's “Export Your Data”, or individual sleep / UDS JSON files.</small>
      </label>
      {imp.isPending && <p className="note">Reading the export…</p>}
      {imp.isSuccess && (
        <p className="note up">
          Imported {imp.data.days_imported} days
          {imp.data.first && imp.data.last && ` (${shortDate(imp.data.first)} – ${shortDate(imp.data.last)})`}
          {imp.data.thresholds_imported.length > 0 && ' and your Garmin thresholds'}.
        </p>
      )}
      {imp.isError && <p className="note error">{imp.error.message}</p>}
    </>
  )
}

/** Once data exists, re-importing a newer export is a header button, not a whole panel. */
function ReimportButton() {
  const imp = useGarminImport()
  const me = useMe()
  if (!me.data || me.data.is_demo) return null
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
      {imp.isSuccess && (
        <span className="note up" style={{ margin: 0 }}>
          Imported {imp.data.days_imported} days
          {imp.data.thresholds_imported.length > 0 && ' + thresholds'}
        </span>
      )}
      {imp.isError && (
        <span className="note error" style={{ margin: 0 }}>
          {imp.error.message}
        </span>
      )}
      <label className="btn" title="Upload a newer Garmin export (ZIP or JSON)" aria-disabled={imp.isPending}>
        <input
          type="file"
          accept=".zip,.json"
          hidden
          disabled={imp.isPending}
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) imp.mutate(f)
            e.target.value = ''
          }}
        />
        {imp.isPending ? 'Importing…' : 'Re-import Garmin data'}
      </label>
    </div>
  )
}

export default function Wellness() {
  const well = useWellness(90)
  const pmc = usePmc(90)

  if (well.data && well.data.days.length === 0) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1>Recovery</h1>
            <p className="lede">
              Overnight HRV, resting heart rate and sleep from Garmin, set against training load to show how the body
              absorbs hard days.
            </p>
          </div>
        </div>
        <div className="grid">
          <Panel
            className="span-7"
            title="No Garmin data imported yet"
            note="Strava doesn't receive sleep or HRV, so this page fills from a Garmin account export (or the optional live sync)."
          >
            <p style={{ marginTop: 0 }}>Once imported, this page shows:</p>
            <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6 }}>
              <li>Nightly HRV against a rolling 60-day baseline, flagged when it drops below your normal range</li>
              <li>Resting heart rate, sleep and Body Battery trends</li>
              <li>How strongly yesterday's training stress predicts this morning's HRV and resting HR</li>
            </ul>
          </Panel>
          <Panel className="span-5" title="Import Garmin data">
            <Importer />
          </Panel>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Recovery</h1>
          <p className="lede">
            Overnight HRV, resting heart rate and sleep from Garmin, set against training load to show how your body
            absorbs hard days.
          </p>
        </div>
        <ReimportButton />
      </div>

      <Q q={well} height={110}>
        {(w) => {
          const last = [...w.days].reverse().find((d) => d.hrv_ms) as WellnessDay | undefined
          if (!last)
            return (
              <Panel title="No recovery data yet">
                <Importer />
              </Panel>
            )
          const avg = (k: keyof WellnessDay) => {
            const v = w.days
              .slice(-7)
              .map((d) => d[k] as number | null)
              .filter((x): x is number => x != null)
            return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
          }
          const [label, color] = STATUS[last.hrv_status ?? 'balanced']
          return (
            <div className="kpis">
              <Kpi
                label={`HRV · ${shortDate(last.day)}`}
                value={Math.round(last.hrv_ms!)}
                unit="ms"
                detail={
                  <>
                    <span className="pill" style={{ color }}>
                      {label}
                    </span>{' '}
                    baseline {last.hrv_baseline ? Math.round(last.hrv_baseline) : '—'}
                  </>
                }
              />
              <Kpi label="Resting HR (7-day)" value={avg('rest_hr')?.toFixed(0) ?? '—'} unit="bpm" />
              <Kpi
                label="Sleep (7-day)"
                value={avg('sleep_h')?.toFixed(1) ?? '—'}
                unit="h"
                detail={`score ${avg('sleep_score')?.toFixed(0) ?? '—'}`}
              />
              <Kpi label="Body Battery peak (7-day)" value={avg('body_battery_high')?.toFixed(0) ?? '—'} />
            </div>
          )
        }}
      </Q>

      <Panel
        title="HRV against training load"
        aside={
          <div className="legend">
            <span>
              <Dot color="var(--accent)" />
              HRV
            </span>
            <span>
              <Dot color="var(--muted)" />
              60-day baseline ±1 SD
            </span>
            <span>
              <Dot color="var(--muted)" />
              Daily TSS
            </span>
          </div>
        }
        note="The band is your own normal range. Nights below it after big training days are the body asking for an easier day."
      >
        <Q q={well} height={320}>
          {(w) => {
            const tss = new Map((pmc.data?.series ?? []).map((d) => [d.day, d.tss]))
            const data = w.days.map((d) => {
              const prev = new Date(Date.parse(d.day + 'T12:00:00') - 864e5).toISOString().slice(0, 10)
              const band =
                d.hrv_baseline && d.hrv_sd ? [d.hrv_baseline - d.hrv_sd, d.hrv_baseline + d.hrv_sd] : undefined
              return { ...d, tss: tss.get(prev) ?? 0, band }
            })
            return (
              <ResponsiveContainer width="100%" height={320}>
                <ComposedChart data={data} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="day" tickFormatter={shortDate} minTickGap={40} tickLine={false} axisLine={false} />
                  <YAxis
                    yAxisId="h"
                    domain={['auto', 'auto']}
                    tickLine={false}
                    axisLine={false}
                    width={36}
                    tickFormatter={(v) => `${v}`}
                  />
                  <YAxis yAxisId="t" orientation="right" hide domain={[0, (m: number) => m * 2.5]} />
                  <Tooltip
                    content={({ payload }) => {
                      const r = payload?.[0]?.payload as (WellnessDay & { tss: number }) | undefined
                      if (!r) return null
                      return (
                        <Tip
                          title={shortDate(r.day)}
                          rows={[
                            ['HRV', r.hrv_ms ? `${Math.round(r.hrv_ms)} ms` : '—', 'var(--accent)'],
                            ['Baseline', r.hrv_baseline ? `${Math.round(r.hrv_baseline)} ms` : '—'],
                            ['Resting HR', r.rest_hr ? `${Math.round(r.rest_hr)} bpm` : '—'],
                            ['Sleep', r.sleep_h ? `${r.sleep_h.toFixed(1)} h` : '—'],
                            ['TSS day before', Math.round(r.tss)],
                          ]}
                        />
                      )
                    }}
                  />
                  <Bar yAxisId="t" dataKey="tss" fill="var(--muted)" fillOpacity={0.22} />
                  <Area
                    yAxisId="h"
                    dataKey="band"
                    stroke="none"
                    fill="var(--muted)"
                    fillOpacity={0.15}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="h"
                    dataKey="hrv_baseline"
                    stroke="var(--muted)"
                    strokeDasharray="4 3"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="h"
                    dataKey="hrv_ms"
                    stroke="var(--accent)"
                    strokeWidth={2}
                    dot={{ r: 2 }}
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
          className="span-12"
          title="What the data says"
          note="Pearson correlation across the last 90 nights. Correlation shows a pattern, not proof of cause."
        >
          <Q q={well} height={120}>
            {(w) =>
              w.insights ? (
                <table>
                  <tbody>
                    <tr>
                      <td>Hard day → next-morning HRV</td>
                      <td className="n wrap">{describe(w.insights.hrv_vs_prior_day_tss)}</td>
                    </tr>
                    <tr>
                      <td>Hard day → next-morning resting HR</td>
                      <td className="n wrap">{describe(w.insights.rhr_vs_prior_day_tss)}</td>
                    </tr>
                    <tr>
                      <td>Nights analysed</td>
                      <td className="n">{w.insights.nights}</td>
                    </tr>
                  </tbody>
                </table>
              ) : (
                <p className="note">Import Garmin data to see this.</p>
              )
            }
          </Q>
        </Panel>
      </div>
    </>
  )
}
