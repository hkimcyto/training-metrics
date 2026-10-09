export type Units = 'imperial' | 'metric'

const MI = 1609.344
const YD = 0.9144

export function hms(seconds: number, withSeconds = false): string {
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const mm = String(m).padStart(2, '0')
  return withSeconds ? `${h}:${mm}:${String(sec).padStart(2, '0')}` : `${h}:${mm}`
}

/** A finish time at the precision the race needs: 5:12 for a mile, 1:19:39 for a half, 10:13 for an Ironman. */
export function raceTime(seconds: number): string {
  if (seconds < 3600) return minSec(seconds)
  return hms(seconds, seconds < 5 * 3600)
}

export function minSec(seconds: number): string {
  let m = Math.floor(seconds / 60)
  let s = Math.round(seconds % 60)
  if (s === 60) {
    m += 1
    s = 0
  }
  return `${m}:${String(s).padStart(2, '0')}`
}

export function distance(m: number, sport: string, u: Units): string {
  if (sport === 'swim') {
    return u === 'imperial' ? `${Math.round(m / YD).toLocaleString()} yd` : `${Math.round(m).toLocaleString()} m`
  }
  return u === 'imperial' ? `${(m / MI).toFixed(1)} mi` : `${(m / 1000).toFixed(1)} km`
}

export function distanceValue(m: number, sport: string, u: Units): { value: string; unit: string } {
  const [value, unit] = distance(m, sport, u).split(' ')
  return { value, unit }
}

/** Pace in the convention each sport uses: per 100 yd/m, per mile/km, or speed for bikes. */
export function pace(speed: number | null | undefined, sport: string, u: Units): string {
  if (!speed) return '—'
  if (sport === 'swim')
    return `${minSec((u === 'imperial' ? 100 * YD : 100) / speed)} /100${u === 'imperial' ? 'yd' : 'm'}`
  if (sport === 'run') return `${minSec((u === 'imperial' ? MI : 1000) / speed)} /${u === 'imperial' ? 'mi' : 'km'}`
  return u === 'imperial' ? `${((speed * 3600) / MI).toFixed(1)} mph` : `${(speed * 3.6).toFixed(1)} km/h`
}

export function shortDate(iso: string): string {
  const d = new Date(iso + (iso.length === 10 ? 'T12:00:00' : ''))
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function weekday(iso: string): string {
  const d = new Date(iso + (iso.length === 10 ? 'T12:00:00' : ''))
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'numeric', day: 'numeric' })
}

export function signed(n: number, digits = 0): string {
  const v = n.toFixed(digits)
  return n > 0 ? `+${v}` : v
}

export const SPORT_LABEL: Record<string, string> = {
  swim: 'Swim',
  bike: 'Bike',
  run: 'Run',
  strength: 'Strength',
  other: 'Other',
}
