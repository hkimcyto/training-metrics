import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useRace } from '../api'
import { Panel, Q, Tip } from '../components/ui'
import type { Units } from '../lib/format'
import { distance, hms, minSec, pace, signed } from '../lib/format'

const LEGS = [
  ['swim', 'Swim', 'var(--swim)'],
  ['t1', 'T1', 'var(--muted)'],
  ['bike', 'Bike', 'var(--bike)'],
  ['t2', 'T2', 'var(--muted)'],
  ['run', 'Run', 'var(--run)'],
] as const

export default function Race({ units }: { units: Units }) {
  const race = useRace()
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Race forecast</h1>
          <p className="lede">
            6,000 simulated races. Each one draws race-day pacing, aerodynamic drag, rolling resistance, run fade and
            transition times from realistic ranges, then solves each leg from your current thresholds.
          </p>
        </div>
      </div>

      <Q q={race} height={420}>
        {(r) => {
          const median = r.legs.total.p50
          const total = LEGS.reduce((s, [k]) => s + r.legs[k].p50, 0)
          return (
            <>
              <div className="grid">
                <Panel className="span-5" title={r.course.name}>
                  <div className="label">Predicted finish (median)</div>
                  <div className="finish">{hms(median)}</div>
                  <p className="mono" style={{ color: 'var(--muted)', margin: '6px 0 16px' }}>
                    80% range {hms(r.legs.total.p10)} – {hms(r.legs.total.p90)}
                  </p>
                  <div
                    style={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden' }}
                    aria-label="Share of race time by leg"
                  >
                    {LEGS.map(([k, , c]) => (
                      <span key={k} style={{ width: `${(r.legs[k].p50 / total) * 100}%`, background: c }} />
                    ))}
                  </div>
                  <div className="legs" style={{ marginTop: 16 }}>
                    {LEGS.filter(([k]) => !k.startsWith('t')).map(([k, label, c]) => (
                      <div key={k} className="leg" style={{ borderLeftColor: c }}>
                        <div className="label">{label}</div>
                        <div className="t">{hms(r.legs[k].p50)}</div>
                        <div className="r">
                          {hms(r.legs[k].p10)}–{hms(r.legs[k].p90)}
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>

                <Panel
                  className="span-7"
                  title="Finish-time distribution"
                  note="Where the 6,000 simulated finishes landed. The shaded bars are the middle 80%."
                >
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={r.histogram} barCategoryGap={1}>
                      <CartesianGrid vertical={false} />
                      <XAxis
                        dataKey="hours"
                        tickFormatter={(h: number) => hms(h * 3600)}
                        tickLine={false}
                        axisLine={false}
                        minTickGap={30}
                      />
                      <YAxis hide />
                      <Tooltip
                        cursor={{ fill: 'var(--grid)' }}
                        content={({ payload }) => {
                          const b = payload?.[0]?.payload as { hours: number; count: number } | undefined
                          return b ? (
                            <Tip title={`≈ ${hms(b.hours * 3600)}`} rows={[['Simulated races', b.count]]} />
                          ) : null
                        }}
                      />
                      <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                        {r.histogram.map((b) => {
                          const inside = b.hours * 3600 >= r.legs.total.p10 && b.hours * 3600 <= r.legs.total.p90
                          return <Cell key={b.hours} fill={inside ? 'var(--accent)' : 'var(--grid)'} />
                        })}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </Panel>
              </div>

              <div className="grid">
                <Panel
                  className="span-4"
                  title="Swim"
                  note={
                    r.course.wetsuit ? 'Wetsuit legal. Includes extra distance from sighting.' : 'Non-wetsuit swim.'
                  }
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
                            : `${r.course.bike_climb_m} m`}
                        </td>
                      </tr>
                      <tr>
                        <td>FTP</td>
                        <td className="n">{Math.round(r.inputs.ftp_watts)} W</td>
                      </tr>
                      <tr>
                        <td>Target power</td>
                        <td className="n">
                          {Math.round(r.bike_avg_watts)} W · IF {r.drivers.bike_intensity_factor.toFixed(2)}
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
                <Panel
                  className="span-4"
                  title="Run"
                  note={`Durability is the share of threshold pace you can hold for a marathon off the bike. Heat at ${r.course.run_temp_c}°C is included.`}
                >
                  <table>
                    <tbody>
                      <tr>
                        <td>Threshold pace</td>
                        <td className="n">{pace(r.inputs.run_threshold_speed, 'run', units)}</td>
                      </tr>
                      <tr>
                        <td>Durability</td>
                        <td className="n">{Math.round(r.drivers.run_durability * 100)}% of threshold</td>
                      </tr>
                      <tr>
                        <td>Predicted pace</td>
                        <td className="n">
                          {units === 'imperial'
                            ? `${minSec(r.run_pace_s_per_km * 1.609344)} /mi`
                            : `${minSec(r.run_pace_s_per_km)} /km`}
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
        }}
      </Q>
    </>
  )
}
