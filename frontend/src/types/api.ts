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
  base_predicted_points: number | null
  predicted_points: number | null
  status: 'projected' | 'skipped'
  projection_method:
    | 'model'
    | 'recent_average'
    | 'position_average'
    | null
  history_games: number | null
  injury_context_used: boolean
  unavailable_teammates: number
  is_on_bye: boolean
  injury_status: string | null
  availability:
    | 'healthy'
    | 'questionable'
    | 'doubtful'
    | 'unavailable'
    | 'unknown'
  adjustment_reason: string | null
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
  generated_at: string
  cache_hit: boolean
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

export type LeaguePlayer = {
  espn_id: number
  player_name: string
  position: string
  team: string | null
  roster_status: 'available' | 'rostered'
  fantasy_team_id: number | null
  fantasy_team_name: string | null
  percent_owned: number | null
  percent_started: number | null
  season_average: number | null
  opponent_team: string | null
  base_predicted_points: number | null
  predicted_points: number | null
  projection_status: 'projected' | 'skipped'
  projection_method:
    | 'model'
    | 'recent_average'
    | 'position_average'
    | null
  history_games: number | null
  projection_reason: string | null
  is_on_bye: boolean
  injury_status: string | null
  availability:
    | 'healthy'
    | 'questionable'
    | 'doubtful'
    | 'unavailable'
    | 'unknown'
}

export type LeaguePlayersResponse = {
  league_id: number
  season: number
  week: number
  roster_week: number
  player_count: number
  available_count: number
  rostered_count: number
  players: LeaguePlayer[]
}

export type ConnectLeagueInput = {
  league_id: number
  season: number
}

export type TeamProjectionInput = ConnectLeagueInput & {
  refresh?: boolean
  team_id: number
  week: number
}

export type LocalTeamProjectionInput = {
  refresh?: boolean
  team_id: number
  week: number
}

export type LeaguePlayersInput = ConnectLeagueInput & {
  week: number
}

export type LocalLeaguePlayersInput = {
  week: number
}
