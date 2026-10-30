import type {
  ConnectLeagueInput,
  ESPNLeague,
  LeaguePlayersInput,
  LeaguePlayersResponse,
  LocalLeaguePlayersInput,
  LocalTeamProjectionInput,
  MatchupResponse,
  TeamProjectionInput,
  TeamProjectionResponse,
} from '../types/api'

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? ''
).replace(/\/$/, '')

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

async function postJson<TResponse>(
  path: string,
  body: unknown,
): Promise<TResponse> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
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
