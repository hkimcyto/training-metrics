import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAddRace, useDeleteRace, useEditRace, useMe, useRace, useRaces } from '../api'
import { Panel, Q, Tip } from '../components/ui'
import type { Units } from '../lib/format'
import { distance, hms, minSec, pace, raceTime, shortDate, signed, weekday } from '../lib/format'
import type { CatalogRace, LegKey, Priority, RaceInput, RacePrediction, Races, RaceType, SavedRace } from '../types'

const LEGS: readonly (readonly [LegKey, string, string])[] = [
  ['swim', 'Swim', 'var(--swim)'],
  ['t1', 'T1', 'var(--muted)'],
  ['bike', 'Bike', 'var(--bike)'],
  ['t2', 'T2', 'var(--muted)'],
  ['run', 'Run', 'var(--run)'],
]

const MI = 1609.344
const PRIORITY: Record<Priority, [string, string]> = {
  A: ['A race', 'var(--accent)'],
  B: ['B race', 'var(--bike)'],
  C: ['C race', 'var(--muted)'],
}

const runPace = (sPerKm: number, units: Units) =>
  units === 'imperial' ? `${minSec(sPerKm * 1.609344)} /mi` : `${minSec(sPerKm)} /km`

/** "in 9 days", "in 5 weeks", "3 days ago": how far a race is from today. */
function fromToday(day: string, today: string) {
  const d = Math.round((Date.parse(day) - Date.parse(today)) / 864e5)
  if (d === 0) return 'today'
  const n = Math.abs(d)
  const span = n > 35 ? `${Math.round(n / 7)} weeks` : `${n} day${n === 1 ? '' : 's'}`
  return d > 0 ? `in ${span}` : `${span} ago`
}

/** A race date, with the year when it isn't this year's. */
const raceDate = (day: string, today: string | undefined, fmt: (d: string) => string = weekday) =>
  today && day.slice(0, 4) !== today.slice(0, 4) ? `${fmt(day)}, ${day.slice(0, 4)}` : fmt(day)

/** A race's type with its distance when that isn't implied, e.g. "15 km run". */
const raceLabel = (r: SavedRace, units: Units) =>
  r.race_type === 'run' && r.distance_m ? `${distance(r.distance_m, 'run', units)} run` : r.label

