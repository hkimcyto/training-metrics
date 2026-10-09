import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useMe, useRace } from '../api'
import { Panel, Q, Tip } from '../components/ui'
import type { Units } from '../lib/format'
import { distance, hms, minSec, pace, raceTime, signed } from '../lib/format'
import type { LegKey, RacePrediction, RaceType } from '../types'

const LEGS: readonly (readonly [LegKey, string, string])[] = [
  ['swim', 'Swim', 'var(--swim)'],
  ['t1', 'T1', 'var(--muted)'],
  ['bike', 'Bike', 'var(--bike)'],
  ['t2', 'T2', 'var(--muted)'],
  ['run', 'Run', 'var(--run)'],
]

const runPace = (sPerKm: number, units: Units) =>
  units === 'imperial' ? `${minSec(sPerKm * 1.609344)} /mi` : `${minSec(sPerKm)} /km`

export default function Race({ units }: { units: Units }) {
  const me = useMe()
  const [picked, setPicked] = useState<string>()
  const raceType = picked ?? me.data?.settings.race_type
  const race = useRace(raceType)
  const types = me.data?.race_types ?? []

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Race forecast</h1>
          <p className="lede">
            6,000 simulated races. Each one draws race-day pacing, fade and conditions from realistic ranges, then
            solves every leg from your current thresholds and race-day form.
          </p>
        </div>
        {types.length > 0 && raceType && (
          <div className="field">
            <label htmlFor="race-type">Race</label>
            <select id="race-type" value={raceType} onChange={(e) => setPicked(e.target.value)}>
              {(['run', 'triathlon'] as const).map((kind) => (
                <optgroup key={kind} label={kind === 'run' ? 'Running' : 'Triathlon'}>
                  {types
                    .filter((t: RaceType) => t.kind === kind)
                    .map((t) => (
                      <option key={t.key} value={t.key}>
                        {t.label}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </div>
        )}
      </div>

      <Q q={race} height={420}>
        {(r) => <Forecast r={r} units={units} />}
      </Q>
    </>
  )
}

function Forecast({ r, units }: { r: RacePrediction; units: Units }) {
  const tri = r.course.kind === 'triathlon'
  const legs = LEGS.filter(([k]) => r.legs[k])
  const share = legs.reduce((s, [k]) => s + r.legs[k]!.p50, 0)
  const total = r.legs.total
  const runLeg = r.legs.run!
  const conditions = r.is_target
    ? null
    : `Typical course: ${tri ? `${Math.round(r.course.bike_climb_m)} m of bike climbing, wetsuit legal, ` : ''}${r.course.run_temp_c}°C. Set this as your race in Settings to use your own course.`

  return (
    <>
      <div className="grid">
        <Panel className="span-5" title={r.course.name} note={conditions}>
          <div className="label">Predicted finish (median)</div>
          <div className="finish">{raceTime(total.p50)}</div>
          <p className="mono" style={{ color: 'var(--muted)', margin: '6px 0 16px' }}>
            80% range {raceTime(total.p10)} – {raceTime(total.p90)}
          </p>
          {tri ? (
            <>
              <div
                style={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden' }}
                aria-label="Share of race time by leg"
              >
                {legs.map(([k, , c]) => (
                  <span key={k} style={{ width: `${(r.legs[k]!.p50 / share) * 100}%`, background: c }} />
                ))}
              </div>
              <div className="legs" style={{ marginTop: 16 }}>
                {legs
                  .filter(([k]) => !k.startsWith('t'))
                  .map(([k, label, c]) => (
                    <div key={k} className="leg" style={{ borderLeftColor: c }}>
                      <div className="label">{label}</div>
                      <div className="t">{raceTime(r.legs[k]!.p50)}</div>
                      <div className="r">
                        {raceTime(r.legs[k]!.p10)}–{raceTime(r.legs[k]!.p90)}
                      </div>
                    </div>
                  ))}
              </div>
            </>
          ) : (
            <div className="legs">
              <div className="leg" style={{ borderLeftColor: 'var(--run)' }}>
                <div className="label">Average pace</div>
                <div className="t">{runPace(r.run_pace_s_per_km, units)}</div>
                <div className="r">{distance(r.course.run_m, 'run', units)}</div>
              </div>
              <div className="leg" style={{ borderLeftColor: 'var(--muted)' }}>
                <div className="label">vs threshold</div>
                <div className="t">{Math.round(r.drivers.run_vs_threshold * 100)}%</div>
                <div className="r">of threshold speed</div>
              </div>
            </div>
          )}
        </Panel>

        <Panel
          className="span-7"
          title="Finish-time distribution"
          note="Where the 6,000 simulated finishes landed. The shaded bars are the middle 80%."
        >
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={r.histogram} barCategoryGap={1}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="s" tickFormatter={raceTime} tickLine={false} axisLine={false} minTickGap={30} />
              <YAxis hide />
              <Tooltip
                cursor={{ fill: 'var(--grid)' }}
                content={({ payload }) => {
                  const b = payload?.[0]?.payload as { s: number; count: number } | undefined
                  return b ? <Tip title={`≈ ${raceTime(b.s)}`} rows={[['Simulated races', b.count]]} /> : null
                }}
              />
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {r.histogram.map((b) => (
                  <Cell key={b.s} fill={b.s >= total.p10 && b.s <= total.p90 ? 'var(--accent)' : 'var(--grid)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <div className="grid">
        {tri && r.legs.swim && (
          <Panel
            className="span-4"
            title="Swim"
            note={r.course.wetsuit ? 'Wetsuit legal. Includes extra distance from sighting.' : 'Non-wetsuit swim.'}
          >
            <table>
              <tbody>
                <tr>
                  <td>Distance</td>
                  <td className="n">{distance(r.course.swim_m, 'swim', units)}</td>
                </tr>
                <tr>
                  <td>Critical swim speed</td>
                  <td className="n">{pace(r.inputs.css_speed, 'swim', units)}</td>
                </tr>
                <tr>
                  <td>Predicted pace</td>
                  <td className="n">{pace(r.course.swim_m / r.legs.swim.p50, 'swim', units)}</td>
                </tr>
                <tr>
                  <td>Threshold source</td>
                  <td className="n">{r.inputs.sources.css}</td>
                </tr>
              </tbody>
            </table>
          </Panel>
        )}
        {tri && r.bike_avg_watts != null && (
          <Panel
            className="span-4"
            title="Bike"
            note="Speed solved from an energy balance: your power against air drag, rolling resistance and climbing."
          >
            <table>
              <tbody>
                <tr>
                  <td>Distance · climbing</td>
                  <td className="n">
                    {distance(r.course.bike_m, 'bike', units)} ·{' '}
                    {units === 'imperial'
                      ? `${Math.round(r.course.bike_climb_m * 3.281).toLocaleString()} ft`
                      : `${Math.round(r.course.bike_climb_m)} m`}
                  </td>
                </tr>
                <tr>
                  <td>FTP</td>
                  <td className="n">{Math.round(r.inputs.ftp_watts)} W</td>
                </tr>
                <tr>
                  <td>Target power</td>
                  <td className="n">
                    {Math.round(r.bike_avg_watts)} W · IF {r.drivers.bike_intensity_factor?.toFixed(2)}
                  </td>
                </tr>
                <tr>
                  <td>Average speed</td>
                  <td className="n">{pace(r.bike_avg_speed, 'bike', units)}</td>
                </tr>
                <tr>
                  <td>Longest ride (8 wk)</td>
                  <td className="n">{hms(r.inputs.longest_ride_8wk_s)} h</td>
                </tr>
              </tbody>
            </table>
          </Panel>
        )}
        <Panel
          className={tri ? 'span-4' : 'span-12'}
          title="Run"
          note={
            tri
              ? `Durability is the share of threshold pace you can hold over ${distance(r.course.run_m, 'run', units)} off the bike. Heat at ${r.course.run_temp_c}°C is included.`
              : `Threshold pace is stretched to the race distance with Riegel's power law, then scaled by durability (long runs and fitness) and heat at ${r.course.run_temp_c}°C.`
          }
        >
          <table>
            <tbody>
              <tr>
                <td>Threshold pace</td>
                <td className="n">{pace(r.inputs.run_threshold_speed, 'run', units)}</td>
              </tr>
              <tr>
                <td>Durability</td>
                <td className="n">
                  {Math.round(r.drivers.run_durability * 100)}% {tri ? 'of threshold' : 'of fresh-legs pace'}
                </td>
              </tr>
              <tr>
                <td>Predicted pace</td>
                <td className="n">
                  {runPace(r.run_pace_s_per_km, units)}
                  {!tri && ` · ${raceTime(runLeg.p10)}–${raceTime(runLeg.p90)}`}
                </td>
              </tr>
              <tr>
                <td>Longest run (8 wk)</td>
                <td className="n">{distance(r.inputs.longest_run_8wk_m, 'run', units)}</td>
              </tr>
              <tr>
                <td>Race-day form</td>
                <td className="n">
                  {signed(r.inputs.race_day_tsb)} → ×{r.drivers.form_multiplier.toFixed(3)}
                </td>
              </tr>
            </tbody>
          </table>
        </Panel>
      </div>
    </>
  )
}
