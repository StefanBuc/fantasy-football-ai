import type { ESPNTeamSummary } from '../types/api'

type MatchupOption = {
  teamId: number
  opponentId: number | null
  label: string
  disabled: boolean
}

export function matchupOptions(
  teams: ESPNTeamSummary[],
  week: number,
  currentOpponents: Record<string, number | null> = {},
): MatchupOption[] {
  const seen = new Set<string>()

  return teams.flatMap<MatchupOption>((team) => {
    const schedule = team.opponents_by_week ?? {}
    const fromScoreboard = Object.hasOwn(currentOpponents, String(team.team_id))
    const opponentId = fromScoreboard
      ? currentOpponents[String(team.team_id)]
      : schedule[String(week)]
    const opponent = teams.find((item) => item.team_id === opponentId)

    if (opponent) {
      const key = [team.team_id, opponent.team_id]
        .sort((left, right) => left - right)
        .join(':')
      if (seen.has(key)) {
        return []
      }
      seen.add(key)
      return [{
        teamId: team.team_id,
        opponentId: opponent.team_id,
        label: `${team.team_name} vs ${opponent.team_name}`,
        disabled: false,
      }]
    }

    const bye = (
      fromScoreboard || Object.hasOwn(schedule, String(week))
    ) && opponentId === null

    return [{
      teamId: team.team_id,
      opponentId: null,
      label: `${team.team_name} vs ${bye ? 'BYE' : 'TBD'}`,
      disabled: bye,
    }]
  })
}
