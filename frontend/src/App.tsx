import { useMemo, useState, type FormEvent } from 'react'

import {
  LeagueDashboard,
  type ConnectionMode,
} from './components/LeagueDashboard'
import {
  connectLeague,
  connectLocalLeague,
  getLocalTeamProjections,
  getTeamProjections,
} from './lib/api'
import type {
  ESPNLeague,
  ESPNTeamSummary,
  RosterProjection,
  TeamProjectionResponse,
} from './types/api'

const currentSeason = new Date().getFullYear()
const weeks = Array.from({ length: 18 }, (_, index) => index + 1)
const showLocalLeagueOption = import.meta.env.DEV

function hasConnectedLeague(league: ESPNLeague | null): boolean {
  return league !== null
}

const positionStyles: Record<string, string> = {
  QB: 'bg-violet-100 text-violet-700 ring-violet-200',
  RB: 'bg-emerald-100 text-emerald-700 ring-emerald-200',
  WR: 'bg-sky-100 text-sky-700 ring-sky-200',
  TE: 'bg-amber-100 text-amber-700 ring-amber-200',
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="size-5">
      <path d="M4 10h12m-5-5 5 5-5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function FootballMark() {
  return (
    <div className="grid size-10 place-items-center rounded-xl bg-lime-300 text-slate-950 shadow-[0_8px_24px_rgba(190,242,100,0.2)]">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="size-6">
        <path d="M5.1 18.9c3.2.7 7.3-.8 10.3-3.8s4.5-7.1 3.8-10.3c-3.2-.7-7.3.8-10.3 3.8s-4.5 7.1-3.8 10.3Z" stroke="currentColor" strokeWidth="1.7" />
        <path d="m8.2 15.8 7.6-7.6M10 10l4 4M11.8 8.3l3.9 3.9M8.3 11.8l3.9 3.9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </div>
  )
}

function TeamAvatar({ team }: { team: ESPNTeamSummary | undefined }) {
  if (team?.logo_url) {
    return (
      <img
        src={team.logo_url}
        alt=""
        className="size-12 rounded-xl bg-white object-contain p-1.5 ring-1 ring-slate-200"
      />
    )
  }

  return (
    <div className="grid size-12 place-items-center rounded-xl bg-slate-900 text-sm font-black tracking-wider text-lime-300">
      {team?.abbreviation.slice(0, 3) ?? 'FF'}
    </div>
  )
}

