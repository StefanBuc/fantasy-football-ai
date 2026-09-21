import { useCallback, useEffect, useRef, useState } from 'react'

import {
  getLocalMatchup,
  getMatchup,
  getTeamLogoUrl,
} from '../lib/api'
import type {
  ESPNLeague,
  ESPNTeamSummary,
  MatchupResponse,
  RosterProjection,
  TeamProjectionResponse,
} from '../types/api'

type MatchupViewProps = {
  league: ESPNLeague
  connectionMode: 'public' | 'local'
  selectedTeamId: number
  week: number
  onTeamChange: (teamId: number) => void
  onWeekChange: (week: number) => void
}

const weeks = Array.from({ length: 18 }, (_, index) => index + 1)

const starterSlotOrder = [
  'QB',
  'RB',
  'WR',
  'TE',
  'RB/WR/TE',
  'RB/WR',
  'WR/TE',
  'FLEX',
  'OP',
  'D/ST',
  'K',
]

function displayLineupSlot(slot: string): string {
  if (['RB/WR/TE', 'RB/WR', 'WR/TE'].includes(slot)) {
    return 'FLEX'
  }

  return slot
}

function sortStarters(players: RosterProjection[]): RosterProjection[] {
  return [...players].sort((left, right) => {
    const leftIndex = starterSlotOrder.indexOf(left.lineup_slot)
    const rightIndex = starterSlotOrder.indexOf(right.lineup_slot)

    return (
      (leftIndex < 0 ? 99 : leftIndex)
      - (rightIndex < 0 ? 99 : rightIndex)
    )
  })
}

function projectedTotal(team: TeamProjectionResponse): number {
  return team.players
    .filter((player) => !['BE', 'IR'].includes(player.lineup_slot))
    .reduce(
      (total, player) => total + (player.predicted_points ?? 0),
      0,
    )
}

function TeamLogo({
  team,
  connectionMode,
}: {
  team: ESPNTeamSummary | undefined
  connectionMode: 'public' | 'local'
}) {
  const logoUrl = team
    ? getTeamLogoUrl(team.team_id, team.logo_url, connectionMode)
    : null
  return (
    <div className="relative grid size-16 place-items-center overflow-hidden rounded-full bg-slate-900 font-black text-lime-300 ring-2 ring-white shadow-sm dark:ring-slate-700">
      <span>{team?.abbreviation ?? 'FF'}</span>
      {logoUrl && (
        <img
          src={logoUrl}
          alt=""
          referrerPolicy="no-referrer"
          onError={(event) => {
            event.currentTarget.style.display = 'none'
          }}
          className="absolute inset-0 size-full bg-white object-cover"
        />
      )}
    </div>
  )
}

function MatchupPlayer({ player }: { player: RosterProjection }) {
  return (
    <div className="grid grid-cols-[44px_minmax(0,1fr)_58px] items-center gap-3 border-t border-slate-100 px-4 py-3 first:border-0">
      <span className="text-xs font-black text-slate-400">
        {displayLineupSlot(player.lineup_slot)}
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-bold text-slate-900">
          {player.player_name}
        </p>
        <p className="mt-0.5 text-xs text-slate-500">
          {player.position} · {player.team ?? '—'}
          {player.opponent_team ? ` vs ${player.opponent_team}` : ''}
        </p>
      </div>
      <p className="text-right text-lg font-black tabular-nums text-slate-950">
        {player.predicted_points !== null
          ? player.predicted_points.toFixed(1)
          : '—'}
      </p>
    </div>
  )
}

function MatchupRoster({
  projection,
  team,
  connectionMode,
}: {
  projection: TeamProjectionResponse
  team: ESPNTeamSummary | undefined
  connectionMode: 'public' | 'local'
}) {
  const starters = sortStarters(
    projection.players.filter(
      (player) => !['BE', 'IR'].includes(player.lineup_slot),
    ),
  )
  const bench = projection.players
    .filter((player) => ['BE', 'IR'].includes(player.lineup_slot))
    .sort((left, right) => {
      const leftIsIr = left.lineup_slot === 'IR' ? 1 : 0
      const rightIsIr = right.lineup_slot === 'IR' ? 1 : 0
      return leftIsIr - rightIsIr
    })

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-4 border-b border-slate-200 bg-slate-50/70 p-5">
        <TeamLogo team={team} connectionMode={connectionMode} />
        <div className="min-w-0">
          <h2 className="truncate text-lg font-black text-slate-950">
            {projection.team_name}
          </h2>
          <p className="mt-1 text-xs font-bold uppercase tracking-wider text-slate-400">
            Starting lineup
          </p>
        </div>
      </div>
      {starters.map((player) => (
        <MatchupPlayer key={player.espn_id} player={player} />
      ))}

      <div className="border-y border-slate-200 bg-slate-50 px-4 py-2.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
        Bench
      </div>
      {bench.length > 0 ? (
        bench.map((player) => (
          <MatchupPlayer key={player.espn_id} player={player} />
        ))
      ) : (
        <p className="px-4 py-5 text-sm text-slate-500">
          No bench players.
        </p>
      )}
    </section>
  )
}

