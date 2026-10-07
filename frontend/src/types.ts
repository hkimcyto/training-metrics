export type Sport = 'swim' | 'bike' | 'run' | 'strength' | 'other'

export interface Me {
  id: number
  name: string
  is_demo: boolean
  measurement: 'imperial' | 'metric'
  strava_enabled: boolean
  last_synced_at: string | null
  today: string
  settings: {
    weight_kg: number
    ftp_watts: number | null
    run_threshold_speed: number | null
    css_speed: number | null
    max_hr: number | null
    rest_hr: number | null
    lthr: number | null
    race_name: string | null
    race_date: string | null
    race_climb_m: number
    race_wetsuit: boolean
    race_temp_c: number
  }
  thresholds: {
    ftp_watts: number
    run_threshold_speed: number
    css_speed: number
    lthr: number
    max_hr: number
    rest_hr: number
    sources: Record<string, string>
  }
}

export interface Week {
  week: string
  swim_s: number
  bike_s: number
  run_s: number
  swim_m: number
  bike_m: number
  run_m: number
  strength_sessions: number
  tss: number
  longest_ride_s: number
  longest_run_s: number
}

export interface Activity {
  id: number
  name: string
  sport: Sport
  sport_type: string
  start_time: string
  day: string
  trainer: boolean
  moving_s: number
  distance_m: number
  elev_gain_m: number
  avg_speed: number | null
  avg_hr: number | null
  max_hr: number | null
  avg_watts: number | null
  np_watts: number | null
  tss: number
  tss_method: string
  intensity: number | null
  ef: number | null
  decoupling_pct: number | null
  has_map: boolean
}

export interface Dashboard {
  weeks: Week[]
  records: Partial<Record<'swim' | 'bike' | 'run', Activity>>
}

export interface PmcPoint {
  day: string
  tss: number
  ctl: number
  atl: number
  tsb: number
  ramp?: number
}

export interface Pmc {
  series: PmcPoint[]
  acwr: number | null
  model: {
    personalised: boolean
    tau_fitness: number
    tau_fatigue: number
    k_ratio: number | null
    r2: number
    observations: number
    markers: { day: string; z: number }[]
  } | null
  forecast: {
    race_date: string
    race_name: string | null
    taper_days: number
    taper_reduction: number
    gain_vs_no_taper: number
    race_day: { ctl: number; atl: number; tsb: number }
    days: PmcPoint[]
    grid: { days: number; reduction: number; gain: number }[]
  } | null
}

export interface Leg {
  p10: number
  p50: number
  p90: number
}

export interface RacePrediction {
  course: {
    name: string
    swim_m: number
    bike_m: number
    run_m: number
    bike_climb_m: number
    wetsuit: boolean
    run_temp_c: number
  }
  inputs: {
    ftp_watts: number
    run_threshold_speed: number
    css_speed: number
    race_day_ctl: number
    race_day_tsb: number
    longest_run_8wk_m: number
    longest_ride_8wk_s: number
    sources: Record<string, string>
  }
  legs: Record<'total' | 'swim' | 't1' | 'bike' | 't2' | 'run', Leg>
  bike_avg_watts: number
  bike_avg_speed: number
  run_pace_s_per_km: number
  histogram: { hours: number; count: number }[]
  drivers: { bike_intensity_factor: number; run_durability: number; form_multiplier: number }
}

export interface PowerCurve {
  recent: { s: number; w: number }[]
  all_time: { s: number; w: number }[]
  cp: { cp: number; w_prime: number; ftp_estimate: number; r2: number } | null
  weight_kg: number
}

export interface EfficiencyTrend {
  points: { day: string; sport: 'bike' | 'run'; ef: number; decoupling: number | null; name: string }[]
  trend: Partial<Record<'bike' | 'run', { pct_per_4wk: number; start: number; end: number }>>
}

export interface RouteRow {
  id: number
  sport: Sport
  name: string
  day: string
  distance_m: number
  polyline: string
}

export interface WellnessDay {
  day: string
  sleep_h: number | null
  sleep_score: number | null
  hrv_ms: number | null
  hrv_baseline: number | null
  hrv_sd: number | null
  hrv_status: 'low' | 'balanced' | 'high' | null
  rest_hr: number | null
  body_battery_high: number | null
  stress_avg: number | null
}

export interface Wellness {
  days: WellnessDay[]
  insights: { hrv_vs_prior_day_tss: number | null; rhr_vs_prior_day_tss: number | null; nights: number } | null
}
