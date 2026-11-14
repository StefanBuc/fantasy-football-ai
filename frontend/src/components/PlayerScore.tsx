import type { ProjectionDisplay, LivePlayerScore, LiveScoreResponse } from '../types/api'
import { scoreDisplay } from '../lib/scoreDisplay'

type Props = { player: ProjectionDisplay & { predicted_points: number | null; is_on_bye?: boolean };
  live?: LivePlayerScore }

export function PlayerScore({ player, live }: Props) {
  const score = scoreDisplay(player, live)
  const format = (value: number | null) => value === null ? '\u2014' : value.toFixed(1)
  if (score.bye) return <div className="text-right text-xs font-bold text-sky-700 dark:text-sky-300">BYE</div>
  return <div className="text-right tabular-nums">
    {score.started ? <>
      <p className="text-[10px] font-black uppercase text-emerald-700 dark:text-emerald-300" title={live?.game_detail ?? undefined}>
        {score.state === 'final' ? 'Final · ESPN' : score.state === 'postponed' ? 'Postponed' : score.state === 'unknown' ? 'Status unavailable' : 'Live · ESPN'}
      </p>
      <p className="text-2xl font-black text-emerald-700 dark:text-emerald-300">{format(score.actual)}</p>
      {score.actual === null && <p className="text-[10px] text-slate-500">Score unavailable</p>}
      <p className="mt-1 text-xs font-bold text-slate-500 dark:text-slate-300">AI pregame {format(score.prediction)}</p>
      {score.prediction === null && <p className="text-[10px] text-slate-500">Not saved before kickoff</p>}
    </> : <>
      <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400" title={score.rangeNote ?? undefined}>Ceiling {format(score.ceiling)}</p>
      <p className="text-xl font-black text-slate-950 dark:text-white">{format(score.prediction)}</p>
      <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400" title={score.rangeNote ?? undefined}>Floor {format(score.floor)}</p>
      <p className="text-[9px] uppercase tracking-wide text-slate-400" title={score.rangeNote ?? undefined}>{score.floor === null ? 'Range unavailable' : 'AI estimate'}</p>
    </>}
  </div>
}

export function LiveScoreNote({ data, error }: { data: LiveScoreResponse | null; error: string | null }) {
  return <div className="mt-3 text-xs leading-5 text-slate-500 dark:text-slate-400">
    <p>{data?.note ?? 'Live scores use ESPN league scoring; AI predictions use full PPR and app K/DST rules. Estimated floor/ceiling values are not limits or guarantees.'}</p>
    {data && <p>Score feed checked {new Date(data.checked_at).toLocaleTimeString()}. Updates every 30 seconds while this page is visible.</p>}
    {error && <p role="status" className="font-bold text-amber-700 dark:text-amber-300">Live updates unavailable. {data ? 'Showing the last received scores; they may be stale.' : error}</p>}
  </div>
}
