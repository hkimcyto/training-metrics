/** Rough city labels for route areas. Only used to name a group of routes. */
const PLACES: [string, number, number][] = [
  ['SF Bay Area', 37.78, -122.35],
  ['San Jose', 37.34, -121.89],
  ['Sacramento', 38.58, -121.49],
  ['San Diego', 32.9, -117.2],
  ['Los Angeles', 34.05, -118.25],
  ['New York', 40.75, -73.98],
  ['Austin', 30.27, -97.74],
  ['Honolulu', 21.31, -157.86],
]

export function placeName(lat: number, lng: number): string | null {
  let best: [string, number] | null = null
  for (const [name, plat, plng] of PLACES) {
    const d = Math.hypot(lat - plat, (lng - plng) * Math.cos((lat * Math.PI) / 180))
    if (d < 0.6 && (!best || d < best[1])) best = [name, d]
  }
  return best?.[0] ?? null
}
