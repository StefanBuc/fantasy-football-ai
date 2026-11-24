import { useCallback, useEffect, useRef, useState } from 'react'
import { analyzeTrade, getTradeRosters } from '../lib/api'
import type { ESPNLeague, TradeAnalysis, TradeRosters } from '../types/api'
import type { ConnectionMode } from './LeagueDashboard'

const panel = 'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm'
const inputStyle = 'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-bold'
const pts = (value: number | null) => value === null ? '—' : value.toFixed(1)
const gain = (value: number | null) => value === null ? 'Unavailable' : `${value > 0 ? '+' : ''}${value.toFixed(1)} pts`
const rank = (value: number | null) => value === null ? '—' : `#${value}`
const slotName = (value: string) => value === 'RB/WR/TE' ? 'FLEX' : value === 'OP' ? 'Superflex' : value
const gainStyle = (value: number | null) => value !== null && value < 0 ? 'text-rose-700 dark:text-rose-300' : 'text-emerald-700 dark:text-emerald-300'

export function TradeAnalysisResults({ data }: { data: TradeAnalysis }) {
  return <div className="space-y-5">
    <section className={`${panel} border-emerald-300`} aria-live="polite">
      <p className="text-xs font-black uppercase tracking-wider text-emerald-700 dark:text-emerald-300">Trade analysis · Weeks {data.week}–{data.end_week}</p>
      <h2 className="mt-2 text-2xl font-black">{data.verdict}</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">{data.summary}</p>
      <p className="mt-2 text-xs text-slate-500">Checked {new Date(data.generated_at).toLocaleString()}. Hypothetical only; make any trade in ESPN.</p>
    </section>

    <div className="grid gap-5 lg:grid-cols-2">{data.teams.map((team) => <section key={team.team_id} className={panel}>
      <h3 className="text-xl font-black">{team.team_name}</h3>
      <dl className="mt-4 grid grid-cols-2 gap-4">
        <div><dt className="text-xs font-bold text-slate-500">Week {data.week} optimized lineup</dt>
          <dd className="mt-1 font-black tabular-nums">{pts(team.weekly_before)} → {pts(team.weekly_after)}</dd>
          <dd className={`text-sm font-bold ${gainStyle(team.weekly_change)}`}>{gain(team.weekly_change)}</dd></div>
        <div><dt className="text-xs font-bold text-slate-500">Remaining starting-lineup points</dt>
          <dd className="mt-1 font-black tabular-nums">{pts(team.rest_before)} → {pts(team.rest_after)}</dd>
          <dd className={`text-sm font-bold ${gainStyle(team.rest_change)}`}>{gain(team.rest_change)}</dd></div>
        <div><dt className="text-xs font-bold text-slate-500">Projected power rank</dt>
          <dd className="mt-1 font-black">{rank(team.power_rank_before)} → {rank(team.power_rank_after)}</dd></div>
        <div><dt className="text-xs font-bold text-slate-500">Weeks with complete comparisons</dt>
          <dd className="mt-1 font-black">{team.weeks_covered} / {data.end_week - data.week + 1}</dd></div>
      </dl>
      <h4 className="mt-5 text-sm font-black">Team needs and depth</h4>
      <ul className="mt-2 space-y-2 text-sm leading-5 text-slate-600">{team.explanations.length
        ? team.explanations.map((text) => <li key={text}>{text}</li>)
        : <li>No material change to projected starters or available backups.</li>}</ul>
      <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-xs">
        <caption className="mb-2 text-left text-slate-500">Starting-slot points averaged across Weeks {data.week}–{data.end_week}. Backups are for Week {data.week}.</caption>
        <thead className="text-slate-500"><tr><th className="py-2 pr-3">Slot</th><th className="px-2">Before → after</th><th className="px-2">League avg</th><th className="pl-2">Backups</th></tr></thead>
        <tbody>{team.positions.map((position) => <tr key={position.slot} className="border-t border-slate-100">
          <th className="py-2 pr-3">{slotName(position.slot)}</th><td className="whitespace-nowrap px-2 tabular-nums">{pts(position.before_points)} → {pts(position.after_points)}</td>
          <td className="px-2 tabular-nums">{pts(position.league_average)}</td><td className="pl-2 tabular-nums">{position.backups_before} → {position.backups_after}</td>
        </tr>)}</tbody></table></div>
      <details className="mt-5 border-t border-slate-200 pt-4"><summary className="cursor-pointer text-sm font-black">Week {data.week} lineups before and after</summary>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs">
          <thead className="text-slate-500"><tr><th className="py-2 pr-3">Slot</th><th className="px-2">Before</th><th className="pl-2">After</th></tr></thead>
          <tbody>{team.lineup_after.map((entry, index) => {
            const before = team.lineup_before[index]?.player
            const incoming = entry.player && data.players.some((player) => player.espn_id === entry.player?.espn_id && player.from_team_id !== team.team_id)
            return <tr key={`${entry.slot}:${index}`} className="border-t border-slate-100">
              <th className="py-3 pr-3">{slotName(entry.slot)}</th><td className="px-2">{before?.player_name ?? 'Empty'}<span className="block text-slate-500">{pts(before?.predicted_points ?? null)} pts</span></td>
              <td className="pl-2">{entry.player?.player_name ?? 'Empty'}{incoming && <span className="ml-1 font-bold text-emerald-700 dark:text-emerald-300">(Incoming)</span>}
                <span className="block text-slate-500">{pts(entry.player?.predicted_points ?? null)} pts{entry.locked ? ' · Locked' : ''}</span></td>
            </tr>
          })}</tbody></table></div>
      </details>
    </section>)}</div>

    <section className={panel}><h3 className="font-black">Players in the trade</h3>
      <p className="mt-1 text-xs text-slate-500">Player totals include bench value. The verdict measures how those players affect each team's starting lineup.</p>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500"><tr><th className="py-2 pr-4">Player / sending team</th><th className="px-3">Week {data.week}</th><th className="px-3">Weeks {data.week}–{data.end_week}</th><th className="pl-3">Coverage</th></tr></thead>
        <tbody>{data.players.map((player) => <tr key={player.espn_id} className="border-t border-slate-100">
          <td className="py-3 pr-4"><span className="font-bold">{player.player_name}</span><span className="block text-xs text-slate-500">{player.position} · {data.teams.find((team) => team.team_id === player.from_team_id)?.team_name}</span></td>
          <td className="px-3 tabular-nums">{pts(player.weekly_points)}</td><td className="px-3 tabular-nums">{pts(player.rest_of_season_points)}</td>
          <td className="pl-3 text-xs text-slate-500">{player.projected_games} games{player.missing_weeks > 0 ? ` · ${player.missing_weeks} missing week(s)` : ''}</td>
        </tr>)}</tbody></table></div>
    </section>

    <section className={panel}><h3 className="font-black">Week-by-week lineup impact</h3>
      <div className="mt-3 grid gap-5 md:grid-cols-2">{data.teams.map((team) => <div key={team.team_id} className="overflow-x-auto">
        <h4 className="mb-2 text-sm font-bold">{team.team_name}</h4><table className="w-full text-left text-xs">
          <thead className="text-slate-500"><tr><th className="py-2">Week</th><th>Before</th><th>After</th><th>Change</th></tr></thead>
          <tbody>{team.weeks.map((week) => <tr key={week.week} className="border-t border-slate-100"><th className="py-2">{week.week}</th>
            <td>{pts(week.before_points)}</td><td>{pts(week.after_points)}</td><td className={`font-bold ${gainStyle(week.change)}`}>{gain(week.change)}</td></tr>)}</tbody>
        </table></div>)}</div>
    </section>

    <section className={panel}><h3 className="font-black">Projected league power rankings</h3>
      <p className="mt-1 text-xs text-slate-500">Average optimized lineup points for Weeks {data.week}–{data.end_week}. This measures roster strength, not playoff odds.</p>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500"><tr><th className="py-2 pr-4">Team</th><th className="px-3">Rank before → after</th><th className="pl-3">Avg points before → after</th></tr></thead>
        <tbody>{data.power_rankings.map((team) => <tr key={team.team_id} className="border-t border-slate-100">
          <th className="py-3 pr-4">{team.team_name}</th><td className="whitespace-nowrap px-3">{rank(team.rank_before)} → {rank(team.rank_after)}</td>
          <td className="whitespace-nowrap pl-3 tabular-nums">{pts(team.before_points)} → {pts(team.after_points)}</td>
        </tr>)}</tbody></table></div>
    </section>
    <details className={panel}><summary className="cursor-pointer text-sm font-black">How to read these estimates</summary>
      <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-500">{data.notes.map((note) => <li key={note}>{note}</li>)}</ul>
    </details>
  </div>
}

