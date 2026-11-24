import { useCallback, useEffect, useRef, useState } from 'react'
import { getOptimizedLineup } from '../lib/api'
import type { ESPNLeague, OptimizedLineupResponse, OptimizerPlayer } from '../types/api'
import type { ConnectionMode } from './LeagueDashboard'

const weeks = Array.from({ length: 18 }, (_, index) => index + 1)
const points = (value: number | null) => value === null ? '\u2014' : value.toFixed(1)
const slotLabel = (value: string | null) => value === 'OP' ? 'Superflex' : value === 'RB/WR/TE' ? 'FLEX' : value ?? ''
const panel = 'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm'

export function OptimizedPlayerName({ player }: { player: OptimizerPlayer }) {
  return <span className="font-extrabold text-slate-950 dark:text-white">{player.player_name}
    {player.is_free_agent && <span className="ml-1 text-xs font-bold text-emerald-700 dark:text-emerald-300">(Free agent)</span>}
  </span>
}

type Props = { league: ESPNLeague; connectionMode: ConnectionMode; selectedTeamId: number; week: number;
  onTeamChange: (id: number) => void; onWeekChange: (week: number) => void }

export function OptimizedLineupView({ league, connectionMode, selectedTeamId, week, onTeamChange, onWeekChange }: Props) {
  const [includeFreeAgents, setIncludeFreeAgents] = useState(false)
  const [loaded, setLoaded] = useState<{ key: string; result: OptimizedLineupResponse | null; error: string | null } | null>(null)
  const [loadingKey, setLoadingKey] = useState<string | null>(null)
  const requestVersion = useRef(0)
  const pending = useRef(false)
  const key = JSON.stringify([league.league_id, league.season, connectionMode, selectedTeamId, week, includeFreeAgents])
  const data = loaded?.key === key ? loaded.result : null
  const error = loaded?.key === key ? loaded.error : null
  const loading = loadingKey === key || loaded?.key !== key

  const load = useCallback(async (refresh = false) => {
    const version = ++requestVersion.current
    pending.current = true
    setLoadingKey(key)
    try {
      const result = await getOptimizedLineup({ league_id: league.league_id, season: league.season,
        team_id: selectedTeamId, week, include_free_agents: includeFreeAgents, refresh }, connectionMode)
      if (version === requestVersion.current) setLoaded({ key, result, error: null })
    } catch (caught) {
      if (version === requestVersion.current) setLoaded((previous) => ({ key,
        result: previous?.key === key ? previous.result : null,
        error: caught instanceof Error ? caught.message : 'Could not optimize this lineup.' }))
    } finally {
      if (version === requestVersion.current) { pending.current = false; setLoadingKey(null) }
    }
  }, [key, league.league_id, league.season, selectedTeamId, week, includeFreeAgents, connectionMode])

  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => { window.clearTimeout(timer); requestVersion.current += 1 }
  }, [load])

  useEffect(() => {
    if (!data) return
    // Recheck recommended moves when a kickoff passes; never retain an actionable
    // cached pregame recommendation for a now-locked player.
    const timer = window.setInterval(() => {
      const checked = new Date(data.generated_at).getTime()
      const upcoming = [...data.lineup.filter((slot) => !slot.locked).map((slot) => slot.player),
        ...data.changes.map((change) => change.player)]
      if (!pending.current && upcoming.some((player) => player?.kickoff_at
        && new Date(player.kickoff_at).getTime() > checked && new Date(player.kickoff_at).getTime() <= Date.now())) void load()
    }, 30_000)
    return () => window.clearInterval(timer)
  }, [data, load])

  return <div className="space-y-5">
    <section className={panel}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><h1 className="text-2xl font-black text-slate-950">Optimized lineup</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-500">Find your highest projected starting lineup for this week, with changes to review in ESPN.</p></div>
        <div className="flex flex-wrap gap-3">
          <label className="grid gap-1 text-xs font-bold text-slate-500">Fantasy team
            <select className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" value={selectedTeamId} onChange={(event) => onTeamChange(Number(event.target.value))}>
              {league.teams.map((team) => <option key={team.team_id} value={team.team_id}>{team.team_name}</option>)}
            </select></label>
          <label className="grid gap-1 text-xs font-bold text-slate-500">Week
            <select className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" value={week} onChange={(event) => onWeekChange(Number(event.target.value))}>
              {weeks.map((value) => <option key={value} value={value}>Week {value}</option>)}
            </select></label>
          <button type="button" disabled={loading} onClick={() => void load()} className="self-end rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{loading ? 'Optimizing...' : 'Optimize again'}</button>
        </div>
      </div>
      <label className="mt-5 flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 p-4">
        <input type="checkbox" checked={includeFreeAgents} onChange={(event) => setIncludeFreeAgents(event.target.checked)} className="size-5 accent-emerald-600" />
        <span><span className="block text-sm font-bold">Include free agents</span>
          <span className="mt-1 block text-xs text-slate-500">{includeFreeAgents ? 'Compare your roster with available players and waiver options.' : 'Only use players already on this team.'}</span></span>
      </label>
      {data && <p className="mt-3 text-xs text-slate-500">Checked {new Date(data.generated_at).toLocaleString()}. Recommendations do not change your ESPN roster.</p>}
    </section>

    {error && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}<button type="button" onClick={() => void load()} className="ml-2 font-bold underline">Retry</button></div>}
    {loading && <p role="status" className={`${panel} text-center text-sm text-slate-500`}>Checking your lineup{includeFreeAgents ? ' and the available-player pool' : ''}...</p>}
    {data && <>
      <div className="grid gap-3 sm:grid-cols-3">
        {([['Current projected points', data.current_points], ['Optimized projected points', data.optimized_points], ['Projected improvement', data.improvement]] as const).map(([label, value]) =>
          <div key={label} className={panel}><p className="text-xs font-bold text-slate-500">{label}</p><p className="mt-2 text-3xl font-black tabular-nums">{label === 'Projected improvement' && value !== null && value > 0 ? '+' : ''}{points(value)} <span className="text-sm font-bold text-slate-400">pts</span></p></div>)}
      </div>
      <section className={panel}>
        <h2 className="font-black">Recommended changes</h2>
        {data.changes.length === 0 ? <p className="mt-3 text-sm text-slate-500">No lineup changes recommended among the eligible players with usable projections.</p> :
          <ul className="mt-3 divide-y divide-slate-100">{data.changes.map((change) => <li key={`${change.action}:${change.player.espn_id}`} className="py-3">
            <p className="text-sm"><span className="mr-2 font-black text-emerald-700 dark:text-emerald-300">{change.action === 'bench' ? 'Bench' : change.action === 'add' ? 'Add and start' : change.action === 'move' ? 'Move' : 'Start'}</span>
              <OptimizedPlayerName player={change.player} />{change.slot && <span className="ml-2 font-bold text-slate-500">at {slotLabel(change.slot)}</span>}</p>
            <p className="mt-1 text-xs text-slate-500">{change.reason}</p>
          </li>)}</ul>}
      </section>
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <h2 className="border-b border-slate-200 p-5 font-black">Recommended starting lineup</h2>
        {data.lineup.map((entry, index) => <div key={`${entry.slot}:${index}`} className="grid grid-cols-[62px_minmax(0,1fr)_70px] items-center gap-3 border-b border-slate-100 px-5 py-4 last:border-0">
          <span className="text-xs font-black text-slate-500">{slotLabel(entry.slot)}</span>
          <div>{entry.player ? <>
            <OptimizedPlayerName player={entry.player} />
            <p className="mt-1 text-xs text-slate-500">{entry.player.position} · {entry.player.team ?? 'No NFL team'}{entry.player.opponent_team ? ` vs ${entry.player.opponent_team}` : ''}
              {entry.player.availability !== 'healthy' && entry.player.injury_status ? ` · ${entry.player.injury_status}` : ''}</p>
            <p className="mt-1 text-[10px] font-bold uppercase text-slate-400">{entry.locked ? 'Locked — game started or kickoff unknown' : entry.action === 'keep' ? 'Keep in lineup' : entry.action === 'add' ? 'Add, then start' : entry.action === 'move' ? `Move from ${slotLabel(entry.player.current_slot)}` : 'Start from bench'}</p>
          </> : <p className="text-sm text-amber-700 dark:text-amber-300">No eligible player available</p>}</div>
          <div className="text-right"><p className="text-xl font-black tabular-nums">{points(entry.player?.predicted_points ?? null)}</p><p className="text-[9px] uppercase text-slate-400">Projected</p></div>
        </div>)}
      </section>
      <section className={panel}><h2 className="font-black">Recommended bench</h2>
        {data.bench.length === 0 ? <p className="mt-3 text-sm text-slate-500">No bench players in this recommendation.</p> :
          <ul className="mt-3 divide-y divide-slate-100">{data.bench.map((player) => <li key={player.espn_id} className="flex items-center justify-between gap-3 py-3"><div><OptimizedPlayerName player={player} /><p className="mt-1 text-xs text-slate-500">{player.position} · {player.team ?? 'No NFL team'}{player.is_on_bye ? ' · BYE' : ''}{player.injury_status && player.availability !== 'healthy' ? ` · ${player.injury_status}` : ''}</p></div><span className="font-bold tabular-nums">{points(player.predicted_points)}</span></li>)}</ul>}
      </section>
      <section className={panel}><h2 className="text-sm font-black">Lineup notes</h2><ul className="mt-2 space-y-2 text-xs leading-5 text-slate-500">{data.notes.map((note) => <li key={note}>{note}</li>)}</ul></section>
    </>}
  </div>
}
