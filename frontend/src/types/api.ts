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
  opponents_by_week?: Record<string, number | null>
}

export type ESPNLeague = {
  league_id: number
  season: number
  current_week: number
  league_name: string
  team_count: number
  teams: ESPNTeamSummary[]
}

export type ProjectionDisplay = {
  floor_points?: number | null
  ceiling_points?: number | null
  range_note?: string | null
  kickoff_at?: string | null
  prediction_saved?: boolean
  pregame_predicted_points?: number | null
}

export type RosterProjection = ProjectionDisplay & {
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

export type ScoreboardMatchup = {
  home_team_id: number
  home_team_name: string
  home_score: number
  away_team_id: number
  away_team_name: string
  away_score: number
}

export type MatchupResponse = {
  opponents_by_team?: Record<string, number | null>
  scoreboard?: ScoreboardMatchup[]
  home_win_pct: number | null
  away_win_pct: number | null
  win_probability_note: string
  league_id: number
  league_name: string
  season: number
  week: number
  home_score: number
  away_score: number
  home: TeamProjectionResponse
  away: TeamProjectionResponse
}

export type LeaguePlayer = ProjectionDisplay & {
  player_id?: string | null
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

export type AccuracyMetrics = {
  saved: number
  scored: number
  pending: number
  mae: number | null
  bias: number | null
}

export type AccuracyRecord = {
  season: number
  week: number
  player_id: string
  player_name: string | null
  position: string
  team: string
  opponent_team: string
  predicted_points: number
  actual_points: number | null
  error: number | null
  projection_method: string
  model_version: string
  model_revision: string
  generated_at: string
  recorded_at: string
  kickoff: string
  actual_updated_at: string | null
}

export type AccuracyReport = {
  season: number
  scoring: string
  summary: AccuracyMetrics
  by_position: (AccuracyMetrics & { position: string })[]
  by_model: (AccuracyMetrics & { model_version: string; model_revision: string; projection_method: string })[]
  weekly_trend: (AccuracyMetrics & { week: number })[]
  records: AccuracyRecord[]
  limit: number
  offset: number
}

export type AccuracyQuery = {
  season: number
  league_id?: number
  week?: number
  position?: string
  offset?: number
}

export type AccuracySyncResult = { updated_count: number; checked_count: number }

export type AutomationJob = {
  week: number | null
  state: 'running' | 'success' | 'error'
  last_started_at: string | null
  last_finished_at: string | null
  last_success_at: string | null
  last_error: string | null
  next_run_at: string | null
  result: Record<string, number> | null
}

export type AutomationStatus = {
  enabled: boolean
  registered: boolean
  capture_enabled: boolean
  note: string
  last_checked_at: string | null
  worker_error: string | null
  capture: AutomationJob | null
  sync: AutomationJob | null
  poll_seconds: number
  capture_interval_minutes: number
  capture_window_hours: number
  sync_interval_hours: number
}

export type LivePlayerDescriptor = {
  espn_id: number
  player_id?: string | null
  position: string
  team: string | null
}

export type LivePlayerScore = ProjectionDisplay & {
  espn_id: number
  game_state: 'pregame' | 'live' | 'final' | 'postponed' | 'bye' | 'unknown'
  live_points: number | null
  game_detail: string | null
}

export type LiveScoreResponse = {
  season: number
  week: number
  checked_at: string
  note: string
  players: LivePlayerScore[]
}
