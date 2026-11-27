import { useEffect, useState } from 'react'
import { getAccuracy, syncAccuracy, getAutomationStatus } from '../lib/api'
import type { AccuracyReport, ESPNLeague, AutomationStatus } from '../types/api'
import { AccuracyAutomation } from './AccuracyAutomation'
import { AccuracyInsights } from './AccuracyInsights'

const positions = ['QB', 'RB', 'WR', 'TE', 'K', 'DST']
const weeks = Array.from({ length: 18 }, (_, i) => i + 1)
const seasons = Array.from({ length: new Date().getFullYear() - 2019 }, (_, i) => 2020 + i).reverse()
const selectClass = 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-bold disabled:opacity-50'
const panelClass = 'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm'

function points(value: number | null, signed = false) {
  return value === null ? '\u2014' : `${signed && value > 0 ? '+' : ''}${value.toFixed(2)}`
}

function methodLabel(method: string) {
  return method === 'model' ? 'Model' : method === 'recent_average' ? 'Recent average' : 'Position average'
}

export function AccuracyView({ league }: { league: ESPNLeague }) {
  const [season, setSeason] = useState(league.season)
  const [source, setSource] = useState('league')
  const [week, setWeek] = useState('')
  const [position, setPosition] = useState('')
  const [offset, setOffset] = useState(0)
  const [reload, setReload] = useState(0)
  const [loaded, setLoaded] = useState<{ key: string; report: AccuracyReport | null; error: string | null;
    automation: AutomationStatus | null; automationError: string | null } | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const leagueId = source === 'league' ? league.league_id : undefined
  const requestKey = JSON.stringify([season, leagueId, week, position, offset, reload])
  const loading = loaded?.key !== requestKey
  const report = loading ? null : loaded?.report
  const error = syncError ?? (loading ? null : loaded?.error)

  useEffect(() => {
    let cancelled = false
    let pending = false
    async function load() {
      if (pending) return
      pending = true
      const [history, automation] = await Promise.allSettled([
        getAccuracy({ season, league_id: leagueId, week: week ? Number(week) : undefined,
          position: position || undefined, offset }), getAutomationStatus(season, leagueId),
      ])
      if (!cancelled) setLoaded({ key: requestKey,
        report: history.status === 'fulfilled' ? history.value : null,
        error: history.status === 'rejected' ? history.reason instanceof Error ? history.reason.message : 'Could not load history.' : null,
        automation: automation.status === 'fulfilled' ? automation.value : null,
        automationError: automation.status === 'rejected' ? 'Automatic tracking status could not be loaded. History is still available.' : null,
      })
      pending = false
    }
    void load()
    const timer = window.setInterval(() => { void load() }, 60_000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [requestKey, season, leagueId, week, position, offset])

  async function sync() {
    setSyncing(true)
    setSyncError(null)
    setNotice(null)
    try {
      const result = await syncAccuracy(season, leagueId)
      setNotice(result.checked_count
        ? `Checked ${result.checked_count} predictions; ${result.updated_count} results added or corrected.`
        : 'No published results to compare yet. Games need to be at least 12 hours past kickoff and have published scores and player stats.')
      setReload((value) => value + 1)
    } catch (caught) {
      setSyncError(caught instanceof Error ? caught.message : 'Could not sync results.')
    } finally {
      setSyncing(false)
    }
  }

  function resetPage() {
    setOffset(0)
    setNotice(null)
    setSyncError(null)
  }

  function refreshHistory() {
    setSyncError(null)
    setNotice(null)
    setReload((value) => value + 1)
  }

  const maxError = Math.max(1, ...(report?.weekly_trend.map((row) => row.mae ?? 0) ?? []))

  return (
    <div className="space-y-5">
      <section className={panelClass}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black text-slate-950">Prediction accuracy</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-500">The latest projection saved before each player's kickoff is kept for comparison. Predictions made after kickoff never enter this history.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" disabled={loading || syncing} onClick={refreshHistory} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold disabled:opacity-50">Refresh history</button>
            <button type="button" disabled={loading || syncing} onClick={sync} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{syncing ? 'Syncing results...' : 'Sync results'}</button>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <label className="grid gap-1 text-xs font-bold text-slate-500">Season
            <select value={season} disabled={syncing} onChange={(event) => { setSeason(Number(event.target.value)); resetPage() }} className={selectClass}>
              {seasons.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-xs font-bold text-slate-500">History
            <select value={source} disabled={syncing} onChange={(event) => { setSource(event.target.value); resetPage() }} className={selectClass}>
              <option value="league">This league's projections</option>
              <option value="weekly">Weekly NFL projections</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs font-bold text-slate-500">Week
            <select value={week} disabled={syncing} onChange={(event) => { setWeek(event.target.value); resetPage() }} className={selectClass}>
              <option value="">All weeks</option>
              {weeks.map((value) => <option key={value} value={value}>Week {value}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-xs font-bold text-slate-500">Position
            <select value={position} disabled={syncing} onChange={(event) => { setPosition(event.target.value); resetPage() }} className={selectClass}>
              <option value="">All positions</option>
              {positions.map((value) => <option key={value} value={value}>{value === 'DST' ? 'D/ST' : value}</option>)}
            </select>
          </label>
        </div>
        <p className="mt-4 text-xs leading-5 text-slate-500">{report?.scoring ?? 'Full PPR offense; app K/DST scoring. Custom ESPN scoring may differ.'} League history includes injury adjustments from scheduled captures and viewed pages. You can also sync manually after published stats arrive; this can take longer for K/DST. Missing stats stay pending.</p>
      </section>

      {!loading && <AccuracyAutomation status={loaded?.automation ?? null} error={loaded?.automationError ?? null} />}

      {error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error} <button type="button" onClick={refreshHistory} className="ml-2 font-bold underline">Retry history</button></p>}
      {notice && <p role="status" className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">{notice}</p>}
      {loading && <p role="status" className="p-6 text-center text-sm text-slate-500">Loading saved history...</p>}

      {report && <>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {([
            ['Saved predictions', String(report.summary.saved)],
            ['Compared / pending', `${report.summary.scored} / ${report.summary.pending}`],
            ['Average absolute error', `${points(report.summary.mae)} pts`],
            ['Average signed error', `${points(report.summary.bias, true)} pts`],
          ]).map(([label, value]) => <div key={label} className={panelClass}><p className="text-xs font-bold text-slate-500">{label}</p><p className="mt-2 text-2xl font-black tabular-nums">{value}</p></div>)}
        </div>
        <p className="text-xs text-slate-500">Lower absolute error is better. Signed error = projected minus actual: positive means overprediction. Averages use scored predictions only.</p>
        <AccuracyInsights report={report} />

        {report.summary.saved === 0 ? <section className={`${panelClass} py-12 text-center`}>
          <h2 className="text-lg font-black">No saved predictions for these filters yet</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500">Keep the backend running before games for automatic captures, or open My team, Matchup, or Players to save projections yourself. Tracking starts from now; past projections cannot be reconstructed fairly.</p>
        </section> : <>
          <div className="grid gap-5 lg:grid-cols-2">
            <section className={panelClass}>
              <h2 className="font-black">Accuracy by position</h2>
              <div className="mt-4 overflow-x-auto"><table className="w-full text-right text-sm tabular-nums">
                <thead className="text-xs text-slate-500"><tr><th className="pb-3 text-left">Position</th><th>Scored</th><th>Pending</th><th>Avg error</th><th>Signed</th></tr></thead>
                <tbody>{report.by_position.filter((row) => row.saved > 0).map((row) => <tr key={row.position} className="border-t border-slate-100"><th className="py-3 text-left">{row.position === 'DST' ? 'D/ST' : row.position}</th><td>{row.scored}</td><td>{row.pending}</td><td>{points(row.mae)}</td><td>{points(row.bias, true)}</td></tr>)}</tbody>
              </table></div>
            </section>
            <section className={panelClass}>
              <h2 className="font-black">Weekly trend</h2>
              <p className="mt-1 text-xs text-slate-500">All weeks in this season, using the position filter. Select a week to see its players.</p>
              <div className="mt-4 space-y-3">{report.weekly_trend.map((row) => <div key={row.week} className="flex items-center gap-3 text-xs">
                <button type="button" disabled={syncing} onClick={() => { setWeek(String(row.week)); resetPage() }} className="w-14 shrink-0 text-left font-bold underline">Week {row.week}</button>
                <div className="h-3 flex-1 rounded-full bg-slate-100" aria-hidden="true"><div className="h-3 rounded-full bg-emerald-500" style={{ width: `${((row.mae ?? 0) / maxError) * 100}%` }} /></div>
                <span className="w-32 text-right tabular-nums">{row.mae === null ? 'Pending' : `${points(row.mae)} pts (${row.scored})`}</span>
              </div>)}</div>
            </section>
          </div>

          <section className={panelClass}>
            <h2 className="font-black">Model and fallback performance</h2>
            <div className="mt-4 overflow-x-auto"><table className="w-full text-right text-sm tabular-nums">
              <thead className="text-xs text-slate-500"><tr><th className="pb-3 text-left">Model / method</th><th>Revision</th><th>Scored</th><th>Avg error</th><th>Signed</th></tr></thead>
              <tbody>{report.by_model.map((row) => <tr key={`${row.model_version}:${row.model_revision}:${row.projection_method}`} className="border-t border-slate-100"><th className="py-3 text-left">{row.model_version}<span className="ml-2 text-xs font-normal text-slate-500">{methodLabel(row.projection_method)}</span></th><td title={row.model_revision}>{row.model_revision.slice(0, 8)}</td><td>{row.scored}</td><td>{points(row.mae)}</td><td>{points(row.bias, true)}</td></tr>)}</tbody>
            </table></div>
          </section>

          <section className={`${panelClass} overflow-hidden`}>
            <h2 className="font-black">Projected vs. actual</h2>
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-175 text-right text-sm tabular-nums">
              <thead className="text-xs text-slate-500"><tr><th className="pb-3 text-left">Player</th><th>Week</th><th>AI</th><th>ESPN · PPR</th><th>Actual</th><th>AI difference</th><th>Saved range</th><th>Saved before kickoff</th></tr></thead>
              <tbody>{report.records.map((row) => <tr key={`${row.week}:${row.position}:${row.player_id}`} className="border-t border-slate-100">
                <th className="py-3 text-left"><p>{row.player_name ?? row.player_id}</p><p className="mt-1 text-xs font-normal text-slate-500">{row.position} · {row.team} vs {row.opponent_team} · {methodLabel(row.projection_method)}</p></th>
                <td>{row.week}</td><td>{points(row.predicted_points)}</td><td title={row.espn_recorded_at ? `ESPN projected stats converted to full PPR; observed ${new Date(row.espn_recorded_at).toLocaleString()}` : 'No ESPN forecast saved before kickoff'}>{points(row.espn_predicted_points ?? null)}</td><td>{row.actual_points === null ? <span className="text-xs text-slate-500">Pending</span> : points(row.actual_points)}</td><td>{points(row.error, true)}</td>
                <td className="whitespace-nowrap text-xs text-slate-500">{row.floor_points != null && row.ceiling_points != null ? <>{points(row.floor_points)}–{points(row.ceiling_points)}<span className="block">{row.range_result === 'inside' ? 'Inside range' : row.range_result === 'below' ? 'Below floor' : row.range_result === 'above' ? 'Above ceiling' : 'Awaiting result'}</span></> : 'Not saved'}</td>
                <td className="text-xs text-slate-500" title={`Generated: ${new Date(row.generated_at).toLocaleString()} | Kickoff: ${new Date(row.kickoff).toLocaleString()} | ${row.model_version} ${row.model_revision}`}>{new Date(row.recorded_at).toLocaleString()}</td>
              </tr>)}</tbody>
            </table></div>
            <div className="mt-4 flex items-center justify-between gap-3 text-sm">
              <button type="button" disabled={offset === 0 || syncing} onClick={() => setOffset(Math.max(0, offset - report.limit))} className="rounded-lg border border-slate-200 px-3 py-2 font-bold disabled:opacity-40">Previous</button>
              <span className="text-xs text-slate-500">{offset + 1}–{offset + report.records.length} of {report.summary.saved}</span>
              <button type="button" disabled={offset + report.records.length >= report.summary.saved || syncing} onClick={() => setOffset(offset + report.limit)} className="rounded-lg border border-slate-200 px-3 py-2 font-bold disabled:opacity-40">Next</button>
            </div>
          </section>
        </>}
      </>}
    </div>
  )
}
