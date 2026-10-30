import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  getLeaguePlayers,
  getLocalLeaguePlayers,
} from '../lib/api'
import type {
  ESPNLeague,
  LeaguePlayer,
  LeaguePlayersResponse,
} from '../types/api'
import type { ConnectionMode } from './LeagueDashboard'

type PlayersViewProps = {
  league: ESPNLeague
  connectionMode: ConnectionMode
  week: number
  onWeekChange: (week: number) => void
}

type RosterFilter = 'all' | 'available' | 'rostered'
type SortOption = 'projection' | 'season_average'

const positions = ['ALL', 'QB', 'RB', 'WR', 'TE', 'FLEX', 'D/ST', 'K'] as const
const weeks = Array.from({ length: 18 }, (_, index) => index + 1)

const positionStyles: Record<string, string> = {
  QB: 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-200',
  RB: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200',
  WR: 'bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-200',
  TE: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-200',
  K: 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-200',
  'D/ST': 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-100',
}

function healthLabel(player: LeaguePlayer): string | null {
  if (player.availability === 'healthy') {
    return null
  }

  if (player.injury_status) {
    return player.injury_status.replaceAll('_', ' ')
  }

  return player.availability === 'unknown'
    ? null
    : player.availability
}

function PlayerPoolRow({ player }: { player: LeaguePlayer }) {
  const injury = healthLabel(player)
  const isAvailable = player.roster_status === 'available'
  const fallbackLabel = player.projection_method === 'recent_average'
    ? `${player.history_games ?? 0}-game avg`
    : player.projection_method === 'position_average'
      ? 'Position avg'
      : null

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_80px] gap-3 border-t border-slate-100 px-4 py-4 first:border-t-0 dark:border-slate-800 sm:grid-cols-[minmax(210px,1.4fr)_90px_140px_80px_90px_90px] sm:items-center sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <span className={`inline-flex w-12 shrink-0 justify-center rounded-lg px-2 py-1 text-xs font-black ${positionStyles[player.position] ?? positionStyles['D/ST']}`}>
          {player.position}
        </span>
        <div className="min-w-0">
          <p className="truncate font-extrabold text-slate-950 dark:text-white">
            {player.player_name}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
            <span>{player.team ?? 'Free agent'}</span>
            {player.is_on_bye ? (
              <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-black uppercase text-sky-800 dark:bg-sky-950 dark:text-sky-200">
                BYE
              </span>
            ) : (
              <span>
                {player.opponent_team
                  ? `vs ${player.opponent_team}`
                  : 'No matchup'}
              </span>
            )}
            {injury && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-black uppercase text-amber-800 dark:bg-amber-950 dark:text-amber-200">
                {injury}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="text-right sm:order-last">
        <p
          className="text-xl font-black tabular-nums text-slate-950 dark:text-white"
          title={player.projection_reason ?? undefined}
        >
          {player.predicted_points !== null
            ? player.predicted_points.toFixed(1)
            : '—'}
        </p>
        <p className="text-[10px] font-black uppercase tracking-wider text-slate-400">
          {fallbackLabel ?? 'AI points'}
        </p>
      </div>

      <div className="col-span-2 sm:col-span-1">
        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-black ${isAvailable ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'}`}>
          {isAvailable ? 'Available' : 'Rostered'}
        </span>
      </div>

      <p className="col-span-2 truncate text-sm font-semibold text-slate-600 dark:text-slate-300 sm:col-span-1">
        {player.fantasy_team_name ?? 'No fantasy team'}
      </p>

      <div className="col-span-2 sm:col-span-1 sm:text-right">
        <p className="font-black tabular-nums text-slate-950 dark:text-white">
          {player.percent_owned !== null
            ? `${player.percent_owned.toFixed(1)}%`
            : '—'}
        </p>
        <p className="text-[10px] font-black uppercase tracking-wider text-slate-400">
          ESPN rostered
        </p>
      </div>

      <div className="col-span-2 text-right sm:col-span-1">
        <p className="font-black tabular-nums text-slate-950 dark:text-white">
          {player.season_average !== null
            ? player.season_average.toFixed(1)
            : '—'}
        </p>
        <p className="text-[10px] font-black uppercase tracking-wider text-slate-400 sm:hidden">
          Season avg
        </p>
      </div>
    </div>
  )
}

