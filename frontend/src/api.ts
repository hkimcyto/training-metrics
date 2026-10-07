import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  Activity,
  Dashboard,
  EfficiencyTrend,
  Me,
  Pmc,
  PowerCurve,
  RacePrediction,
  RouteRow,
  Wellness,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: 'include', ...init })
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, String(detail))
  }
  return r.json() as Promise<T>
}

const get =
  <T>(path: string) =>
  () =>
    request<T>(path)

/** Polls every few seconds while a Strava import is running. */
export const useMe = () =>
  useQuery({
    queryKey: ['me'],
    queryFn: get<Me>('/me'),
    refetchInterval: (q) => (q.state.data?.sync?.state === 'running' ? 4000 : false),
  })
export const useDashboard = (weeks = 12) =>
  useQuery({ queryKey: ['dashboard', weeks], queryFn: get<Dashboard>(`/dashboard?weeks=${weeks}`) })
export const usePmc = (days = 150) => useQuery({ queryKey: ['pmc', days], queryFn: get<Pmc>(`/pmc?days=${days}`) })
export const useRace = () => useQuery({ queryKey: ['race'], queryFn: get<RacePrediction>('/race/prediction') })
export const usePowerCurve = (days = 90) =>
  useQuery({ queryKey: ['power', days], queryFn: get<PowerCurve>(`/power-curve?days=${days}`) })
export const useEfficiency = () => useQuery({ queryKey: ['eff'], queryFn: get<EfficiencyTrend>('/efficiency') })
export const useCalendar = () =>
  useQuery({ queryKey: ['calendar'], queryFn: get<{ day: string; tss: number }[]>('/calendar') })
export const useRoutes = (days = 180) =>
  useQuery({ queryKey: ['routes', days], queryFn: get<RouteRow[]>(`/routes?days=${days}`) })
export const useWellness = (days = 90) =>
  useQuery({ queryKey: ['wellness', days], queryFn: get<Wellness>(`/wellness?days=${days}`) })
export const useActivities = (sport: string, offset: number, limit = 20) =>
  useQuery({
    queryKey: ['activities', sport, offset, limit],
    queryFn: get<{ total: number; items: Activity[] }>(
      `/activities?limit=${limit}&offset=${offset}${sport ? `&sport=${sport}` : ''}`,
    ),
    placeholderData: (prev) => prev,
  })

export function useSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => request<{ status: string }>('/sync', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
}

export function useSaveSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Me['settings']>) =>
      request('/me/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries(),
  })
}

export function useGarminImport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return request<{ days_imported: number; first: string; last: string }>('/wellness/garmin-import', {
        method: 'POST',
        body: fd,
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wellness'] }),
  })
}

export const logout = () => request('/auth/logout', { method: 'POST' })