type Props = { league: ESPNLeague; connectionMode: ConnectionMode; selectedTeamId: number; week: number;
  onTeamChange: (id: number) => void; onWeekChange: (week: number) => void }

export function TradeAnalyzerView({ league, connectionMode, selectedTeamId, week, onTeamChange, onWeekChange }: Props) {
  const [teamB, setTeamB] = useState(() => league.teams.find((team) => team.team_id !== selectedTeamId)?.team_id ?? 0)
  const [picksA, setPicksA] = useState<number[]>([])
  const [picksB, setPicksB] = useState<number[]>([])
  const [endWeek, setEndWeek] = useState(18)
  const [rosters, setRosters] = useState<TradeRosters | null>(null)
  const [rosterError, setRosterError] = useState<string | null>(null)
  const [rostersLoading, setRostersLoading] = useState(true)
  const [analysis, setAnalysis] = useState<{ key: string; data: TradeAnalysis } | null>(null)
  const [error, setError] = useState<{ key: string; text: string } | null>(null)
  const [loadingKey, setLoadingKey] = useState<string | null>(null)
  const requestVersion = useRef(0)
  const rosterVersion = useRef(0)
  const effectiveEnd = Math.max(week, endWeek)
  const key = JSON.stringify([selectedTeamId, teamB, picksA, picksB, week, effectiveEnd])
  const loading = loadingKey === key
  const result = analysis?.key === key ? analysis.data : null

  const loadRosters = useCallback(async () => {
    const version = ++rosterVersion.current
    setRostersLoading(true)
    setRosterError(null)
    try {
      const data = await getTradeRosters({ league_id: league.league_id, season: league.season }, connectionMode)
      if (version === rosterVersion.current) {
        setRosters(data)
        // Re-select after a reload so removed/changed ownership cannot retain a checkmark.
        setPicksA([]); setPicksB([]); setAnalysis(null)
      }
    } catch (caught) {
      if (version === rosterVersion.current) setRosterError(caught instanceof Error ? caught.message : 'Could not load rosters.')
    } finally {
      if (version === rosterVersion.current) setRostersLoading(false)
    }
  }, [league.league_id, league.season, connectionMode])

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadRosters() }, 0)
    return () => { window.clearTimeout(timer); rosterVersion.current += 1; requestVersion.current += 1 }
  }, [loadRosters])

  async function submit() {
    const version = ++requestVersion.current
    setLoadingKey(key); setError(null)
    try {
      const data = await analyzeTrade({ league_id: league.league_id, season: league.season,
        team_a_id: selectedTeamId, team_b_id: teamB, team_a_player_ids: picksA,
        team_b_player_ids: picksB, week, end_week: effectiveEnd }, connectionMode)
      if (version === requestVersion.current) setAnalysis({ key, data })
    } catch (caught) {
      if (version === requestVersion.current) setError({ key, text: caught instanceof Error ? caught.message : 'Could not analyze this trade.' })
    } finally {
      if (version === requestVersion.current) setLoadingKey(null)
    }
  }

  return <div className="space-y-5">
    <section className={panel}>
      <h1 className="text-2xl font-black">Trade analyzer</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">Compare a trade's effect on both teams' best starting lineups, positional needs, depth, and projected power rankings.</p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <label className="grid gap-1 text-xs font-bold text-slate-500">Effective week
          <select className={inputStyle} value={week} onChange={(event) => onWeekChange(Number(event.target.value))}>
            {Array.from({ length: 18 }, (_, index) => index + 1).map((value) => <option key={value} value={value}>Week {value}</option>)}
          </select></label>
        <label className="grid gap-1 text-xs font-bold text-slate-500">Last week to include
          <select className={inputStyle} value={effectiveEnd} onChange={(event) => setEndWeek(Number(event.target.value))}>
            {Array.from({ length: 19 - week }, (_, index) => week + index).map((value) => <option key={value} value={value}>Week {value}</option>)}
          </select></label>
        <button type="button" onClick={() => void loadRosters()} disabled={rostersLoading || loading} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-bold disabled:opacity-50">{rostersLoading ? 'Loading rosters...' : 'Reload rosters'}</button>
      </div>
      <p className="mt-3 text-xs text-slate-500">Choose the week when the trade would take effect. Future estimates use current health and roles; no recovery dates are predicted. Roster space and drops are left to managers.</p>
      {rosterError && <p role="alert" className="mt-3 text-sm text-rose-700 dark:text-rose-300">{rosterError}</p>}
    </section>

    <div className="grid gap-5 lg:grid-cols-2">{(['a', 'b'] as const).map((side) => {
      const id = side === 'a' ? selectedTeamId : teamB
      const picks = side === 'a' ? picksA : picksB
      const setPicks = side === 'a' ? setPicksA : setPicksB
      const roster = rosters?.teams.find((team) => team.team_id === id)
      return <section key={side} className={panel}>
        <label className="grid gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">{side === 'a' ? 'Team A sends' : 'Team B sends'}
          <select className={inputStyle} value={id} onChange={(event) => {
            const next = Number(event.target.value)
            if (side === 'a') {
              onTeamChange(next); setPicksA([])
              if (next === teamB) { setTeamB(league.teams.find((team) => team.team_id !== next)?.team_id ?? 0); setPicksB([]) }
            } else { setTeamB(next); setPicksB([]) }
          }}>{league.teams.filter((team) => side === 'a' || team.team_id !== selectedTeamId).map((team) => <option key={team.team_id} value={team.team_id}>{team.team_name}</option>)}</select>
        </label>
        <p className="mt-3 text-xs text-slate-500">Select players to give up · {picks.length} selected</p>
        <div className="mt-3 max-h-96 space-y-2 overflow-y-auto pr-1">
          {rostersLoading ? <p role="status" className="py-6 text-sm text-slate-500">Loading current roster...</p>
            : roster?.players.length ? roster.players.map((player) => <label key={player.espn_id} className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-200 p-3">
              <input type="checkbox" disabled={picks.length >= 10 && !picks.includes(player.espn_id)} checked={picks.includes(player.espn_id)}
                onChange={(event) => setPicks((previous) => event.target.checked ? [...previous, player.espn_id] : previous.filter((value) => value !== player.espn_id))} className="size-4 shrink-0 accent-emerald-600" />
              <span><span className="block text-sm font-bold">{player.player_name}</span><span className="mt-1 block text-xs text-slate-500">{player.position} · {player.team ?? 'No NFL team'}{player.injury_status && player.injury_status !== 'ACTIVE' ? ` · ${player.injury_status}` : ''}</span></span>
            </label>) : <p className="py-6 text-sm text-slate-500">No roster players available. Try reloading rosters.</p>}
        </div>
      </section>
    })}</div>

    <button type="button" disabled={loading || rostersLoading || !picksA.length || !picksB.length || selectedTeamId === teamB}
      onClick={() => void submit()} className="w-full rounded-xl bg-emerald-600 px-5 py-3 font-black text-white disabled:opacity-50">{loading ? 'Analyzing trade...' : 'Analyze trade'}</button>
    {loading && <p role="status" className="text-center text-sm text-slate-500">Comparing optimized lineups for Weeks {week}–{effectiveEnd}. The first analysis can take longer while future-week projections are built; later analyses reuse them.</p>}
    {error?.key === key && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error.text}</p>}
    {result && <TradeAnalysisResults data={result} />}
  </div>
}
