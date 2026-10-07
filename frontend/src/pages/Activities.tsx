import { useState } from 'react'
import { useActivities } from '../api'
import { Dot, Panel, Q, Seg } from '../components/ui'
import type { Units } from '../lib/format'
import { distance, hms, pace, weekday } from '../lib/format'

const METHOD: Record<string, string> = {
  power: 'power',
  pace: 'pace',
  swim_pace: 'swim pace',
  heart_rate: 'heart rate',
  relative_effort: 'Relative Effort',
  duration: 'duration',
}

export default function Activities({ units }: { units: Units }) {
  const [sport, setSport] = useState('')
  const [page, setPage] = useState(0)
  const size = 25
  const q = useActivities(sport, page * size, size)

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Activities</h1>
          <p className="lede">Every session with its training stress and the method used to score it.</p>
        </div>
        <Seg
          label="Sport"
          value={sport}
          onChange={(v) => {
            setSport(v)
            setPage(0)
          }}
          options={[
            ['', 'All'],
            ['swim', 'Swim'],
            ['bike', 'Bike'],
            ['run', 'Run'],
            ['strength', 'Strength'],
          ]}
        />
      </div>
      <Panel>
        <Q q={q} height={500}>
          {(d) => (
            <>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Session</th>
                      <th>Time</th>
                      <th>Distance</th>
                      <th>Pace / speed</th>
                      <th>Avg HR</th>
                      <th>Power</th>
                      <th>TSS</th>
                      <th>Scored by</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((a) => (
                      <tr key={a.id}>
                        <td className="n">{weekday(a.day)}</td>
                        <td style={{ whiteSpace: 'normal', minWidth: 180 }}>
                          <Dot sport={a.sport} />
                          {a.name}
                          {a.trainer && (
                            <span className="pill" style={{ marginLeft: 6, color: 'var(--muted)' }}>
                              indoor
                            </span>
                          )}
                        </td>
                        <td className="n">{hms(a.moving_s)}</td>
                        <td className="n">{a.distance_m ? distance(a.distance_m, a.sport, units) : '—'}</td>
                        <td className="n">{a.sport === 'strength' ? '—' : pace(a.avg_speed, a.sport, units)}</td>
                        <td className="n">{a.avg_hr ? Math.round(a.avg_hr) : '—'}</td>
                        <td className="n">
                          {a.np_watts
                            ? `${Math.round(a.np_watts)} W NP`
                            : a.avg_watts
                              ? `${Math.round(a.avg_watts)} W`
                              : '—'}
                        </td>
                        <td className="n">{Math.round(a.tss)}</td>
                        <td className="n" style={{ color: 'var(--muted)' }}>
                          {METHOD[a.tss_method] ?? a.tss_method}
                          {a.intensity ? ` · IF ${a.intensity.toFixed(2)}` : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12 }}>
                <button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>
                  Newer
                </button>
                <button className="btn" disabled={(page + 1) * size >= d.total} onClick={() => setPage(page + 1)}>
                  Older
                </button>
                <span className="note" style={{ margin: 0 }}>
                  {page * size + 1}–{Math.min((page + 1) * size, d.total)} of {d.total}
                </span>
              </div>
            </>
          )}
        </Q>
      </Panel>
    </>
  )
}
