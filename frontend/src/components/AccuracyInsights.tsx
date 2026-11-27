import type { AccuracyReport } from '../types/api'

const panel = 'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm'
const number = (value: number | null | undefined) => value == null ? '—' : value.toFixed(2)
const pct = (value: number | null | undefined) => value == null ? '—' : `${value.toFixed(1)}%`

export function AccuracyInsights({ report }: { report: AccuracyReport }) {
  const range = report.range_coverage, errors = report.error_distribution, espn = report.espn_comparison
  // Allow an older API response during a rolling frontend/backend update.
  if (!range || !errors || !espn) return null
  return <div className="space-y-5">
    <section className={panel} aria-label="Prediction error distribution">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-black">How close were the predictions?</h2><span className="text-xs text-slate-500">{errors.count.toLocaleString()} graded forecasts</span></div>
      <p className="mt-2 text-xs leading-6 text-slate-500">These figures use every graded prediction matching your filters, including rows on other pages. The thresholds below overlap: within 2 points also counts toward within 5 and 10.</p>
      <div className="mt-4 grid grid-cols-3 gap-3">{[
        ['Within 2 points', errors.within_two_pct], ['Within 5 points', errors.within_five_pct], ['Within 10 points', errors.within_ten_pct],
      ].map(([label, value]) => <div key={String(label)} className="rounded-xl border border-slate-200 p-3 sm:p-4"><p className="text-[11px] font-bold text-slate-500">{label}</p><p className="mt-2 text-xl font-black sm:text-2xl">{pct(value as number | null)}</p></div>)}</div>
      {errors.count ? <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">{errors.buckets.map((bucket, index) => <div key={bucket.label} className="grid grid-cols-[112px_1fr_74px] items-center gap-3 text-[11px] sm:text-xs"><span className="font-bold text-slate-500">{bucket.label}</span><div aria-hidden="true" className="h-3 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${index < 3 ? 'bg-amber-500' : index === 3 ? 'bg-emerald-500' : 'bg-sky-500'}`} style={{ width: `${bucket.pct ?? 0}%` }} /></div><span className="text-right tabular-nums">{bucket.count} · {pct(bucket.pct)}</span></div>)}</div>
        <dl className="space-y-4 rounded-xl bg-slate-50 p-4 text-sm">
          <div><dt className="text-xs font-bold text-slate-500">Median absolute miss</dt><dd className="mt-1 font-black">{number(errors.median_absolute_error)} pts</dd></div>
          <div><dt className="text-xs font-bold text-slate-500">90th percentile absolute miss</dt><dd className="mt-1 font-black">{number(errors.p90_absolute_error)} pts</dd><p className="mt-1 text-[11px] text-slate-500">About 90% of misses were this size or smaller.</p></div>
          <div><dt className="text-xs font-bold text-slate-500">Root mean square error</dt><dd className="mt-1 font-black">{number(errors.rmse)} pts</dd><p className="mt-1 text-[11px] text-slate-500">Gives larger misses more weight.</p></div>
        </dl>
      </div> : <p className="mt-5 text-sm text-slate-500">Error patterns will appear once published results are synced.</p>}
      <p className="mt-4 text-xs text-slate-500">Under = forecast below actual points. Over = forecast above actual points.</p>
    </section>

    <section className={panel} aria-label="Floor and ceiling coverage">
      <h2 className="font-black">Did the floor/ceiling range hold up?</h2>
      <p className="mt-2 text-xs leading-6 text-slate-500">Coverage measures how often the final score landed between the saved pregame floor and ceiling, including either boundary. Current calibrated ranges target 80% coverage; they are not guaranteed limits.</p>
      <div className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-4"><div><p className="text-3xl font-black">{pct(range.coverage_pct)}</p><p className="mt-1 text-xs text-slate-500">{range.inside} inside / {range.count} graded forecasts with saved ranges</p></div><div className="text-sm"><p><strong>{range.below}</strong> below the floor · <strong>{range.above}</strong> above the ceiling</p><p className="mt-2 text-xs text-slate-500">Average range width: {number(range.average_width)} pts</p></div></div>
      {range.count ? <div className="mt-5 flex h-3 overflow-hidden rounded-full bg-slate-100" aria-label="Scores below, inside, and above the range">{[[range.below, 'bg-amber-500'], [range.inside, 'bg-emerald-500'], [range.above, 'bg-sky-500']].map(([count, color], index) => <div key={index} className={String(color)} style={{ width: `${100 * Number(count) / range.count}%` }} />)}</div> : <p className="mt-5 text-sm text-slate-500">No graded forecasts with saved ranges match these filters yet.</p>}
      <p className="mt-3 text-xs text-slate-500">{range.missing} graded forecasts had no usable saved range and are excluded from coverage.</p>
      {range.by_position.some((row) => row.count) && <div className="mt-4 overflow-x-auto"><table className="w-full text-right text-xs"><thead className="text-slate-500"><tr><th className="pb-3 text-left">Position</th><th>Inside / graded</th><th>Below</th><th>Above</th><th>Coverage</th></tr></thead><tbody>{range.by_position.filter((row) => row.count).map((row) => <tr key={row.position} className="border-t border-slate-100"><th className="py-3 text-left">{row.position === 'DST' ? 'D/ST' : row.position}</th><td>{row.inside} / {row.count}</td><td>{row.below}</td><td>{row.above}</td><td className="font-bold">{pct(row.coverage_pct)}</td></tr>)}</tbody></table></div>}
    </section>

    <section className={panel} aria-label="AI versus ESPN comparison">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-black">AI vs ESPN · same players, same scoring</h2><span className="text-xs text-slate-500">{espn.count} paired results · {espn.pending} awaiting results</span></div>
      <p className="mt-2 text-xs leading-6 text-slate-500">ESPN's week-specific projected QB/RB/WR/TE stats are converted to full-PPR offense, then compared with the same published NFL results as the AI. These values may differ from ESPN's displayed points in a custom-scoring league. K/DST are excluded from this comparison.</p>
      {espn.count ? <>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">{[['AI average miss', espn.ai_mae], ['ESPN average miss', espn.espn_mae], ['AI error reduction', espn.mae_improvement]].map(([label, value]) => <div key={String(label)} className="rounded-xl border border-slate-200 p-4"><p className="text-xs font-bold text-slate-500">{label}</p><p className="mt-2 text-2xl font-black">{number(value as number | null)} pts</p></div>)}</div>
        <p className="mt-3 text-xs text-slate-500">Positive error reduction favors the AI; negative favors ESPN. Both average errors use exactly the same {espn.count} results.</p>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm"><span><strong>{espn.ai_closer}</strong> AI closer</span><span><strong>{espn.espn_closer}</strong> ESPN closer</span><span><strong>{espn.ties}</strong> ties</span></div>
        <div className="mt-5 overflow-x-auto"><table className="w-full text-right text-xs"><thead className="text-slate-500"><tr><th className="pb-3 text-left">Position</th><th>Paired results</th><th>AI avg miss</th><th>ESPN avg miss</th></tr></thead><tbody>{espn.by_position.filter((row) => row.count).map((row) => <tr key={row.position} className="border-t border-slate-100"><th className="py-3 text-left">{row.position}</th><td>{row.count}</td><td>{number(row.ai_mae)}</td><td>{number(row.espn_mae)}</td></tr>)}</tbody></table></div>
      </> : <p className="mt-5 text-sm text-slate-500">Collecting paired forecasts. ESPN comparisons begin with newly captured pregame projections; older ESPN forecasts cannot be reconstructed fairly.</p>}
      <p className="mt-4 text-xs leading-6 text-slate-500">Only ESPN forecasts observed before kickoff qualify. The comparison includes model and fallback estimates. A small sample does not establish which forecaster is consistently better.</p>
    </section>
  </div>
}