function PlayerRow({ player }: { player: RosterProjection }) {
  const positionClass =
    positionStyles[player.position] ??
    'bg-slate-100 text-slate-700 ring-slate-200'

  return (
    <div className="grid gap-4 border-b border-slate-100 px-5 py-4 last:border-0 sm:grid-cols-[minmax(0,1.5fr)_0.7fr_0.75fr] sm:items-center sm:px-6">
      <div className="flex min-w-0 items-center gap-3.5">
        <span className={`inline-flex w-10 shrink-0 justify-center rounded-lg px-2 py-1 text-xs font-black ring-1 ${positionClass}`}>
          {player.position}
        </span>
        <div className="min-w-0">
          <p className="truncate font-bold text-slate-950">{player.player_name}</p>
          <p className="mt-0.5 text-sm text-slate-500">
            {player.lineup_slot} · {player.team ?? 'No team'}
            {player.opponent_team ? ` vs ${player.opponent_team}` : ''}
          </p>
        </div>
      </div>

      <div className="sm:text-center">
        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold ${player.status === 'projected' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
          {player.status === 'projected' ? 'Ready' : 'Skipped'}
        </span>
      </div>

      <div className="sm:text-right">
        {player.predicted_points !== null ? (
          <>
            <span className="text-2xl font-black tracking-tight text-slate-950">
              {player.predicted_points.toFixed(1)}
            </span>
            <span className="ml-1 text-xs font-bold uppercase tracking-wider text-slate-400">pts</span>
          </>
        ) : (
          <p className="text-sm leading-5 text-slate-500">{player.reason ?? 'Projection unavailable'}</p>
        )}
      </div>
    </div>
  )
}

function App() {
  const [leagueId, setLeagueId] = useState('')
  const [season, setSeason] = useState(currentSeason)
  const [league, setLeague] = useState<ESPNLeague | null>(null)
  const [connectionMode, setConnectionMode] =
    useState<ConnectionMode>('public')
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null)
  const [week, setWeek] = useState(1)
  const [projection, setProjection] = useState<TeamProjectionResponse | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isProjecting, setIsProjecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedTeam = useMemo(
    () => league?.teams.find((team) => team.team_id === selectedTeamId),
    [league, selectedTeamId],
  )

  const projectedPlayers = projection?.players.filter(
    (player) => player.status === 'projected',
  ) ?? []
  const skippedPlayers = projection?.players.filter(
    (player) => player.status === 'skipped',
  ) ?? []

  function applyConnectedLeague(
    result: ESPNLeague,
    mode: ConnectionMode,
  ) {
    setLeague(result)
    setSelectedTeamId(result.teams[0]?.team_id ?? null)
    setConnectionMode(mode)
  }

  async function handleConnect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const numericLeagueId = Number(leagueId)

    if (!Number.isInteger(numericLeagueId) || numericLeagueId <= 0) {
      setError('Enter a valid numeric ESPN league ID.')
      return
    }

    setIsConnecting(true)
    setError(null)
    setProjection(null)

    try {
      const result = await connectLeague({
        league_id: numericLeagueId,
        season,
      })

      applyConnectedLeague(result, 'public')
    } catch (caughtError) {
      setLeague(null)
      setSelectedTeamId(null)
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'The league could not be connected.',
      )
    } finally {
      setIsConnecting(false)
    }
  }

  async function handleLocalConnect() {
    setIsConnecting(true)
    setError(null)
    setProjection(null)

    try {
      const result = await connectLocalLeague()
      applyConnectedLeague(result, 'local')
    } catch (caughtError) {
      setLeague(null)
      setSelectedTeamId(null)
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'The configured private league could not be connected.',
      )
    } finally {
      setIsConnecting(false)
    }
  }

  async function handleProjection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!league || selectedTeamId === null) {
      setError('Select a fantasy team first.')
      return
    }

    setIsProjecting(true)
    setError(null)

    try {
      const result = connectionMode === 'local'
        ? await getLocalTeamProjections({
            team_id: selectedTeamId,
            week,
          })
        : await getTeamProjections({
            league_id: league.league_id,
            season: league.season,
            team_id: selectedTeamId,
            week,
          })

      setProjection(result)
    } catch (caughtError) {
      setProjection(null)
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'Projections could not be generated.',
      )
    } finally {
      setIsProjecting(false)
    }
  }

  function resetLeague() {
    setLeague(null)
    setProjection(null)
    setSelectedTeamId(null)
    setConnectionMode('public')
    setError(null)
  }

  if (hasConnectedLeague(league)) {
    return (
      <LeagueDashboard
        league={league as ESPNLeague}
        connectionMode={connectionMode}
        onDisconnect={resetLeague}
      />
    )
  }

  return (
    <div className="min-h-screen bg-[#f5f7f2] text-slate-900">
      <header className="border-b border-slate-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <FootballMark />
            <div>
              <p className="font-black tracking-tight text-slate-950">Fantasy Football AI</p>
              <p className="text-xs font-medium text-slate-500">Weekly lineup intelligence</p>
            </div>
          </div>
          <div className="hidden items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600 sm:flex">
            <span className="size-2 rounded-full bg-emerald-500" />
            PyTorch models ready
          </div>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden bg-slate-950 text-white">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_20%,rgba(190,242,100,0.14),transparent_30%),radial-gradient(circle_at_10%_90%,rgba(56,189,248,0.09),transparent_28%)]" />
          <div className="relative mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-8 sm:py-20 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:py-24">
            <div className="max-w-2xl">
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-bold uppercase tracking-[0.16em] text-lime-300">
                Built for better lineup calls
              </div>
              <h1 className="text-4xl font-black leading-[1.02] tracking-[-0.045em] text-white sm:text-6xl">
                Your league. Your roster.{' '}
                <span className="text-lime-300">Smarter projections.</span>
              </h1>
              <p className="mt-6 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">
                Connect a public ESPN fantasy league and turn recent player form, matchup data, and position-specific models into one clear weekly view.
              </p>
              <div className="mt-8 flex flex-wrap gap-x-7 gap-y-3 text-sm font-semibold text-slate-300">
                <span>✓ Real roster data</span>
                <span>✓ Weekly matchups</span>
                <span>✓ QB, RB, WR &amp; TE</span>
              </div>
            </div>

            <form onSubmit={handleConnect} className="rounded-3xl border border-white/10 bg-white p-5 text-slate-900 shadow-2xl shadow-black/30 sm:p-7">
              <div className="mb-6">
                <p className="text-xs font-black uppercase tracking-[0.18em] text-emerald-700">Step one</p>
                <h2 className="mt-2 text-2xl font-black tracking-tight">Connect your league</h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">Enter the number found in your ESPN league URL.</p>
              </div>

              <div className="grid gap-4 sm:grid-cols-[1fr_130px]">
                <label className="block">
                  <span className="mb-2 block text-sm font-bold text-slate-700">League ID</span>
                  <input
                    value={leagueId}
                    onChange={(event) => setLeagueId(event.target.value)}
                    inputMode="numeric"
                    placeholder="123456789"
                    className="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-base font-semibold outline-none transition focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                  />
                </label>
                <label className="block">
                  <span className="mb-2 block text-sm font-bold text-slate-700">Season</span>
                  <input
                    type="number"
                    min="2018"
                    max={currentSeason}
                    value={season}
                    onChange={(event) => setSeason(Number(event.target.value))}
                    className="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-base font-semibold outline-none transition focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                  />
                </label>
              </div>

              <button
                type="submit"
                disabled={isConnecting}
                className="mt-5 flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 font-black text-white transition hover:bg-emerald-500 focus:outline-none focus:ring-4 focus:ring-emerald-200 disabled:cursor-wait disabled:opacity-60"
              >
                {isConnecting ? 'Connecting…' : 'Find my league'}
                {!isConnecting && <ArrowIcon />}
              </button>

              {showLocalLeagueOption && (
                <>
                  <div className="my-4 flex items-center gap-3 text-xs font-bold uppercase tracking-wider text-slate-300">
                    <span className="h-px flex-1 bg-slate-200" />
                    or
                    <span className="h-px flex-1 bg-slate-200" />
                  </div>
                  <button
                    type="button"
                    onClick={handleLocalConnect}
                    disabled={isConnecting}
                    className="flex h-12 w-full items-center justify-center rounded-xl border border-slate-200 bg-slate-50 px-5 font-black text-slate-700 transition hover:border-slate-300 hover:bg-slate-100 focus:outline-none focus:ring-4 focus:ring-slate-100 disabled:cursor-wait disabled:opacity-60"
                  >
                    Use configured private league
                  </button>
                </>
              )}

              <p className="mt-4 text-center text-xs leading-5 text-slate-400">
                The private-league option is available only during local development and keeps ESPN cookies in the backend.
              </p>
            </form>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-5 py-10 sm:px-8 sm:py-14">
          {error && (
            <div role="alert" className="mb-6 flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-800">
              <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-rose-200 font-black">!</span>
              <p>{error}</p>
            </div>
          )}

          {!league ? (
            <div className="grid gap-5 md:grid-cols-3">
              {[
                ['01', 'Connect', 'Use a public ESPN league ID to load teams and roster information.'],
                ['02', 'Choose', 'Pick your fantasy team and the NFL week you want to analyze.'],
                ['03', 'Compare', 'See every available model projection in one lineup-friendly view.'],
              ].map(([number, title, description]) => (
                <article key={number} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <p className="text-sm font-black tracking-wider text-emerald-600">{number}</p>
                  <h2 className="mt-5 text-xl font-black tracking-tight">{title}</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="space-y-7">
              <div className="flex flex-col gap-5 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7 lg:flex-row lg:items-end lg:justify-between">
                <div className="flex items-center gap-4">
                  <TeamAvatar team={selectedTeam} />
                  <div>
                    <p className="text-sm font-bold text-emerald-700">
                      {league.season} season · {connectionMode === 'local' ? 'Private local league' : 'Public league'}
                    </p>
                    <h2 className="text-2xl font-black tracking-tight text-slate-950">{league.league_name}</h2>
                    <p className="mt-1 text-sm text-slate-500">{league.team_count} teams connected</p>
                  </div>
                </div>

                <button type="button" onClick={resetLeague} className="self-start text-sm font-bold text-slate-500 underline decoration-slate-300 underline-offset-4 transition hover:text-slate-900 lg:self-auto">
                  Change league
                </button>
              </div>

              <form onSubmit={handleProjection} className="grid gap-4 rounded-3xl bg-slate-900 p-5 text-white shadow-xl sm:grid-cols-[minmax(0,1fr)_160px_auto] sm:items-end sm:p-7">
                <label>
                  <span className="mb-2 block text-sm font-bold text-slate-300">Fantasy team</span>
                  <select
                    value={selectedTeamId ?? ''}
                    onChange={(event) => {
                      setSelectedTeamId(Number(event.target.value))
                      setProjection(null)
                    }}
                    className="h-12 w-full rounded-xl border border-white/10 bg-white/10 px-4 font-semibold text-white outline-none focus:border-lime-300 focus:ring-4 focus:ring-lime-300/10"
                  >
                    {league.teams.map((team) => (
                      <option key={team.team_id} value={team.team_id} className="text-slate-900">
                        {team.team_name}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span className="mb-2 block text-sm font-bold text-slate-300">NFL week</span>
                  <select
                    value={week}
                    onChange={(event) => {
                      setWeek(Number(event.target.value))
                      setProjection(null)
                    }}
                    className="h-12 w-full rounded-xl border border-white/10 bg-white/10 px-4 font-semibold text-white outline-none focus:border-lime-300 focus:ring-4 focus:ring-lime-300/10"
                  >
                    {weeks.map((weekNumber) => (
                      <option key={weekNumber} value={weekNumber} className="text-slate-900">
                        Week {weekNumber}
                      </option>
                    ))}
                  </select>
                </label>

                <button type="submit" disabled={isProjecting || selectedTeamId === null} className="flex h-12 items-center justify-center gap-2 rounded-xl bg-lime-300 px-6 font-black text-slate-950 transition hover:bg-lime-200 focus:outline-none focus:ring-4 focus:ring-lime-300/20 disabled:cursor-wait disabled:opacity-60">
                  {isProjecting ? 'Running models…' : 'Generate projections'}
                  {!isProjecting && <ArrowIcon />}
                </button>
              </form>

              {projection ? (
                <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
                  <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex items-end justify-between border-b border-slate-100 px-5 py-5 sm:px-6">
                      <div>
                        <p className="text-xs font-black uppercase tracking-[0.16em] text-emerald-700">Week {projection.week}</p>
                        <h2 className="mt-1 text-xl font-black tracking-tight">{projection.team_name}</h2>
                      </div>
                      <p className="text-sm font-semibold text-slate-400">Model projection</p>
                    </div>

                    {projectedPlayers.length > 0 ? (
                      projectedPlayers.map((player) => (
                        <PlayerRow key={player.espn_id} player={player} />
                      ))
                    ) : (
                      <p className="px-6 py-12 text-center text-sm text-slate-500">No players could be projected for this week.</p>
                    )}
                  </section>

                  <aside className="space-y-5">
                    <div className="rounded-3xl bg-emerald-600 p-6 text-white shadow-lg shadow-emerald-900/10">
                      <p className="text-xs font-black uppercase tracking-[0.16em] text-emerald-100">Roster coverage</p>
                      <p className="mt-4 text-5xl font-black tracking-[-0.05em]">{projection.projected_count}</p>
                      <p className="mt-1 text-sm text-emerald-100">players successfully projected</p>
                    </div>

                    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                      <div className="flex items-center justify-between">
                        <h3 className="font-black">Skipped players</h3>
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-black text-slate-600">{projection.skipped_count}</span>
                      </div>
                      {skippedPlayers.length > 0 ? (
                        <div className="mt-4 space-y-4">
                          {skippedPlayers.map((player) => (
                            <div key={player.espn_id}>
                              <p className="text-sm font-bold text-slate-800">{player.player_name}</p>
                              <p className="mt-1 text-xs leading-5 text-slate-500">{player.reason ?? 'Projection unavailable'}</p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-4 text-sm leading-6 text-slate-500">Every supported roster player had enough data for a projection.</p>
                      )}
                    </div>
                  </aside>
                </div>
              ) : (
                <div className="rounded-3xl border border-dashed border-slate-300 bg-white/50 px-6 py-14 text-center">
                  <p className="font-black text-slate-800">Choose a team and week to begin</p>
                  <p className="mt-2 text-sm text-slate-500">Your model results will appear here.</p>
                </div>
              )}
            </div>
          )}
        </section>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-5 py-6 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p>Fantasy Football AI · Independent analysis tool</p>
          <p>Not affiliated with ESPN or the NFL</p>
        </div>
      </footer>
    </div>
  )
}

export default App
