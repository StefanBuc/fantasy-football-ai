export type ESPNTeamSummary = {
  team_id: number
  team_name: string
  abbreviation: string
  logo_url: string | null
}

export type ESPNLeague = {
  league_id: number
  season: number
  league_name: string
  team_count: number
  teams: ESPNTeamSummary[]
}

export type RosterProjection = {
  espn_id: number
  player_id: string | null
  player_name: string
  position: string
  lineup_slot: string
  team: string | null
  opponent_team: string | null
  predicted_points: number | null
  status: 'projected' | 'skipped'
  reason: string | null
}

export type TeamProjectionResponse = {
  league_id: number
  league_name: string
  season: number
  week: number
  team_id: number
  team_name: string
  projected_count: number
  skipped_count: number
  players: RosterProjection[]
}

export type ConnectLeagueInput = {
  league_id: number
  season: number
}

export type TeamProjectionInput = ConnectLeagueInput & {
  team_id: number
  week: number
}

export type LocalTeamProjectionInput = {
  team_id: number
  week: number
}
