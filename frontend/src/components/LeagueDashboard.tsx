import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  getLocalTeamProjections,
  getTeamLogoUrl,
  getTeamProjections,
} from '../lib/api'
import type {
  ESPNLeague,
  ESPNTeamSummary,
  RosterProjection,
  TeamProjectionResponse,
} from '../types/api'
import { LeagueStandings } from './LeagueStandings'
import { MatchupView } from './MatchupView'
import { ThemeToggle } from './ThemeToggle'

export type ConnectionMode = 'public' | 'local'
type DashboardView = 'team' | 'matchup' | 'league'

type LeagueDashboardProps = {
  league: ESPNLeague
  connectionMode: ConnectionMode
  onDisconnect: () => void
  isDark: boolean
  onToggleDark: () => void
}

const weeks = Array.from({ length: 18 }, (_, index) => index + 1)

const positionStyles: Record<string, string> = {
  QB: 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-200',
  RB: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200',
  WR: 'bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-200',
  TE: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-200',
  K: 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-200',
  'D/ST': 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-100',
}

const availabilityStyles: Record<
  RosterProjection['availability'],
  string
> = {
  healthy: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200',
  questionable: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  doubtful: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200',
  unavailable: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200',
  unknown: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-100',
}

function playerStatusLabel(player: RosterProjection): string {
  if (player.availability !== 'healthy') {
    return player.injury_status ?? 'Injury update'
  }

  return player.status === 'projected' ? 'Ready' : 'Unavailable'
}

