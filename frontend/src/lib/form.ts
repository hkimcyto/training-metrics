/** Label and colour for a form (TSB) value. */
export function formState(tsb: number): [string, string] {
  if (tsb > 25) return ['Very fresh', 'var(--swim)']
  if (tsb > 5) return ['Fresh', 'var(--good)']
  if (tsb > -10) return ['Neutral', 'var(--muted)']
  if (tsb > -30) return ['Productive', 'var(--warn)']
  return ['Overreaching', 'var(--bad)']
}

export const SPORT_COLOR: Record<string, string> = {
  swim: 'var(--swim)',
  bike: 'var(--bike)',
  run: 'var(--run)',
  strength: 'var(--strength)',
  other: 'var(--muted)',
}
