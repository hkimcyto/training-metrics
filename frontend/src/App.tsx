import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { logout, useMe, useSync } from './api'
import type { Units } from './lib/format'
import Overview from './pages/Overview'

const Load = lazy(() => import('./pages/Load'))
const Race = lazy(() => import('./pages/Race'))
const Performance = lazy(() => import('./pages/Performance'))
const RoutesPage = lazy(() => import('./pages/Routes'))
const WellnessPage = lazy(() => import('./pages/Wellness'))
const Activities = lazy(() => import('./pages/Activities'))
const Settings = lazy(() => import('./pages/Settings'))

const TABS = [
  ['overview', 'Overview'],
  ['load', 'Load & taper'],
  ['race', 'Race forecast'],
  ['performance', 'Performance'],
  ['routes', 'Routes'],
  ['wellness', 'Recovery'],
  ['activities', 'Activities'],
  ['settings', 'Settings'],
] as const
type Tab = (typeof TABS)[number][0]

function useHashTab(): Tab {
  const read = () => {
    const h = window.location.hash.slice(1) as Tab
    return TABS.some(([t]) => t === h) ? h : 'overview'
  }
  const [tab, setTab] = useState<Tab>(read)
  useEffect(() => {
    const on = () => {
      setTab(read())
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return tab
}

function Logo() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--ink)" />
      <path d="M6 21c3-6 6-9 10-9s7 3 10 9" fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
      <circle cx="16" cy="12" r="2.6" fill="var(--bike)" />
    </svg>
  )
}

export default function App() {
  const tab = useHashTab()
  const me = useMe()
  const sync = useSync()
  const qc = useQueryClient()
  const status = me.data?.sync
  const running = status?.state === 'running'
  // when an import finishes, refresh every chart
  const wasRunning = useRef(false)
  useEffect(() => {
    if (wasRunning.current && !running) qc.invalidateQueries()
    wasRunning.current = running
  }, [running, qc])
  // while importing, refresh charts periodically so they fill in as data lands
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'me' }), 20000)
    return () => clearInterval(id)
  }, [running, qc])
  const units: Units = me.data?.measurement ?? 'imperial'
  const race = me.data?.settings.race_date
  const daysOut = race && me.data ? Math.round((Date.parse(race) - Date.parse(me.data.today)) / 864e5) : null

  return (
    <>
      <header className="top">
        <div className="shell">
          <div className="top-row">
            <div className="brand">
              <Logo /> Tri Dash
            </div>
            {me.data && <span className="who">{me.data.name}</span>}
            <span className="spacer" />
            {daysOut !== null && daysOut >= 0 && (
              <span className="countdown">
                <b>{daysOut}</b> days to {me.data?.settings.race_name ?? 'race day'}
              </span>
            )}
            {me.data && !me.data.is_demo && (
              <>
                <button className="btn" onClick={() => sync.mutate()} disabled={sync.isPending || running}>
                  {running ? 'Syncing…' : 'Sync now'}
                </button>
                <button className="btn" onClick={() => logout().then(() => window.location.reload())}>
                  Sign out
                </button>
              </>
            )}
          </div>
          <nav className="tabs" aria-label="Sections">
            {TABS.map(([id, label]) => (
              <a key={id} href={`#${id}`} aria-current={tab === id ? 'page' : undefined}>
                {label}
              </a>
            ))}
          </nav>
        </div>
      </header>

      <div className="shell">
        {me.data?.is_demo && (
          <div className="demo-bar">
            <span>
              <b>Live demo</b>
              {me.data.name === 'Demo Athlete'
                ? "You're viewing a sample athlete. Connect Strava to see your own training."
                : `Real Strava training from ${me.data.name}'s build to ${me.data.settings.race_name ?? 'race day'}. Route start and end points are trimmed for privacy.`}
            </span>
            {me.data.strava_enabled && (
              <a className="btn strava" href="/api/auth/strava/login">
                Connect with Strava
              </a>
            )}
          </div>
        )}
        {me.data && !me.data.is_demo && status && status.state !== 'idle' && (
          <div className="demo-bar" style={status.state === 'error' ? { borderColor: 'var(--bad)' } : undefined}>
            <span>
              <b style={status.state === 'error' ? { color: 'var(--bad)' } : undefined}>
                {status.state === 'error' ? 'Sync error' : 'Importing'}
              </b>
              {status.message}
              {status.total > 0 && ` · ${status.done} of ${status.total}`}
              {status.total === 0 && status.done > 0 && ` · ${status.done} so far`}
              {running && '. Charts fill in as data arrives; the first import can take 10–15 minutes.'}
            </span>
            {status.state === 'error' && (
              <button className="btn" onClick={() => sync.mutate()}>
                Try again
              </button>
            )}
          </div>
        )}
        <main>
          {me.isError && <p className="error">Couldn't reach the API: {me.error.message}</p>}
          <Suspense fallback={<div className="skeleton" />}>
            {tab === 'overview' && <Overview units={units} />}
            {tab === 'load' && <Load />}
            {tab === 'race' && <Race units={units} />}
            {tab === 'performance' && <Performance units={units} />}
            {tab === 'routes' && <RoutesPage units={units} />}
            {tab === 'wellness' && <WellnessPage />}
            {tab === 'activities' && <Activities units={units} />}
            {tab === 'settings' && <Settings />}
          </Suspense>
        </main>
      </div>
    </>
  )
}
