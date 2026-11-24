import type {
  AccuracyQuery,
  AccuracyReport,
  AccuracySyncResult,
  AutomationStatus,
  LiveScoreResponse,
  LivePlayerDescriptor,
  ConnectLeagueInput,
  ESPNLeague,
  LeaguePlayersInput,
  LeaguePlayersResponse,
  LocalLeaguePlayersInput,
  LocalTeamProjectionInput,
  MatchupResponse,
  ScoreboardResponse,
  TeamProjectionInput,
  TeamProjectionResponse,
  OptimizedLineupResponse,
} from '../types/api'

const API_BASE_URL = (
  import.meta.env?.VITE_API_BASE_URL ?? ''
).replace(/\/$/, '')

export function getScoreboard(input: LeaguePlayersInput, mode: 'public' | 'local'): Promise<ScoreboardResponse> {
  return postJson<ScoreboardResponse>(
    mode === 'local' ? '/api/espn/local/scoreboard' : '/api/espn/scoreboard',
    mode === 'local' ? { week: input.week } : input,
  )
}

function getErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') {
    return null
  }

  const detail = Reflect.get(payload, 'detail')

  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object') {
          const message = Reflect.get(item, 'msg')
          return typeof message === 'string' ? message : null
        }

        return null
      })
      .filter(Boolean)
      .join(' ')
  }

  return null
}

const pendingRequests = new Map<string, Promise<unknown>>()

function postJson<TResponse>(path: string, body: unknown): Promise<TResponse> {
  const key = JSON.stringify([API_BASE_URL, path, body])
  const existing = pendingRequests.get(key)
  if (existing) return existing as Promise<TResponse>
  const pending: Promise<TResponse> = sendJson<TResponse>(path, body).finally(() => {
    if (pendingRequests.get(key) === pending) pendingRequests.delete(key)
  })
  pendingRequests.set(key, pending)
  return pending
}

async function sendJson<TResponse>(
  path: string,
  body: unknown,
  method: 'POST' | 'GET' = 'POST',
): Promise<TResponse> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
      body: method === 'POST' ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new Error(
      'Could not reach the API. Make sure the backend is running.',
    )
  }

  const payload: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(
      getErrorMessage(payload) ??
        `The API returned status ${response.status}.`,
    )
  }

  return payload as TResponse
}

export function connectLeague(
  input: ConnectLeagueInput,
): Promise<ESPNLeague> {
  return postJson<ESPNLeague>('/api/espn/connect', input)
}

export function getTeamProjections(
  input: TeamProjectionInput,
): Promise<TeamProjectionResponse> {
  return postJson<TeamProjectionResponse>(
    '/api/espn/projections',
    input,
  )
}

export function connectLocalLeague(): Promise<ESPNLeague> {
  return postJson<ESPNLeague>(
    '/api/espn/local/connect',
    {},
  )
}

export function getLocalTeamProjections(
  input: LocalTeamProjectionInput,
): Promise<TeamProjectionResponse> {
  return postJson<TeamProjectionResponse>(
    '/api/espn/local/projections',
    input,
  )
}

export function getMatchup(
  input: TeamProjectionInput,
): Promise<MatchupResponse> {
  return postJson<MatchupResponse>(
    '/api/espn/matchup',
    input,
  )
}

export function getLocalMatchup(
  input: LocalTeamProjectionInput,
): Promise<MatchupResponse> {
  return postJson<MatchupResponse>(
    '/api/espn/local/matchup',
    input,
  )
}

export function getLeaguePlayers(
  input: LeaguePlayersInput,
): Promise<LeaguePlayersResponse> {
  return postJson<LeaguePlayersResponse>(
    '/api/espn/players',
    input,
  )
}

export function getLocalLeaguePlayers(
  input: LocalLeaguePlayersInput,
): Promise<LeaguePlayersResponse> {
  return postJson<LeaguePlayersResponse>(
    '/api/espn/local/players',
    input,
  )
}

export function getTeamLogoUrl(
  teamId: number,
  logoUrl: string | null,
  connectionMode: 'public' | 'local',
): string | null {
  if (!logoUrl) {
    return null
  }

  try {
    const hostname = new URL(logoUrl).hostname
    if (
      connectionMode === 'local'
      && hostname === 'mystique-api.fantasy.espn.com'
    ) {
      return `${API_BASE_URL}/api/espn/local/team-logo/${teamId}`
    }
  } catch {
    return null
  }

  return logoUrl
}

export function getAccuracy(input: AccuracyQuery): Promise<AccuracyReport> {
  const params = new URLSearchParams()
  for (const key of ['league_id', 'week', 'position', 'offset'] as const) {
    const value = input[key]
    if (value !== undefined) params.set(key, String(value))
  }
  return sendJson<AccuracyReport>(`/api/accuracy/${input.season}?${params}`, undefined, 'GET')
}

export function syncAccuracy(season: number, leagueId?: number): Promise<AccuracySyncResult> {
  const query = leagueId === undefined ? '' : `?league_id=${leagueId}`
  return postJson<AccuracySyncResult>(`/api/accuracy/${season}/sync${query}`, {})
}

export function getAutomationStatus(season: number, leagueId?: number): Promise<AutomationStatus> {
  const query = leagueId === undefined ? '' : `?league_id=${leagueId}`
  return sendJson<AutomationStatus>(`/api/accuracy/${season}/automation${query}`, undefined, 'GET')
}

export function getLiveScores(input: { league_id: number; season: number; week: number;
  players: LivePlayerDescriptor[] }, mode: 'public' | 'local'): Promise<LiveScoreResponse> {
  const { week, players } = input
  return postJson<LiveScoreResponse>(mode === 'local' ? '/api/espn/local/live' : '/api/espn/live',
    mode === 'local' ? { week, players } : input)
}

export function getOptimizedLineup(input: TeamProjectionInput & { include_free_agents: boolean },
  mode: 'public' | 'local'): Promise<OptimizedLineupResponse> {
  return postJson<OptimizedLineupResponse>(mode === 'local'
    ? '/api/espn/local/optimized-lineup' : '/api/espn/optimized-lineup', mode === 'local'
    ? { team_id: input.team_id, week: input.week, include_free_agents: input.include_free_agents, refresh: input.refresh ?? false }
    : input)
}
