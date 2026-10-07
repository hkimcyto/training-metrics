import { useState } from 'react'
import { useMe, useSaveSettings } from '../api'
import { Panel, Q } from '../components/ui'
import { pace } from '../lib/format'
import type { Me } from '../types'

type Form = Record<string, string | boolean>

const MI = 1609.344
const YD = 0.9144

/** Thresholds are stored as m/s; people think in pace, so convert both ways. */
const toPace = (speed: number | null, per: number) => {
  if (!speed) return ''
  const s = per / speed
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
}
const fromPace = (v: string, per: number) => {
  const m = /^(\d+):(\d{1,2})$/.exec(v.trim())
  if (!m) return null
  const secs = Number(m[1]) * 60 + Number(m[2])
  return secs ? per / secs : null
}

export default function Settings() {
  const me = useMe()
  return (
    <Q q={me} height={400}>
      {(m) => <SettingsForm key={m.id} m={m} />}
    </Q>
  )
}

function SettingsForm({ m }: { m: Me }) {
  const save = useSaveSettings()
  const imperial = m.measurement !== 'metric'
  const runPer = imperial ? MI : 1000
  const swimPer = imperial ? 100 * YD : 100
  const [form, setForm] = useState<Form>(() => {
    const s = m.settings
    return {
      race_name: s.race_name ?? '',
      race_date: s.race_date ?? '',
      race_climb_m: String(s.race_climb_m),
      race_temp_c: String(s.race_temp_c),
      race_wetsuit: s.race_wetsuit,
      weight_kg: String(s.weight_kg),
      ftp_watts: s.ftp_watts ? String(Math.round(s.ftp_watts)) : '',
      run_pace: toPace(s.run_threshold_speed, runPer),
      css_pace: toPace(s.css_speed, swimPer),
      max_hr: s.max_hr ? String(s.max_hr) : '',
      rest_hr: s.rest_hr ? String(s.rest_hr) : '',
      lthr: s.lthr ? String(s.lthr) : '',
    }
  })

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const num = (k: string) => (form[k] === '' ? null : Number(form[k]))

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const body: Partial<Me['settings']> = {
      race_name: (form.race_name as string) || null,
      race_date: (form.race_date as string) || null,
      race_climb_m: num('race_climb_m') ?? 1500,
      race_temp_c: num('race_temp_c') ?? 22,
      race_wetsuit: Boolean(form.race_wetsuit),
      weight_kg: num('weight_kg') ?? 75,
      ftp_watts: num('ftp_watts'),
      run_threshold_speed: fromPace(form.run_pace as string, runPer),
      css_speed: fromPace(form.css_pace as string, swimPer),
      max_hr: num('max_hr'),
      rest_hr: num('rest_hr'),
      lthr: num('lthr'),
    }
    save.mutate(body)
  }

  const field = (id: string, label: string, hint?: string, type = 'text') => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} type={type} value={String(form[id] ?? '')} onChange={set(id)} disabled={m.is_demo} />
      {hint && <small>{hint}</small>}
    </div>
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <p className="lede">
            Leave a threshold blank and it's estimated from your recent training. Changing one re-scores every workout.
          </p>
        </div>
      </div>
      <form onSubmit={submit} style={{ display: 'grid', gap: 16 }}>
        <Panel title="Race">
          <div className="form">
            {field('race_name', 'Race name')}
            {field('race_date', 'Race date', undefined, 'date')}
            {field('race_climb_m', 'Bike climbing (m)', 'Total elevation gain on the bike course')}
            {field('race_temp_c', 'Run temperature (°C)', 'Expected afternoon temperature')}
            <div className="field">
              <label htmlFor="race_wetsuit">
                <input
                  id="race_wetsuit"
                  type="checkbox"
                  checked={Boolean(form.race_wetsuit)}
                  onChange={set('race_wetsuit')}
                  disabled={m.is_demo}
                />{' '}
                Wetsuit-legal swim
              </label>
            </div>
          </div>
        </Panel>
        <Panel title="Thresholds">
          <div className="form">
            {field('weight_kg', 'Weight (kg)')}
            {field(
              'ftp_watts',
              'FTP (W)',
              `Current: ${Math.round(m.thresholds.ftp_watts)} W, ${m.thresholds.sources.ftp}`,
            )}
            {field(
              'run_pace',
              `Run threshold pace (min/${imperial ? 'mi' : 'km'})`,
              `Current: ${pace(m.thresholds.run_threshold_speed, 'run', m.measurement)}, ${m.thresholds.sources.run}`,
            )}
            {field(
              'css_pace',
              `Critical swim speed (min/100${imperial ? 'yd' : 'm'})`,
              `Current: ${pace(m.thresholds.css_speed, 'swim', m.measurement)}, ${m.thresholds.sources.css}`,
            )}
            {field('max_hr', 'Max HR (bpm)')}
            {field('rest_hr', 'Resting HR (bpm)')}
            {field('lthr', 'Lactate threshold HR (bpm)', `Current: ${Math.round(m.thresholds.lthr)}`)}
          </div>
        </Panel>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button className="btn primary" type="submit" disabled={m.is_demo || save.isPending}>
            {save.isPending ? 'Saving…' : 'Save and re-score'}
          </button>
          {m.is_demo && (
            <span className="note" style={{ margin: 0 }}>
              The demo athlete is read-only.
            </span>
          )}
          {save.isSuccess && (
            <span className="note up" style={{ margin: 0 }}>
              Saved. Every workout has been re-scored.
            </span>
          )}
          {save.isError && (
            <span className="note error" style={{ margin: 0 }}>
              {save.error.message}
            </span>
          )}
        </div>
      </form>
    </>
  )
}
