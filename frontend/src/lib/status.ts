/** Training status labels, colours and plain-language meaning, in Garmin's vocabulary. */
export const STATUS: Record<string, { label: string; color: string; meaning: string }> = {
  PEAKING: {
    label: 'Peaking',
    color: 'var(--strength)',
    meaning: 'Fitness is built and fatigue is coming down. You are in race shape.',
  },
  PRODUCTIVE: {
    label: 'Productive',
    color: 'var(--good)',
    meaning: 'Fitness is rising and your load is in a good range. Keep it up.',
  },
  MAINTAINING: {
    label: 'Maintaining',
    color: 'var(--bike)',
    meaning: 'Your load is enough to hold your fitness, not to raise it.',
  },
  RECOVERY: {
    label: 'Recovery',
    color: 'var(--swim)',
    meaning: 'A lighter load is letting your body recover and absorb earlier training.',
  },
  STRAINED: {
    label: 'Strained',
    color: 'var(--warn)',
    meaning: 'Recovery is lagging behind training: HRV is suppressed or fatigue is deep. Ease off for a few days.',
  },
  UNPRODUCTIVE: {
    label: 'Unproductive',
    color: 'var(--bad)',
    meaning: 'Load is normal but fitness is slipping, often from poor sleep, stress or illness.',
  },
  OVERREACHING: {
    label: 'Overreaching',
    color: 'var(--bad)',
    meaning: 'Load is far above what you are used to. Plan recovery before pushing on.',
  },
  DETRAINING: {
    label: 'Detraining',
    color: 'var(--bad)',
    meaning: 'Load has been much lower than usual for a while and fitness is falling.',
  },
  NO_STATUS: {
    label: 'No status',
    color: 'var(--muted)',
    meaning: 'Not enough recent training to judge.',
  },
}

export const statusOf = (key: string | null | undefined) => STATUS[key ?? 'NO_STATUS'] ?? STATUS.NO_STATUS

export const LOAD_STATUS: Record<string, [string, string]> = {
  LOW: ['Low', 'var(--swim)'],
  OPTIMAL: ['Optimal', 'var(--good)'],
  HIGH: ['High', 'var(--bad)'],
  NONE: ['—', 'var(--muted)'],
}

export const HRV_STATUS: Record<string, [string, string]> = {
  BALANCED: ['Balanced', 'var(--good)'],
  UNBALANCED: ['Unbalanced', 'var(--warn)'],
  LOW: ['Low', 'var(--bad)'],
}