export function PlayersView({
  league,
  connectionMode,
  week,
  onWeekChange,
}: PlayersViewProps) {
  const [playerPool, setPlayerPool] = useState<LeaguePlayersResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [position, setPosition] = useState<(typeof positions)[number]>('ALL')
  const [rosterFilter, setRosterFilter] = useState<RosterFilter>('available')
  const [team, setTeam] = useState('ALL')
  const [sortBy, setSortBy] = useState<SortOption>('projection')

  const loadPlayers = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = connectionMode === 'local'
        ? await getLocalLeaguePlayers({ week })
        : await getLeaguePlayers({
            league_id: league.league_id,
            season: league.season,
            week,
          })
      setPlayerPool(result)
    } catch (caughtError) {
      setPlayerPool(null)
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'The ESPN player pool could not be loaded.',
      )
    } finally {
      setIsLoading(false)
    }
  }, [connectionMode, league.league_id, league.season, week])

  useEffect(() => {
    const requestTimer = window.setTimeout(() => {
      void loadPlayers()
    }, 0)

    return () => window.clearTimeout(requestTimer)
  }, [loadPlayers])

  const nflTeams = useMemo(
    () => Array.from(
      new Set(
        playerPool?.players
          .map((player) => player.team)
          .filter((value): value is string => Boolean(value))
          ?? [],
      ),
    ).sort(),
    [playerPool],
  )

  const filteredPlayers = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()

    return playerPool?.players
      .filter((player) => {
        const matchesSearch = !normalizedSearch
          || player.player_name.toLowerCase().includes(normalizedSearch)
        const matchesPosition = position === 'ALL'
          || player.position === position
          || (
            position === 'FLEX'
            && ['RB', 'WR', 'TE'].includes(player.position)
          )
        const matchesRoster = rosterFilter === 'all'
          || player.roster_status === rosterFilter
        const matchesTeam = team === 'ALL' || player.team === team

        return matchesSearch
          && matchesPosition
          && matchesRoster
          && matchesTeam
      })
      .sort((left, right) => {
        const primaryDifference = sortBy === 'projection'
          ? (
              (right.predicted_points ?? Number.NEGATIVE_INFINITY)
              - (left.predicted_points ?? Number.NEGATIVE_INFINITY)
            )
          : (
              (right.season_average ?? Number.NEGATIVE_INFINITY)
              - (left.season_average ?? Number.NEGATIVE_INFINITY)
            )

        if (primaryDifference !== 0) {
          return primaryDifference
        }

        return left.player_name.localeCompare(right.player_name)
      }) ?? []
  }, [playerPool, position, rosterFilter, search, sortBy, team])

  return (
    <section>
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-400">
              League player pool
            </p>
            <h1 className="mt-1 text-3xl font-black tracking-tight text-slate-950 dark:text-white">
              Players
            </h1>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              Compare weekly AI projections, find available players, or see which fantasy team owns them.
            </p>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <label>
              <span className="mb-1.5 block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">
                NFL week
              </span>
              <select
                value={week}
                onChange={(event) => onWeekChange(Number(event.target.value))}
                className="h-11 min-w-40 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-900 outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:focus:ring-emerald-950"
              >
                {weeks.map((weekNumber) => (
                  <option key={weekNumber} value={weekNumber}>
                    Week {weekNumber}
                    {weekNumber === league.current_week ? ' (current)' : ''}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void loadPlayers()}
              disabled={isLoading}
              className="h-11 self-end rounded-xl bg-emerald-600 px-5 text-sm font-black text-white transition hover:bg-emerald-500 disabled:cursor-wait disabled:opacity-60"
            >
              {isLoading ? 'Refreshing…' : 'Refresh players'}
            </button>
          </div>
        </div>

        {playerPool && (
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-slate-950 p-4 text-white dark:bg-slate-800">
              <p className="text-xs font-black uppercase tracking-wider text-slate-400">Player pool</p>
              <p className="mt-1 text-2xl font-black">{playerPool.player_count}</p>
            </div>
            <div className="rounded-2xl bg-emerald-50 p-4 dark:bg-emerald-950/60">
              <p className="text-xs font-black uppercase tracking-wider text-emerald-700 dark:text-emerald-300">Available</p>
              <p className="mt-1 text-2xl font-black text-emerald-800 dark:text-emerald-100">{playerPool.available_count}</p>
            </div>
            <div className="rounded-2xl bg-slate-100 p-4 dark:bg-slate-800">
              <p className="text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">Rostered</p>
              <p className="mt-1 text-2xl font-black text-slate-900 dark:text-white">{playerPool.rostered_count}</p>
            </div>
          </div>
        )}
      </div>

      <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-5">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-[minmax(220px,1fr)_180px_180px_180px]">
          <label>
            <span className="sr-only">Search players</span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search player name…"
              className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm font-semibold text-slate-900 outline-none placeholder:text-slate-400 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:focus:ring-emerald-950"
            />
          </label>

          <label>
            <span className="sr-only">Roster status</span>
            <select
              value={rosterFilter}
              onChange={(event) => setRosterFilter(event.target.value as RosterFilter)}
              className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-900 outline-none focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="all">All roster statuses</option>
              <option value="available">Available only</option>
              <option value="rostered">Rostered only</option>
            </select>
          </label>

          <label>
            <span className="sr-only">NFL team</span>
            <select
              value={team}
              onChange={(event) => setTeam(event.target.value)}
              className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-900 outline-none focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="ALL">All NFL teams</option>
              {nflTeams.map((nflTeam) => (
                <option key={nflTeam} value={nflTeam}>{nflTeam}</option>
              ))}
            </select>
          </label>

          <label>
            <span className="sr-only">Sort players</span>
            <select
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value as SortOption)}
              className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-900 outline-none focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="projection">Sort: AI projection</option>
              <option value="season_average">Sort: Season average</option>
            </select>
          </label>
        </div>

        <div className="mt-4 flex gap-2 overflow-x-auto pb-1" aria-label="Filter by position">
          {positions.map((positionOption) => (
            <button
              key={positionOption}
              type="button"
              onClick={() => setPosition(positionOption)}
              className={`shrink-0 rounded-full px-4 py-2 text-xs font-black transition ${position === positionOption ? 'bg-slate-950 text-white dark:bg-lime-300 dark:text-slate-950' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'}`}
            >
              {positionOption === 'ALL' ? 'All positions' : positionOption}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div role="alert" className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          <span className="font-black">Could not load players: </span>{error}
        </div>
      )}

      {isLoading && !playerPool && (
        <div className="mt-5 rounded-2xl border border-slate-200 bg-white px-6 py-16 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="mx-auto size-8 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-600 dark:border-slate-700" />
          <p className="mt-4 text-sm font-bold text-slate-600 dark:text-slate-300">Loading the league player pool…</p>
        </div>
      )}

      {playerPool && (
        <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/70 px-4 py-4 dark:border-slate-800 dark:bg-slate-900 sm:px-6">
            <div>
              <h2 className="font-black text-slate-950 dark:text-white">Player results</h2>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {sortBy === 'projection'
                  ? `Sorted by highest AI projection for Week ${week}`
                  : 'Sorted by highest season average'}
              </p>
            </div>
            <p className="text-sm font-black text-slate-500 dark:text-slate-300">
              {filteredPlayers.length} found
            </p>
          </div>

          <div className="hidden grid-cols-[minmax(210px,1.4fr)_90px_140px_80px_90px_90px] gap-3 border-b border-slate-100 px-6 py-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-400 dark:border-slate-800 sm:grid">
            <span>Player</span>
            <span>Status</span>
            <span>Fantasy team</span>
            <span className="text-right">Rostered</span>
            <span className="text-right">Season avg.</span>
            <span className="text-right">AI proj.</span>
          </div>

          {filteredPlayers.length > 0 ? (
            filteredPlayers.map((player) => (
              <PlayerPoolRow key={player.espn_id} player={player} />
            ))
          ) : (
            <div className="px-6 py-14 text-center">
              <p className="font-black text-slate-800 dark:text-slate-100">No players match these filters</p>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Try another position, team, or roster status.</p>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
