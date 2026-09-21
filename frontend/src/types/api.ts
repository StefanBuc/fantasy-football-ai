export type ESPNTeamSummary = {
  team_id: number
  team_name: string
  abbreviation: string
  logo_url: string | null
  standing: number
  wins: number
  losses: number
  ties: number
  points_for: number
  points_against: number
  streak: string | null
  playoff_pct: number | null
}

export type ESPNLeague = {
  league_id: number
  season: number
  current_week: number
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
  roster_week: number
  team_id: number
  team_name: string
  projected_count: number
  skipped_count: number
  players: RosterProjection[]
}

export type MatchupResponse = {
  league_id: number
  league_name: string
  season: number
  week: number
  home_score: number
  away_score: number
  home: TeamProjectionResponse
  away: TeamProjectionResponse
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
