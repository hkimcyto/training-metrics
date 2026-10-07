import { describe, expect, it } from 'vitest'
import { hms, minSec, pace } from './format'
import { decodePolyline } from './polyline'

describe('decodePolyline', () => {
  it('matches the example in Google’s documentation', () => {
    expect(decodePolyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@')).toEqual([
      [38.5, -120.2],
      [40.7, -120.95],
      [43.252, -126.453],
    ])
  })
})

describe('format', () => {
  it('formats durations', () => {
    expect(hms(3725)).toBe('1:02')
    expect(hms(3725, true)).toBe('1:02:05')
  })
  it('never prints 60 seconds', () => {
    expect(minSec(119.6)).toBe('2:00')
  })
  it('uses each sport’s pace convention', () => {
    expect(pace(4.4704, 'run', 'imperial')).toBe('6:00 /mi')
    expect(pace(1, 'swim', 'metric')).toBe('1:40 /100m')
    expect(pace(10, 'bike', 'metric')).toBe('36.0 km/h')
  })
})