export default function Race({ units }: { units: Units }) {
  const me = useMe()
  const races = useRaces()
  const [picked, setPicked] = useState<string>()
  const data = races.data
  const value = picked ?? (data?.target_id != null ? `race:${data.target_id}` : data ? 'type:marathon' : undefined)
  const pick = value
    ? value.startsWith('race:')
      ? { raceId: Number(value.slice(5)) }
      : { type: value.slice(5) }
    : null
  const race = useRace(pick)
  const readOnly = me.data?.is_demo ?? true

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Race forecast</h1>
          <p className="lede">
            6,000 simulated races. Each one draws race-day pacing, fade and conditions from realistic ranges, then
            solves every leg from your current thresholds and your fitness and form on race day.
          </p>
        </div>
        {data && value && (
          <div className="field">
            <label htmlFor="race-pick">Forecast</label>
            <select id="race-pick" value={value} onChange={(e) => setPicked(e.target.value)}>
              {data.races.length > 0 && (
                <optgroup label="Your races">
                  {data.races.map((r) => (
                    <option key={r.id} value={`race:${r.id}`}>
                      {r.name} · {raceDate(r.day, data.today, shortDate)}
                    </option>
                  ))}
                </optgroup>
              )}
              {(['run', 'triathlon'] as const).map((kind) => (
                <optgroup key={kind} label={`Any distance · ${kind === 'run' ? 'running' : 'triathlon'}`}>
                  {data.race_types
                    .filter((t: RaceType) => t.kind === kind)
                    .map((t) => (
                      <option key={t.key} value={`type:${t.key}`}>
                        {t.label}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </div>
        )}
      </div>

      <Q q={races} height={160}>
        {(d) => (
          <RaceCalendar
            data={d}
            units={units}
            readOnly={readOnly}
            selected={pick?.raceId}
            onSelect={(id) => setPicked(`race:${id}`)}
            onRemoved={(id) => pick?.raceId === id && setPicked(undefined)}
          />
        )}
      </Q>

      {pick && (
        <Q q={race} height={420}>
          {(r) => <Forecast r={r} units={units} today={data?.today} />}
        </Q>
      )}
    </>
  )
}

function RaceCalendar({
  data,
  units,
  readOnly,
  selected,
  onSelect,
  onRemoved,
}: {
  data: Races
  units: Units
  readOnly: boolean
  selected?: number
  onSelect: (id: number) => void
  onRemoved: (id: number) => void
}) {
  const [editing, setEditing] = useState<SavedRace | 'new' | null>(null)
  const del = useDeleteRace()
  return (
    <Panel
      title="Your races"
      aside={
        !readOnly &&
        editing === null && (
          <button className="btn primary" onClick={() => setEditing('new')}>
            Add race
          </button>
        )
      }
      note={
        readOnly
          ? 'This is a read-only demo. Connect Strava to keep your own race calendar.'
          : 'Your next A race is the target: the taper, the countdown and the forecast default all work toward it. B and C races are tune-ups and training races.'
      }
    >
      {editing !== null && (
        <RaceForm
          initial={editing === 'new' ? null : editing}
          catalog={data.catalog}
          types={data.race_types}
          units={units}
          onDone={(saved) => {
            setEditing(null)
            if (saved) onSelect(saved.id)
          }}
        />
      )}
      {data.races.length === 0 ? (
        editing === null && (
          <p style={{ margin: 0 }}>
            No races yet. {readOnly ? '' : 'Add one to forecast it with its own course and date.'}
          </p>
        )
      ) : (
        <div className="tablewrap">
          <table>
            <tbody>
              {data.races.map((r) => {
                const past = r.day < data.today
                const [plabel, pcolor] = PRIORITY[r.priority]
                return (
                  <tr
                    key={r.id}
                    onClick={() => onSelect(r.id)}
                    style={{
                      cursor: 'pointer',
                      opacity: past ? 0.6 : 1,
                      background: selected === r.id ? 'var(--grid)' : undefined,
                    }}
                  >
                    <td style={{ width: 70 }}>
                      <span className="pill" style={{ color: pcolor }}>
                        {plabel}
                      </span>
                    </td>
                    <td style={{ whiteSpace: 'normal' }}>
                      <b>{r.name}</b>
                      {r.id === data.target_id && (
                        <span className="pill" style={{ marginLeft: 8, color: 'var(--good)' }}>
                          target
                        </span>
                      )}
                      <div style={{ color: 'var(--muted)', fontSize: '.78rem' }}>{raceLabel(r, units)}</div>
                    </td>
                    <td className="n">{raceDate(r.day, data.today)}</td>
                    <td className="n" style={{ color: 'var(--muted)' }}>
                      {fromToday(r.day, data.today)}
                    </td>
                    {!readOnly && (
                      <td className="n" style={{ width: 150 }} onClick={(e) => e.stopPropagation()}>
                        <button className="btn" onClick={() => setEditing(r)}>
                          Edit
                        </button>{' '}
                        <button
                          className="btn"
                          disabled={del.isPending}
                          onClick={() => {
                            if (window.confirm(`Remove ${r.name} from your races?`))
                              del.mutate(r.id, { onSuccess: () => onRemoved(r.id) })
                          }}
                        >
                          Remove
                        </button>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

type Draft = Record<'name' | 'day' | 'race_type' | 'distance' | 'priority' | 'temp_c' | 'climb_m', string> & {
  wetsuit: boolean
  catalog_key: string | null
}

function RaceForm({
  initial,
  catalog,
  types,
  units,
  onDone,
}: {
  initial: SavedRace | null
  catalog: CatalogRace[]
  types: RaceType[]
  units: Units
  onDone: (saved?: SavedRace) => void
}) {
  const per = units === 'imperial' ? MI : 1000
  const add = useAddRace()
  const edit = useEditRace()
  const save = initial ? edit : add
  const [f, setF] = useState<Draft>(() => ({
    name: initial?.name ?? '',
    day: initial?.day ?? '',
    race_type: initial?.race_type ?? 'marathon',
    distance: initial?.distance_m ? String(+(initial.distance_m / per).toFixed(2)) : '',
    priority: initial?.priority ?? 'A',
    temp_c: String(initial?.temp_c ?? 18),
    climb_m: initial?.climb_m != null ? String(initial.climb_m) : '',
    wetsuit: initial?.wetsuit ?? true,
    catalog_key: initial?.catalog_key ?? null,
  }))
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value })
  const tri = types.find((t) => t.key === f.race_type)?.kind === 'triathlon'
  const custom = f.race_type === 'run'

  const fromCatalog = (key: string) => {
    const c = catalog.find((x) => x.key === key)
    if (!c) return setF({ ...f, catalog_key: null })
    setF({
      ...f,
      catalog_key: c.key,
      name: c.name,
      race_type: c.race_type,
      temp_c: String(c.temp_c),
      climb_m: c.climb_m != null ? String(c.climb_m) : '',
      wetsuit: c.wetsuit,
    })
  }
  const picked = catalog.find((c) => c.key === f.catalog_key)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const body: RaceInput = {
      name: f.name.trim(),
      day: f.day,
      race_type: f.race_type,
      distance_m: custom && f.distance ? Number(f.distance) * per : null,
      priority: f.priority as Priority,
      temp_c: Number(f.temp_c || 18),
      climb_m: tri && f.climb_m !== '' ? Number(f.climb_m) : null,
      wetsuit: f.wetsuit,
      catalog_key: f.catalog_key,
    }
    if (initial) edit.mutate({ id: initial.id, ...body }, { onSuccess: (r) => onDone(r) })
    else add.mutate(body, { onSuccess: (r) => onDone(r) })
  }

  const groups: [string, string[]][] = [
    ['Marathons', ['marathon']],
    ['Half marathons', ['half_marathon']],
    ['Triathlons', ['sprint_tri', 'olympic_tri', 'half_ironman', 'ironman']],
  ]
  return (
    <form
      onSubmit={submit}
      style={{ display: 'grid', gap: 14, paddingBottom: 16, marginBottom: 12, borderBottom: '1px solid var(--line)' }}
    >
      <div className="form">
        <div className="field">
          <label htmlFor="rf-catalog">Start from</label>
          <select id="rf-catalog" value={f.catalog_key ?? ''} onChange={(e) => fromCatalog(e.target.value)}>
            <option value="">My own race (fill in below)</option>
            {groups.map(([label, keys]) => (
              <optgroup key={label} label={label}>
                {catalog
                  .filter((c) => keys.includes(c.race_type))
                  .map((c) => (
                    <option key={c.key} value={c.key}>
                      {c.name}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
          {picked && (
            <small>
              {picked.location} · usually {picked.month}. Course values are typical; adjust them if you know better.
            </small>
          )}
        </div>
        <div className="field">
          <label htmlFor="rf-name">Race name</label>
          <input id="rf-name" required maxLength={120} value={f.name} onChange={set('name')} />
        </div>
        <div className="field">
          <label htmlFor="rf-day">Date</label>
          <input id="rf-day" type="date" required value={f.day} onChange={set('day')} />
        </div>
        <div className="field">
          <label htmlFor="rf-type">Type</label>
          <select id="rf-type" value={f.race_type} onChange={set('race_type')}>
            <optgroup label="Running">
              {types
                .filter((t) => t.kind === 'run')
                .map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.label}
                  </option>
                ))}
              <option value="run">Other distance…</option>
            </optgroup>
            <optgroup label="Triathlon">
              {types
                .filter((t) => t.kind === 'triathlon')
                .map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.label}
                  </option>
                ))}
            </optgroup>
          </select>
        </div>
        {custom && (
          <div className="field">
            <label htmlFor="rf-distance">Distance ({units === 'imperial' ? 'mi' : 'km'})</label>
            <input
              id="rf-distance"
              type="number"
              required
              min={0.2}
              step="any"
              value={f.distance}
              onChange={set('distance')}
            />
          </div>
        )}
        <div className="field">
          <label htmlFor="rf-priority">Priority</label>
          <select id="rf-priority" value={f.priority} onChange={set('priority')}>
            <option value="A">A: goal race (you taper for it)</option>
            <option value="B">B: important, minor taper</option>
            <option value="C">C: training race</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="rf-temp">Temperature (°C)</label>
          <input id="rf-temp" type="number" step="any" value={f.temp_c} onChange={set('temp_c')} />
          <small>{tri ? 'Expected during the run' : 'Expected during the race'}</small>
        </div>
        {tri && (
          <>
            <div className="field">
              <label htmlFor="rf-climb">Bike climbing (m)</label>
              <input id="rf-climb" type="number" min={0} step="any" value={f.climb_m} onChange={set('climb_m')} />
              <small>Leave blank for a typical rolling course</small>
            </div>
            <div className="field">
              <label htmlFor="rf-wetsuit">
                <input id="rf-wetsuit" type="checkbox" checked={f.wetsuit} onChange={set('wetsuit')} /> Wetsuit-legal
                swim
              </label>
            </div>
          </>
        )}
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <button className="btn primary" type="submit" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : initial ? 'Save race' : 'Add race'}
        </button>
        <button className="btn" type="button" onClick={() => onDone()}>
          Cancel
        </button>
        {save.isError && (
          <span className="note error" style={{ margin: 0 }}>
            {save.error.message}
          </span>
        )}
      </div>
    </form>
  )
}

function Forecast({ r, units, today }: { r: RacePrediction; units: Units; today?: string }) {
  const tri = r.course.kind === 'triathlon'
  const legs = LEGS.filter(([k]) => r.legs[k])
  const share = legs.reduce((s, [k]) => s + r.legs[k]!.p50, 0)
  const total = r.legs.total
  const runLeg = r.legs.run!
  const garmin = r.garmin_prediction
  // the histogram axis is categorical, so mark Garmin's time by its nearest bar
  const garminBin =
    garmin && garmin.time_s >= r.histogram[0].s && garmin.time_s <= r.histogram[r.histogram.length - 1].s
      ? r.histogram.reduce((a, b) => (Math.abs(b.s - garmin.time_s) < Math.abs(a.s - garmin.time_s) ? b : a)).s
      : null
  const course = `${tri ? `${Math.round(r.course.bike_climb_m)} m of bike climbing, ${r.course.wetsuit ? 'wetsuit legal' : 'non-wetsuit swim'}, ` : ''}${r.course.run_temp_c}°C`
  const past = r.race_day != null && today != null && r.race_day < today
  const form = !r.race_day
    ? "Assumes today's fitness, arriving fresh."
    : past
      ? 'Uses the fitness and form you actually had on the day.'
      : `Fitness and form projected to ${raceDate(r.race_day, today, shortDate)}, assuming you taper for it.`
  const label = r.race_type === 'run' ? `${distance(r.course.run_m, 'run', units)} run` : r.course.label
  const conditions = r.race
    ? `${label} on ${raceDate(r.race.day, today)}: ${course}. ${form}`
    : `${label} on a typical course: ${course}. ${form} Add it to your races to use your own course and date.`

  return (
    <>
      <div className="grid">
        <Panel className="span-5" title={r.course.name} note={conditions}>
          <div className="label">Predicted finish (median)</div>
          <div className="finish">{raceTime(total.p50)}</div>
          <p className="mono" style={{ color: 'var(--muted)', margin: '6px 0 16px' }}>
            80% range {raceTime(total.p10)} – {raceTime(total.p90)}
          </p>
          {garmin && (
            <p style={{ margin: '-6px 0 16px' }}>
              Garmin predicts <b>{raceTime(garmin.time_s)}</b>
              {garmin.as_of && <span style={{ color: 'var(--muted)' }}> (as of {shortDate(garmin.as_of)})</span>},{' '}
              {Math.abs(garmin.time_s - total.p50) < total.p50 * 0.01
                ? 'in line with this forecast'
                : `${raceTime(Math.abs(garmin.time_s - total.p50))} ${garmin.time_s < total.p50 ? 'faster' : 'slower'} than this forecast`}
              .
            </p>
          )}
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
          note={`Where the 6,000 simulated finishes landed. The shaded bars are the middle 80%.${garminBin != null ? " The highlighted bar is Garmin's prediction." : ''}`}
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
                  <Cell
                    key={b.s}
                    fill={
                      b.s === garminBin
                        ? 'var(--ink)'
                        : b.s >= total.p10 && b.s <= total.p90
                          ? 'var(--accent)'
                          : 'var(--grid)'
                    }
                  />
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
                  <td className="n">
                    {Math.round(r.inputs.ftp_watts)} W · {r.inputs.sources.ftp}
                  </td>
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
                <td className="n">
                  {pace(r.inputs.run_threshold_speed, 'run', units)} · {r.inputs.sources.run}
                </td>
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
