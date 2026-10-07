/** Decode Google's encoded polyline format, which Strava uses for route maps. */
export function decodePolyline(encoded: string, precision = 5): [number, number][] {
  const coords: [number, number][] = []
  const factor = 10 ** precision
  let index = 0
  let lat = 0
  let lng = 0
  while (index < encoded.length) {
    const deltas: number[] = []
    for (let k = 0; k < 2; k++) {
      let shift = 0
      let result = 0
      let b: number
      do {
        b = encoded.charCodeAt(index++) - 63
        result |= (b & 0x1f) << shift
        shift += 5
      } while (b >= 0x20)
      deltas.push(result & 1 ? ~(result >> 1) : result >> 1)
    }
    lat += deltas[0]
    lng += deltas[1]
    coords.push([lat / factor, lng / factor])
  }
  return coords
}
