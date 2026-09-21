import type { ESPNLeague } from '../types/api'
import { getTeamLogoUrl } from '../lib/api'

export function LeagueStandings({
  league,
  selectedTeamId,
  connectionMode,
}: {
  league: ESPNLeague
  selectedTeamId: number
  connectionMode: 'public' | 'local'
}) {
  const teams = [...league.teams].sort(
    (left, right) => left.standing - right.standing,
  )
  const leader = teams[0]
  const averagePoints = teams.length
    ? teams.reduce((total, team) => total + team.points_for, 0) / teams.length
    : 0

  return (
    <>
      <section className="rounded-3xl bg-slate-950 p-6 text-white shadow-xl sm:p-8">
        <p className="text-xs font-black uppercase tracking-[0.16em] text-lime-300">
          {league.season} league overview
        </p>
        <div className="mt-3 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-black tracking-tight">{league.league_name}</h1>
            <p className="mt-2 text-sm text-slate-400">
              Week {league.current_week} · {league.team_count} teams
            </p>
          </div>
          <div className="flex gap-7">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Leader</p>
              <p className="mt-1 font-black">{leader?.team_name ?? '—'}</p>
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Avg. points</p>
              <p className="mt-1 font-black tabular-nums">{averagePoints.toFixed(1)}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4 sm:px-6">
          <h2 className="font-black text-slate-950">League standings</h2>
          <p className="mt-1 text-xs text-slate-500">Live records and scoring totals from ESPN</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left">
            <thead className="bg-slate-50 text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
              <tr>
                <th className="px-5 py-3 text-center">Rank</th>
                <th className="px-5 py-3">Team</th>
                <th className="px-5 py-3 text-center">Record</th>
                <th className="px-5 py-3 text-right">PF</th>
                <th className="px-5 py-3 text-right">PA</th>
                <th className="px-5 py-3 text-center">Streak</th>
                <th className="px-5 py-3 text-right">Playoff</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((team) => (
                <tr
                  key={team.team_id}
                  className={`border-t border-slate-100 ${team.team_id === selectedTeamId ? 'bg-lime-50/70' : ''}`}
                >
                  <td className="px-5 py-4 text-center text-sm font-black text-slate-500">{team.standing}</td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <div className="relative grid size-10 place-items-center overflow-hidden rounded-full bg-slate-900 text-xs font-black text-lime-300 ring-1 ring-slate-200">
                        <span>{team.abbreviation}</span>
                        {getTeamLogoUrl(
                          team.team_id,
                          team.logo_url,
                          connectionMode,
                        ) && (
                          <img
                            src={getTeamLogoUrl(
                              team.team_id,
                              team.logo_url,
                              connectionMode,
                            ) ?? undefined}
                            alt=""
                            referrerPolicy="no-referrer"
                            onError={(event) => {
                              event.currentTarget.style.display = 'none'
                            }}
                            className="absolute inset-0 size-full bg-white object-cover"
                          />
                        )}
                      </div>
                      <div>
                        <p className="font-bold text-slate-950">{team.team_name}</p>
                        {team.team_id === selectedTeamId && (
                          <p className="mt-0.5 text-xs font-bold text-emerald-700">Selected team</p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-center text-sm font-bold tabular-nums">
                    {team.wins}-{team.losses}{team.ties ? `-${team.ties}` : ''}
                  </td>
                  <td className="px-5 py-4 text-right text-sm font-bold tabular-nums">{team.points_for.toFixed(1)}</td>
                  <td className="px-5 py-4 text-right text-sm tabular-nums text-slate-500">{team.points_against.toFixed(1)}</td>
                  <td className="px-5 py-4 text-center text-sm font-bold text-slate-600">{team.streak ?? '—'}</td>
                  <td className="px-5 py-4 text-right text-sm font-bold tabular-nums text-emerald-700">
                    {team.playoff_pct !== null ? `${team.playoff_pct.toFixed(1)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