const starterSlotOrder = [
  'QB',
  'RB',
  'WR',
  'TE',
  'RB/WR/TE',
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

function TeamAvatar({
  team,
  connectionMode,
}: {
  team: ESPNTeamSummary | undefined
  connectionMode: ConnectionMode
}) {
  const logoUrl = team
    ? getTeamLogoUrl(team.team_id, team.logo_url, connectionMode)
    : null
  return (
    <div className="relative grid size-16 place-items-center overflow-hidden rounded-full bg-slate-900 text-lg font-black tracking-wider text-lime-300 ring-2 ring-white shadow-sm dark:ring-slate-700">
      <span>{team?.abbreviation.slice(0, 3) ?? 'FF'}</span>
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

function PlayerRow({ player }: { player: RosterProjection }) {
  const positionClass =
    positionStyles[player.position]
    ?? 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-100'
  const statusClass = player.availability !== 'healthy'
    ? availabilityStyles[player.availability]
    : player.status === 'projected'
      ? availabilityStyles.healthy
      : availabilityStyles.questionable

  return (
    <div className="grid min-h-20 grid-cols-[52px_minmax(0,1fr)_74px] items-center gap-3 border-t border-slate-100 px-4 py-3 first:border-t-0 sm:grid-cols-[70px_minmax(0,1fr)_150px_90px_100px] sm:px-6">
      <div>
        <span className="text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-300">
          {displayLineupSlot(player.lineup_slot)}
        </span>
      </div>

      <div className="flex min-w-0 items-center gap-3">
        <span
          className={`hidden w-11 shrink-0 justify-center rounded-lg px-2 py-1 text-xs font-black sm:inline-flex ${positionClass}`}
        >
          {player.position}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-extrabold text-slate-950 sm:text-base">
            {player.player_name}
          </p>
          <p className="mt-1 truncate text-xs font-semibold text-slate-500 dark:text-slate-300">
            <span className="sm:hidden">{player.position} · </span>
            {player.team ?? 'Team unavailable'}
          </p>
        </div>
      </div>

      <p className="text-right text-xs font-bold text-slate-600 dark:text-slate-200 sm:text-left sm:text-sm">
        {player.opponent_team ? `vs ${player.opponent_team}` : '—'}
      </p>

      <div className="hidden sm:block">
        <span
          title={player.adjustment_reason ?? undefined}
          className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold ${statusClass}`}
        >
          {playerStatusLabel(player)}
        </span>
      </div>

      <div className="hidden text-right sm:block">
        {player.predicted_points !== null ? (
          <p className="text-xl font-black tabular-nums text-slate-950">
            {player.predicted_points.toFixed(1)}
          </p>
        ) : (
          <p className="text-xs leading-4 text-slate-400" title={player.reason ?? ''}>
            Not projected
          </p>
        )}
      </div>

      <div className="col-span-3 -mt-1 flex items-center justify-between sm:hidden">
        <p className="truncate pr-4 text-xs text-slate-400">
          {player.adjustment_reason
            ?? (player.availability !== 'healthy'
              ? playerStatusLabel(player)
              : player.status === 'skipped'
                ? player.reason
                : 'AI projection ready')}
        </p>
        <p className="shrink-0 text-lg font-black tabular-nums text-slate-950">
          {player.predicted_points !== null
            ? `${player.predicted_points.toFixed(1)} pts`
            : '—'}
        </p>
      </div>
    </div>
  )
}

function RosterSection({
  title,
  subtitle,
  players,
}: {
  title: string
  subtitle: string
  players: RosterProjection[]
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-end justify-between border-b border-slate-200 bg-slate-50/70 px-4 py-4 sm:px-6">
        <div>
          <h2 className="font-black tracking-tight text-slate-950">{title}</h2>
          <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
        </div>
        <p className="text-xs font-bold text-slate-400">{players.length} players</p>
      </div>

      <div className="hidden grid-cols-[70px_minmax(0,1fr)_150px_90px_100px] gap-3 border-b border-slate-100 px-6 py-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-400 sm:grid">
        <span>Slot</span>
        <span>Player</span>
        <span>Matchup</span>
        <span>Status</span>
        <span className="text-right">AI proj.</span>
      </div>

      {players.length > 0 ? (
        players.map((player) => (
          <PlayerRow key={player.espn_id} player={player} />
        ))
      ) : (
        <p className="px-6 py-8 text-center text-sm text-slate-500">
          No players in this section.
        </p>
      )}
    </section>
  )
}

export function LeagueDashboard({
  league,
  connectionMode,
  onDisconnect,
  isDark,
  onToggleDark,
}: LeagueDashboardProps) {
  const [selectedTeamId, setSelectedTeamId] = useState(
    league.teams[0]?.team_id ?? 0,
  )
  const [week, setWeek] = useState(league.current_week)
  const [projection, setProjection] = useState<TeamProjectionResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeView, setActiveView] = useState<DashboardView>('team')
  const initialRequestStarted = useRef(false)

  const selectedTeam = useMemo(
    () => league.teams.find((team) => team.team_id === selectedTeamId),
    [league.teams, selectedTeamId],
  )

  const loadProjection = useCallback(
    async (teamId: number, targetWeek: number) => {
      if (!teamId) {
        return
      }

      setIsLoading(true)
      setError(null)

      try {
        const result =
          connectionMode === 'local'
            ? await getLocalTeamProjections({
                team_id: teamId,
                week: targetWeek,
              })
            : await getTeamProjections({
                league_id: league.league_id,
                season: league.season,
                team_id: teamId,
                week: targetWeek,
              })

        setProjection(result)
      } catch (caughtError) {
        setProjection(null)
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : 'The roster projections could not be loaded.',
        )
      } finally {
        setIsLoading(false)
      }
    },
    [connectionMode, league.league_id, league.season],
  )

  useEffect(() => {
    if (initialRequestStarted.current || !selectedTeamId) {
      return
    }

    initialRequestStarted.current = true
    void loadProjection(selectedTeamId, week)
  }, [loadProjection, selectedTeamId, week])

  const starters = useMemo(() => {
    if (!projection) {
      return []
    }

    return projection.players
      .filter((player) => !['BE', 'IR'].includes(player.lineup_slot))
      .sort((left, right) => {
        const leftIndex = starterSlotOrder.indexOf(left.lineup_slot)
        const rightIndex = starterSlotOrder.indexOf(right.lineup_slot)
        return (leftIndex < 0 ? 99 : leftIndex) - (rightIndex < 0 ? 99 : rightIndex)
      })
  }, [projection])

  const bench = useMemo(
    () => projection?.players.filter((player) => player.lineup_slot === 'BE') ?? [],
    [projection],
  )

  const injuredReserve = useMemo(
    () => projection?.players.filter((player) => player.lineup_slot === 'IR') ?? [],
    [projection],
  )

  function changeTeam(teamId: number) {
    setSelectedTeamId(teamId)
    setProjection(null)
    setError(null)
  }

  function changeWeek(targetWeek: number) {
    setWeek(targetWeek)
    setProjection(null)
    setError(null)
  }

  return (
    <div className="min-h-screen bg-[#f3f5f2] text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="bg-slate-950 text-white shadow-lg">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-lime-300 font-black text-slate-950">
              FF
            </div>
            <div className="min-w-0">
              <p className="truncate font-black tracking-tight">{league.league_name}</p>
              <p className="text-xs font-semibold text-slate-400">Fantasy Football AI</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle isDark={isDark} onToggle={onToggleDark} />
            <button
              type="button"
              onClick={onDisconnect}
              className="rounded-lg border border-white/15 px-3 py-2 text-xs font-bold text-slate-200 transition hover:border-white/30 hover:bg-white/10"
            >
              Change league
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-7 overflow-x-auto px-4 sm:px-8" aria-label="League navigation">
          {([
            ['team', 'My team'],
            ['matchup', 'Matchup'],
            ['league', 'League'],
          ] as const).map(([view, label]) => (
            <button
              key={view}
              type="button"
              onClick={() => setActiveView(view)}
              className={`border-b-2 pb-3 text-sm font-black transition ${
                activeView === view
                  ? 'border-lime-300 text-white'
                  : 'border-transparent text-slate-500 hover:text-slate-300'
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-8 sm:py-9">
        {activeView === 'team' && (
          <>
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-4">
              <TeamAvatar
                team={selectedTeam}
                connectionMode={connectionMode}
              />
              <div>
                <p className="text-xs font-black uppercase tracking-[0.14em] text-emerald-700">
                  {league.season} season · {connectionMode === 'local' ? 'Private league' : 'Public league'}
                </p>
                <h1 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">
                  {selectedTeam?.team_name ?? 'Select a team'}
                </h1>
                <p className="mt-1 text-sm text-slate-500">AI-assisted weekly lineup view</p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-[minmax(180px,1fr)_130px_auto]">
              <label>
                <span className="mb-1.5 block text-xs font-black uppercase tracking-wider text-slate-500">Fantasy team</span>
                <select
                  value={selectedTeamId}
                  onChange={(event) => changeTeam(Number(event.target.value))}
                  className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100"
                >
                  {league.teams.map((team) => (
                    <option key={team.team_id} value={team.team_id}>
                      {team.team_name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span className="mb-1.5 block text-xs font-black uppercase tracking-wider text-slate-500">NFL week</span>
                <select
                  value={week}
                  onChange={(event) => changeWeek(Number(event.target.value))}
                  className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100"
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
                onClick={() => void loadProjection(selectedTeamId, week)}
                disabled={isLoading || !selectedTeamId}
                className="h-11 self-end rounded-xl bg-emerald-600 px-5 text-sm font-black text-white transition hover:bg-emerald-500 focus:outline-none focus:ring-4 focus:ring-emerald-100 disabled:cursor-wait disabled:opacity-60"
              >
                {isLoading ? 'Loading…' : 'Update projections'}
              </button>
            </div>
          </div>
        </section>

        {error && (
          <div role="alert" className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-800">
            <span className="font-black">Could not load this week: </span>
            {error}
          </div>
        )}

        {projection && (
          <>
            <section className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl bg-slate-900 p-5 text-white">
                <p className="text-xs font-black uppercase tracking-[0.14em] text-slate-400">Projection week</p>
                <p className="mt-2 text-3xl font-black">Week {projection.week}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <p className="text-xs font-black uppercase tracking-[0.14em] text-slate-400">Projected</p>
                <p className="mt-2 text-3xl font-black text-emerald-600">{projection.projected_count}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <p className="text-xs font-black uppercase tracking-[0.14em] text-slate-400">Unavailable</p>
                <p className="mt-2 text-3xl font-black text-amber-600">{projection.skipped_count}</p>
              </div>
            </section>

            {projection.roster_week < projection.week && (
              <div className="mt-5 rounded-2xl border border-sky-200 bg-sky-50 px-5 py-4 text-sm leading-6 text-sky-900">
                Week {projection.week} has not published an NFL roster yet, so these predictions use the latest active roster from Week {projection.roster_week} with Week {projection.week}'s matchups.
              </div>
            )}

            <div className="mt-5 space-y-5">
              <RosterSection
                title="Starting lineup"
                subtitle={`Your active starters for Week ${projection.week}`}
                players={starters}
              />
              <RosterSection
                title="Bench"
                subtitle="Players currently outside the starting lineup"
                players={bench}
              />
              {injuredReserve.length > 0 && (
                <RosterSection
                  title="Injured reserve"
                  subtitle="Players currently in an IR roster slot"
                  players={injuredReserve}
                />
              )}
            </div>
          </>
        )}

        {isLoading && !projection && (
          <div className="mt-5 rounded-2xl border border-slate-200 bg-white px-6 py-16 text-center shadow-sm">
            <div className="mx-auto size-8 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-600" />
            <p className="mt-4 text-sm font-bold text-slate-600">Loading your roster and running the models…</p>
          </div>
        )}

        {!isLoading && !projection && !error && (
          <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-white/60 px-6 py-14 text-center">
            <p className="font-black text-slate-800">Choose a team and week</p>
            <p className="mt-2 text-sm text-slate-500">Then update projections to load the complete roster.</p>
          </div>
        )}
          </>
        )}

        {activeView === 'matchup' && (
          <MatchupView
            league={league}
            connectionMode={connectionMode}
            selectedTeamId={selectedTeamId}
            week={week}
            onTeamChange={changeTeam}
            onWeekChange={changeWeek}
          />
        )}

        {activeView === 'league' && (
          <LeagueStandings
            league={league}
            selectedTeamId={selectedTeamId}
            connectionMode={connectionMode}
          />
        )}
      </main>
    </div>
  )
}
