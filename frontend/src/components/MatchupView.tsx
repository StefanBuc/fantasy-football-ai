import { useCallback, useEffect, useRef, useState } from 'react'
import { ProjectionFreshness } from './ProjectionFreshness'
import { viewCache, viewKey } from '../lib/viewCache'
import { PlayerScore, LiveScoreNote } from './PlayerScore'
import { useLiveScores } from '../lib/useLiveScores'
import { teamScoreDisplay } from '../lib/scoreDisplay'
import { matchupOptions } from '../lib/matchupOptions'

import {
  getLocalMatchup,
  getMatchup,
  getScoreboard,
  getTeamLogoUrl,
} from '../lib/api'
import type {
  ESPNLeague,
  ESPNTeamSummary,
  MatchupResponse,
  RosterProjection,
  TeamProjectionResponse,
  LivePlayerScore,
  ScoreboardResponse,
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

function TeamScore({ team, liveScores }: { team: TeamProjectionResponse; liveScores: Map<number, LivePlayerScore> }) {
  const score = teamScoreDisplay(team.players, liveScores)
  const format = (value: number | null) => value === null ? '—' : value.toFixed(1)
  return <div>
    <p className="mt-2 text-xs font-bold text-slate-400">{score.started ? score.final ? 'Final · ESPN' : score.actual === null ? 'ESPN score' : 'Live · ESPN' : 'AI projected'}</p>
    <p className="mt-1 text-4xl font-black tabular-nums text-lime-300">{format(score.started ? score.actual : score.prediction)}</p>
    {score.started && <p className="mt-2 text-sm font-bold text-slate-300">AI pregame {format(score.prediction)}</p>}
  </div>
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

function MatchupPlayer({ player, live }: { player: RosterProjection; live?: LivePlayerScore }) {
  const showInjury = player.availability !== 'healthy'
  const fallbackLabel = player.projection_method === 'recent_average'
    ? `${player.history_games ?? 0}-game avg`
    : player.projection_method === 'position_average'
      ? 'Position avg'
      : null
  const injuryContextLabel = (
    player.injury_context_used
    && player.unavailable_teammates > 0
  )
    ? `${player.unavailable_teammates} teammate out`
    : null

  return (
    <div className="grid grid-cols-[44px_minmax(0,1fr)_100px] items-center gap-3 border-t border-slate-100 px-4 py-3 first:border-0">
      <span className="text-xs font-black text-slate-400">
        {displayLineupSlot(player.lineup_slot)}
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-bold text-slate-900">
          {player.player_name}
          {player.is_on_bye && (
            <span className="ml-2 inline-flex rounded bg-sky-100 px-1.5 py-0.5 align-middle text-[9px] font-black uppercase tracking-wide text-sky-800 dark:bg-sky-950 dark:text-sky-200">
              BYE
            </span>
          )}
          {showInjury && (
            <span
              title={player.adjustment_reason ?? undefined}
              className={`ml-2 inline-flex rounded px-1.5 py-0.5 align-middle text-[9px] font-black uppercase tracking-wide ${
                player.availability === 'unavailable'
                  ? 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200'
                  : player.availability === 'doubtful'
                    ? 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200'
                    : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200'
              }`}
            >
              {player.injury_status ?? 'Injury'}
            </span>
          )}
          {fallbackLabel && (
            <span
              title={
                player.projection_method === 'recent_average'
                  ? 'Limited-history fallback projection'
                  : 'No-history position-average projection'
              }
              className="ml-2 inline-flex rounded bg-amber-100 px-1.5 py-0.5 align-middle text-[9px] font-black uppercase tracking-wide text-amber-800 dark:bg-amber-950 dark:text-amber-200"
            >
              {fallbackLabel}
            </span>
          )}
          {injuryContextLabel && (
            <span
              title="The model included unavailable-teammate opportunity context."
              className="ml-2 inline-flex rounded bg-sky-100 px-1.5 py-0.5 align-middle text-[9px] font-black uppercase tracking-wide text-sky-800 dark:bg-sky-950 dark:text-sky-200"
            >
              {injuryContextLabel}
            </span>
          )}
        </p>
        <p className="mt-0.5 text-xs text-slate-500">
          {player.position} · {player.team ?? '—'}
          {player.is_on_bye
            ? ' · BYE'
            : player.opponent_team
              ? ` vs ${player.opponent_team}`
              : ''}
        </p>
      </div>
      <PlayerScore player={player} live={live} />
    </div>
  )
}

function MatchupRoster({
  projection,
  team,
  connectionMode,
  liveScores,
}: {
  projection: TeamProjectionResponse
  team: ESPNTeamSummary | undefined
  connectionMode: 'public' | 'local'
  liveScores: Map<number, LivePlayerScore>
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
        <MatchupPlayer key={player.espn_id} player={player} live={liveScores.get(player.espn_id)} />
      ))}

      <div className="border-y border-slate-200 bg-slate-50 px-4 py-2.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
        Bench
      </div>
      {bench.length > 0 ? (
        bench.map((player) => (
          <MatchupPlayer key={player.espn_id} player={player} live={liveScores.get(player.espn_id)} />
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
  const cacheKey = viewKey('matchup', connectionMode, league.league_id, league.season, week, selectedTeamId)
  const [matchup, setMatchup] = useState<MatchupResponse | null>(() => viewCache.read(cacheKey))
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestVersion = useRef(0)
  const [isRefreshingData, setIsRefreshingData] = useState(false)
  const [scoreboardState, setScoreboardState] = useState<{
    key: string; data: ScoreboardResponse | null; error: string | null
  } | null>(null)
  const scoreboardKey = JSON.stringify([connectionMode, league.league_id, league.season, week])
  const currentScoreboard = scoreboardState?.key === scoreboardKey ? scoreboardState : null

  useEffect(() => {
    let cancelled = false
    let pending = false
    async function update() {
      if (pending || document.hidden) return
      pending = true
      try {
        const data = await getScoreboard({ league_id: league.league_id, season: league.season, week }, connectionMode)
        if (!cancelled) setScoreboardState({ key: scoreboardKey, data, error: null })
      } catch (caught) {
        if (!cancelled) setScoreboardState((previous) => ({
          key: scoreboardKey,
          data: previous?.key === scoreboardKey ? previous.data : null,
          error: caught instanceof Error ? caught.message : 'Scoreboard could not be updated.',
        }))
      } finally {
        pending = false
      }
    }
    void update()
    const timer = window.setInterval(() => { void update() }, 30_000)
    const visible = () => { if (!document.hidden) void update() }
    document.addEventListener('visibilitychange', visible)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [connectionMode, league.league_id, league.season, week, scoreboardKey])

  const loadMatchup = useCallback(async (refresh = false) => {
    const version = ++requestVersion.current
    const saved = refresh ? null : viewCache.read<MatchupResponse>(cacheKey)
    if (!refresh) setMatchup(saved)
    setIsRefreshingData(refresh)
    setIsLoading(true)
    setError(null)

    try {
      const result = connectionMode === 'local'
        ? await getLocalMatchup({ team_id: selectedTeamId, week, refresh })
        : await getMatchup({
            league_id: league.league_id,
            season: league.season,
            team_id: selectedTeamId,
            week,
            refresh,
          })
      if (version !== requestVersion.current) return
      if (refresh) viewCache.clear()
      viewCache.write(cacheKey, result)
      setMatchup(result)
    } catch (caughtError) {
      if (version !== requestVersion.current) return
      if (!refresh && !saved) setMatchup(null)
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'The matchup could not be loaded.',
      )
    } finally {
      if (version === requestVersion.current) setIsLoading(false)
    }
  }, [cacheKey, connectionMode, league.league_id, league.season, selectedTeamId, week])

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadMatchup() }, 0)
    return () => {
      window.clearTimeout(timer)
      requestVersion.current += 1
    }
  }, [loadMatchup])

  const live = useLiveScores(league.league_id, league.season, week, connectionMode,
    matchup?.week === week ? [...matchup.home.players, ...matchup.away.players] : [])

  const homeTeam = league.teams.find(
    (team) => team.team_id === matchup?.home.team_id,
  )
  const awayTeam = league.teams.find(
    (team) => team.team_id === matchup?.away.team_id,
  )
  const options = matchupOptions(
    league.teams,
    week,
    currentScoreboard?.data?.opponents_by_team
      ?? (matchup?.week === week ? matchup.opponents_by_team : undefined),
  )
  const selectedMatchup = options.find(
    (option) => option.teamId === selectedTeamId || option.opponentId === selectedTeamId,
  )
  const scoreboardGames = currentScoreboard?.data?.scoreboard ?? []

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

          <div className="grid min-w-0 gap-3 sm:grid-cols-[minmax(220px,1fr)_110px_auto] lg:max-w-2xl">
            <select
              value={selectedMatchup?.teamId ?? selectedTeamId}
              disabled={isLoading}
              onChange={(event) => onTeamChange(Number(event.target.value))}
              aria-label="Fantasy matchup"
              title={selectedMatchup?.label}
              className="h-11 min-w-0 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-emerald-500"
            >
              {options.map((option) => (
                <option key={option.teamId} value={option.teamId} disabled={option.disabled}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              value={week}
              disabled={isLoading}
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
              onClick={() => void loadMatchup(true)}
              disabled={isLoading}
              className="h-11 rounded-xl bg-emerald-600 px-5 text-sm font-black text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {isLoading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        </div>
        {isLoading && (
          <p role="status" className="mt-3 text-sm text-slate-500">
            {matchup
              ? isRefreshingData
                ? 'Refreshing NFL data and both lineups. Previous results remain visible.'
                : 'Checking for matchup updates. Showing saved results.'
              : 'Loading both lineups. The first request can take longer while data and models load.'}
          </p>
        )}
      </section>

      {error && (
        <div role="alert" className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-800">
          {error}
          {matchup && <span> Showing previous results.</span>}
          <button type="button" disabled={isLoading}
            onClick={() => void loadMatchup(true)}
            className="ml-3 font-bold underline">Retry</button>
        </div>
      )}

      {isLoading && !matchup && (
        <div className="mt-5 rounded-2xl border border-slate-200 bg-white px-6 py-16 text-center">
          <div className="mx-auto size-8 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-600" />
          <p className="mt-4 text-sm font-bold text-slate-600">Projecting both lineups…</p>
        </div>
      )}

      {currentScoreboard?.error && (
        <p role="status" className="mt-4 text-sm text-amber-700 dark:text-amber-300">
          {currentScoreboard.error} {currentScoreboard.data ? 'Showing last received scores; they may be stale.' : 'League scores are unavailable.'}
        </p>
      )}
          {scoreboardGames.length > 0 && (
            <section className="mt-5" aria-labelledby="league-scoreboard-heading">
              <div className="mb-3 flex items-end justify-between gap-4">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">
                    League scoreboard
                  </p>
                  <h2 id="league-scoreboard-heading" className="mt-1 text-lg font-black text-slate-950 dark:text-white">
                    Week {week} matchups
                  </h2>
                </div>
                <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">ESPN scores</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {scoreboardGames.map((game) => {
                  const isSelected = game.home_team_id === selectedTeamId || game.away_team_id === selectedTeamId

                  return (
                    <button
                      key={`${game.away_team_id}-${game.home_team_id}`}
                      type="button"
                      disabled={isLoading}
                      onClick={() => onTeamChange(game.home_team_id)}
                      aria-current={isSelected ? 'true' : undefined}
                      className={`rounded-2xl border p-4 text-left shadow-sm transition focus:outline-none focus:ring-4 focus:ring-emerald-100 disabled:cursor-wait dark:focus:ring-emerald-950 ${
                        isSelected
                          ? 'border-lime-400 bg-lime-50 ring-1 ring-lime-300 dark:border-lime-400 dark:bg-lime-950/40'
                          : 'border-slate-200 bg-white hover:border-emerald-300 hover:shadow-md dark:border-slate-700 dark:bg-slate-900 dark:hover:border-emerald-600'
                      }`}
                    >
                      <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 text-sm">
                        <span className="truncate font-bold text-slate-700 dark:text-slate-200">{game.away_team_name}</span>
                        <span className="font-black tabular-nums text-slate-950 dark:text-white">{game.away_score?.toFixed(1) ?? '—'}</span>
                        <span className="truncate font-bold text-slate-700 dark:text-slate-200">{game.home_team_name}</span>
                        <span className="font-black tabular-nums text-slate-950 dark:text-white">{game.home_score?.toFixed(1) ?? '—'}</span>
                      </div>
                      <p className={`mt-3 text-[10px] font-black uppercase tracking-[0.14em] ${
                        isSelected
                          ? 'text-emerald-700 dark:text-lime-300'
                          : 'text-slate-400'
                      }`}>
                        {isSelected ? 'Selected matchup' : 'View matchup'}
                      </p>
                    </button>
                  )
                })}
              </div>
            </section>
          )}
      {matchup && (
        <>
          <ProjectionFreshness generatedAt={matchup.home.generated_at} />
          <LiveScoreNote data={live.data} error={live.error} />
          <section className="mt-5 rounded-3xl bg-slate-950 px-5 py-7 text-white shadow-xl sm:px-8">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-5 text-center">
              <div>
                <p className="truncate text-sm font-bold text-slate-300">{matchup.away.team_name}</p>
                <TeamScore team={matchup.away} liveScores={live.scores} />
                {matchup.away_win_pct !== null && (
                  <p className="mt-2 text-sm font-bold text-white">
                    {matchup.away_win_pct.toFixed(1)}% pregame estimated win chance
                  </p>
                )}
              </div>
              <div>
                <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-500">Starters</p>
                <p className="mt-1 text-lg font-black text-slate-400">VS</p>
              </div>
              <div>
                <p className="truncate text-sm font-bold text-slate-300">{matchup.home.team_name}</p>
                <TeamScore team={matchup.home} liveScores={live.scores} />
                {matchup.home_win_pct !== null && (
                  <p className="mt-2 text-sm font-bold text-white">
                    {matchup.home_win_pct.toFixed(1)}% pregame estimated win chance
                  </p>
                )}
              </div>
            </div>
            {matchup.home_win_pct !== null && matchup.away_win_pct !== null && (
              <div className="mt-5 flex h-2 overflow-hidden rounded-full bg-slate-700"
                role="img" aria-label={`${matchup.away.team_name}: ${matchup.away_win_pct}% win chance; ${matchup.home.team_name}: ${matchup.home_win_pct}% win chance`}>
                <div className="bg-lime-300" style={{ width: `${matchup.away_win_pct}%` }} />
                <div className="bg-sky-400" style={{ width: `${matchup.home_win_pct}%` }} />
              </div>
            )}
            <p className="mt-4 text-center text-xs leading-5 text-slate-400">
              {matchup.home_win_pct !== null
                ? 'Rough pregame estimate · Does not update with live scores'
                : matchup.win_probability_note}
            </p>
            {matchup.home_win_pct !== null && (
              <details className="mt-2 text-center text-xs leading-5 text-slate-400">
                <summary className="cursor-pointer">How win chance is estimated</summary>
                <p className="mt-2">{matchup.win_probability_note}</p>
              </details>
            )}
            <p className="mt-5 text-center text-xs font-semibold text-slate-400">Totals use the displayed starters. Live scores use ESPN league scoring; AI estimates use the app's scoring.</p>
          </section>

          <div className="mt-5 grid gap-5 lg:grid-cols-2">
            <MatchupRoster
              projection={matchup.away}
              team={awayTeam}
              connectionMode={connectionMode}
              liveScores={live.scores}
            />
            <MatchupRoster
              projection={matchup.home}
              team={homeTeam}
              connectionMode={connectionMode}
              liveScores={live.scores}
            />
          </div>
        </>
      )}
    </>
  )
}
