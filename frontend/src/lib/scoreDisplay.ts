import type { ProjectionDisplay, LivePlayerScore, RosterProjection } from '../types/api'

type PlayerScore = ProjectionDisplay & { predicted_points: number | null; is_on_bye?: boolean }

export function scoreDisplay(player: PlayerScore, live?: LivePlayerScore, now = Date.now()) {
  const kickoff = live?.kickoff_at ?? player.kickoff_at
  const startedByClock = !!kickoff && new Date(kickoff).getTime() <= now
  const state = live?.game_state ?? 'unknown'
  const started = ['live', 'final', 'postponed'].includes(state)
    || state === 'unknown' && startedByClock
  const frozen = live?.prediction_saved ? live : player.prediction_saved ? player : null
  const prediction = started ? frozen?.pregame_predicted_points ?? null
    : frozen?.pregame_predicted_points ?? player.predicted_points
  return {
    started,
    state,
    prediction,
    actual: started && (state === 'live' || state === 'final') ? live?.live_points ?? null : null,
    floor: started ? null : frozen ? frozen.floor_points ?? null : player.floor_points ?? null,
    ceiling: started ? null : frozen ? frozen.ceiling_points ?? null : player.ceiling_points ?? null,
    rangeNote: frozen?.range_note ?? player.range_note,
    bye: player.is_on_bye || state === 'bye',
  }
}

export function teamScoreDisplay(players: RosterProjection[], live: Map<number, LivePlayerScore>) {
  const starters = players.filter((player) => !['BE', 'IR'].includes(player.lineup_slot))
  const scores = starters.map((player) => scoreDisplay(player, live.get(player.espn_id)))
  const started = scores.some((score) => score.started)
  return { started,
    actual: started && scores.every((score) => !score.started || score.actual !== null)
      ? scores.reduce((sum, score) => sum + (score.actual ?? 0), 0) : null,
    prediction: scores.length > 0 && scores.every((score) => score.prediction !== null || score.bye)
      ? scores.reduce((sum, score) => sum + (score.bye ? 0 : score.prediction ?? 0), 0) : null,
    final: scores.length > 0 && scores.every((score) => score.state === 'final' || score.bye),
  }
}