export function MatchupView({
  league,
  connectionMode,
  selectedTeamId,
  week,
  onTeamChange,
  onWeekChange,
}: MatchupViewProps) {
  const [matchup, setMatchup] = useState<MatchupResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lastAutomaticRequest = useRef('')

  const loadMatchup = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = connectionMode === 'local'
        ? await getLocalMatchup({ team_id: selectedTeamId, week })
        : await getMatchup({
            league_id: league.league_id,
            season: league.season,
            team_id: selectedTeamId,
            week,
          })
      setMatchup(result)
    } catch (caughtError) {
      setMatchup(null)
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'The matchup could not be loaded.',
      )
    } finally {
      setIsLoading(false)
    }
  }, [connectionMode, league.league_id, league.season, selectedTeamId, week])

  useEffect(() => {
    const requestKey = `${selectedTeamId}:${week}`
    if (lastAutomaticRequest.current === requestKey) {
      return
    }
    lastAutomaticRequest.current = requestKey
    void loadMatchup()
  }, [loadMatchup, selectedTeamId, week])

  const homeTeam = league.teams.find(
    (team) => team.team_id === matchup?.home.team_id,
  )
  const awayTeam = league.teams.find(
    (team) => team.team_id === matchup?.away.team_id,
  )

  return (
    <>
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.14em] text-emerald-700">
              Head-to-head comparison
            </p>
            <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">
              Week {week} matchup
            </h1>
            <p className="mt-2 text-sm text-slate-500">
              Compare both starting lineups using the same AI models.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-[200px_130px_auto]">
            <select
              value={selectedTeamId}
              onChange={(event) => onTeamChange(Number(event.target.value))}
              aria-label="Fantasy team"
              className="h-11 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-emerald-500"
            >
              {league.teams.map((team) => (
                <option key={team.team_id} value={team.team_id}>
                  {team.team_name}
                </option>
              ))}
            </select>
            <select
              value={week}
              onChange={(event) => onWeekChange(Number(event.target.value))}
              aria-label="NFL week"
              className="h-11 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-emerald-500"
            >
              {weeks.map((weekNumber) => (
                <option key={weekNumber} value={weekNumber}>
                  Week {weekNumber}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void loadMatchup()}
              disabled={isLoading}
              className="h-11 rounded-xl bg-emerald-600 px-5 text-sm font-black text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {isLoading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        </div>
      </section>

      {error && (
        <div role="alert" className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-800">
          {error}
        </div>
      )}

      {isLoading && !matchup && (
        <div className="mt-5 rounded-2xl border border-slate-200 bg-white px-6 py-16 text-center">
          <div className="mx-auto size-8 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-600" />
          <p className="mt-4 text-sm font-bold text-slate-600">Projecting both lineups…</p>
        </div>
      )}

      {matchup && (
        <>
          <section className="mt-5 rounded-3xl bg-slate-950 px-5 py-7 text-white shadow-xl sm:px-8">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-5 text-center">
              <div>
                <p className="truncate text-sm font-bold text-slate-300">{matchup.away.team_name}</p>
                <p className="mt-2 text-4xl font-black tabular-nums text-lime-300">
                  {projectedTotal(matchup.away).toFixed(1)}
                </p>
              </div>
              <div>
                <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-500">Projected</p>
                <p className="mt-1 text-lg font-black text-slate-400">VS</p>
              </div>
              <div>
                <p className="truncate text-sm font-bold text-slate-300">{matchup.home.team_name}</p>
                <p className="mt-2 text-4xl font-black tabular-nums text-lime-300">
                  {projectedTotal(matchup.home).toFixed(1)}
                </p>
              </div>
            </div>
            {(matchup.away_score > 0 || matchup.home_score > 0) && (
              <p className="mt-5 text-center text-xs font-semibold text-slate-400">
                ESPN score: {matchup.away_score.toFixed(1)}–{matchup.home_score.toFixed(1)}
              </p>
            )}
          </section>

          <div className="mt-5 grid gap-5 lg:grid-cols-2">
            <MatchupRoster
              projection={matchup.away}
              team={awayTeam}
              connectionMode={connectionMode}
            />
            <MatchupRoster
              projection={matchup.home}
              team={homeTeam}
              connectionMode={connectionMode}
            />
          </div>
        </>
      )}
    </>
  )
}
