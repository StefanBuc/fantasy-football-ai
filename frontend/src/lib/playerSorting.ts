import { scoreDisplay } from './scoreDisplay.ts'
import type { LeaguePlayer, LivePlayerScore } from '../types/api'

export type PlayerSortOption = 'projection' | 'season_average' | 'current_score'

export function sortPlayers(
  players: LeaguePlayer[],
  sortBy: PlayerSortOption,
  liveScores: Map<number, LivePlayerScore>,
): LeaguePlayer[] {
  const value = (player: LeaguePlayer) => {
    if (sortBy === 'current_score') {
      return scoreDisplay(player, liveScores.get(player.espn_id)).actual
    }
    return sortBy === 'projection' ? player.predicted_points : player.season_average
  }

  return [...players].sort((left, right) => {
    const leftValue = value(left)
    const rightValue = value(right)
    if (leftValue == null && rightValue != null) return 1
    if (rightValue == null && leftValue != null) return -1
    const difference = (rightValue ?? 0) - (leftValue ?? 0)
    return difference || left.player_name.localeCompare(right.player_name)
  })
}
