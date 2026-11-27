import { sendJson } from './api.ts'

export type PublicPerformance = {
  season: number
  state: 'ready' | 'collecting'
  scoring: string
  saved: number
  compared: number
  pending: number
  mae: number | null
  within_five_pct: number | null
  model_compared: number
  fallback_compared: number
  last_result_update: string | null
  latest_week: number | null
  latest_week_mae: number | null
  latest_week_compared: number
}

export const getPublicPerformance = () => sendJson<PublicPerformance>('/api/public/performance', undefined, 'GET')
