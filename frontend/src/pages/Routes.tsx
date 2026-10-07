import type { LatLngBoundsExpression } from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { MapContainer, Polyline, TileLayer, Tooltip as LTooltip, useMap } from 'react-leaflet'
import { useRoutes } from '../api'
import { Dot, Kpi, Panel, Q, Seg } from '../components/ui'
import type { Units } from '../lib/format'
import { distance, shortDate } from '../lib/format'
import { placeName } from '../lib/places'
import { decodePolyline } from '../lib/polyline'
import type { RouteRow } from '../types'

const dark = () => window.matchMedia?.('(prefers-color-scheme: dark)').matches

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression | null }) {
  const map = useMap()
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [24, 24] })
  }, [bounds, map])
  return null
}

export default function Routes({ units }: { units: Units }) {
  const [days, setDays] = useState(180)
  const [sport, setSport] = useState<'all' | 'bike' | 'run'>('all')
  const [selected, setSelected] = useState<number | null>(null)
  const routes = useRoutes(days)

  const decoded = useMemo(
    () => (routes.data ?? []).map((r) => ({ ...r, pts: decodePolyline(r.polyline) })).filter((r) => r.pts.length > 1),
    [routes.data],
  )
  // Group routes into areas (~50 km cells) so the map frames one place at a time
  // instead of zooming out to fit every trip.
  const areas = useMemo(() => {
    const groups = new Map<string, { key: string; lat: number; lng: number; n: number }>()
    for (const r of decoded) {
      const [lat, lng] = r.pts[Math.floor(r.pts.length / 2)]
      const key = placeName(lat, lng) ?? `${Math.round(lat * 2) / 2},${Math.round(lng * 2) / 2}`
      const g = groups.get(key) ?? { key, lat, lng, n: 0 }
      g.n += 1
      groups.set(key, g)
    }
    return [...groups.values()].sort((a, b) => b.n - a.n)
  }, [decoded])
  const [area, setArea] = useState<string | null>(null)
  const activeArea = area ?? areas[0]?.key ?? null
  const areaOf = (pts: [number, number][]) => {
    const [lat, lng] = pts[Math.floor(pts.length / 2)]
    return placeName(lat, lng) ?? `${Math.round(lat * 2) / 2},${Math.round(lng * 2) / 2}`
  }

  const shown = useMemo(
    () =>
      decoded.filter(
        (r) => (sport === 'all' || r.sport === sport) && (activeArea === null || areaOf(r.pts) === activeArea),
      ),
    [decoded, sport, activeArea],
  )
  const bounds = useMemo<LatLngBoundsExpression | null>(() => {
    const pts = shown.flatMap((r) => r.pts)
    if (!pts.length) return null
    const lats = pts.map((p) => p[0])
    const lngs = pts.map((p) => p[1])
    return [
      [Math.min(...lats), Math.min(...lngs)],
      [Math.max(...lats), Math.max(...lngs)],
    ]
  }, [shown])

  const tiles = dark()
    ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Routes</h1>
          <p className="lede">
            Every outdoor ride and run, layered. Roads you train on most build up into the brightest lines.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Seg
            label="Sport"
            value={sport}
            onChange={setSport}
            options={[
              ['all', 'All'],
              ['bike', 'Rides'],
              ['run', 'Runs'],
            ]}
          />
          <Seg
            label="Range"
            value={days}
            onChange={setDays}
            options={[
              [42, '6 wk'],
              [180, '6 mo'],
              [730, '2 yr'],
            ]}
          />
        </div>
      </div>

      {areas.length > 1 && (
        <div className="legend" style={{ gap: 6 }} role="group" aria-label="Area">
          {areas.slice(0, 6).map((a, i) => (
            <button
              key={a.key}
              className="btn"
              aria-pressed={a.key === activeArea}
              style={a.key === activeArea ? { borderColor: 'var(--accent)', color: 'var(--ink)' } : undefined}
              onClick={() => {
                setArea(a.key)
                setSelected(null)
              }}
            >
              {placeName(a.lat, a.lng) ?? `Area ${i + 1}`} · {a.n} {a.n === 1 ? 'route' : 'routes'}
            </button>
          ))}
        </div>
      )}

      <Q q={routes} height={110}>
        {() => {
          const rides = shown.filter((r) => r.sport === 'bike')
          const runs = shown.filter((r) => r.sport === 'run')
          const sum = (rs: RouteRow[]) => rs.reduce((s, r) => s + r.distance_m, 0)
          return (
            <div className="kpis">
              <Kpi
                label="Outdoor sessions"
                value={shown.length}
                detail={`${rides.length} rides · ${runs.length} runs`}
              />
              <Kpi
                label={
                  <>
                    <Dot sport="bike" />
                    Ridden outdoors
                  </>
                }
                value={distance(sum(rides), 'bike', units).split(' ')[0]}
                unit={units === 'imperial' ? 'mi' : 'km'}
              />
              <Kpi
                label={
                  <>
                    <Dot sport="run" />
                    Run outdoors
                  </>
                }
                value={distance(sum(runs), 'run', units).split(' ')[0]}
                unit={units === 'imperial' ? 'mi' : 'km'}
              />
            </div>
          )
        }}
      </Q>

      <div className="grid">
        <Panel
          className="span-8"
          title="Route map"
          note="Indoor sessions (Zwift, treadmill, pool) have no GPS and aren't shown."
        >
          <Q q={routes} height={560}>
            {() => (
              <div className="map">
                <MapContainer center={[37.78, -122.45]} zoom={11} style={{ height: '100%' }} scrollWheelZoom={false}>
                  <TileLayer
                    url={tiles}
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
                  />
                  <FitBounds bounds={bounds} />
                  {shown.map((r) => (
                    <Polyline
                      key={r.id}
                      positions={r.pts}
                      pathOptions={{
                        color: r.sport === 'bike' ? (dark() ? '#e0b13f' : '#b07f08') : dark() ? '#e8708a' : '#c0405a',
                        weight: selected === r.id ? 5 : 2.5,
                        opacity: selected === null ? 0.35 : selected === r.id ? 1 : 0.12,
                      }}
                      eventHandlers={{ click: () => setSelected(selected === r.id ? null : r.id) }}
                    >
                      <LTooltip sticky>
                        {r.name} · {shortDate(r.day)} · {distance(r.distance_m, r.sport, units)}
                      </LTooltip>
                    </Polyline>
                  ))}
                </MapContainer>
              </div>
            )}
          </Q>
        </Panel>
        <Panel
          className="span-4"
          title="Sessions"
          aside={
            selected !== null && (
              <button className="btn" onClick={() => setSelected(null)}>
                Show all
              </button>
            )
          }
        >
          <div className="tablewrap" style={{ maxHeight: 560, overflowY: 'auto' }}>
            <table>
              <tbody>
                {[...shown]
                  .sort((a, b) => b.day.localeCompare(a.day))
                  .map((r) => (
                    <tr
                      key={r.id}
                      className="clickable"
                      onClick={() => setSelected(selected === r.id ? null : r.id)}
                      style={selected === r.id ? { background: 'var(--surface-2)' } : undefined}
                    >
                      <td className="n">{shortDate(r.day)}</td>
                      <td style={{ whiteSpace: 'normal' }}>
                        <Dot sport={r.sport} />
                        {r.name}
                      </td>
                      <td className="n">{distance(r.distance_m, r.sport, units)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
  )
}
