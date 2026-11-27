import { useEffect, useState } from 'react'
import { getRetrainingStatus } from '../lib/api'
import type { RetrainingStatus as Status } from '../types/api'

const date = (value?: string | null) => value ? new Date(value).toLocaleString() : 'Not yet'
const points = (value?: number) => value == null ? '\u2014' : `${value.toFixed(2)} pts`

export function RetrainingStatus() {
  const [status, setStatus] = useState<Status | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [observedAt, setObservedAt] = useState<number | null>(null)
  useEffect(() => {
    let active = true, pending = false
    async function load() {
      if (pending) return
      pending = true
      try {
        const next = await getRetrainingStatus()
        if (active) { setStatus(next); setError(null) }
      } catch {
        if (active) setError('Training status could not be loaded. Try again shortly.')
      } finally { if (active) setObservedAt(Date.now()); pending = false }
    }
    void load()
    const timer = window.setInterval(() => { void load() }, 60_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])
  const workerStale = observedAt != null && status?.worker_checked_at && observedAt - new Date(status.worker_checked_at).getTime() > 5 * 60_000
  return <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6" aria-labelledby="retraining-title">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 id="retraining-title" className="font-black">Model retraining</h2>
      <span className="text-xs font-bold text-slate-500">{!status ? 'Loading...' : !status.enabled ? 'Disabled' : workerStale ? 'Worker not recently seen'
        : status.state === 'running' ? `Training ${status.current_position ?? ''}`
        : status.state === 'complete' ? 'Evaluation complete' : status.state === 'error' ? 'Retry scheduled' : 'Waiting for training'}</span>
    </div>
    <p className="mt-2 text-sm leading-6 text-slate-500">New candidates are compared with the current model on later completed games. A candidate replaces it only after passing accuracy, bias, baseline, and floor/ceiling checks. Saved pregame predictions stay unchanged.</p>
    {error && <p role="alert" className="mt-3 text-sm text-amber-700 dark:text-amber-300">{error}</p>}
    {status && <>
      <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
        <div><dt className="text-slate-500">Next weekly check (your local time)</dt><dd className="mt-1 font-bold">{status.enabled ? date(status.next_scheduled_at) : '\u2014'}</dd></div>
        <div><dt className="text-slate-500">Last evaluation finished</dt><dd className="mt-1 font-bold">{date(status.finished_at)}</dd></div>
        <div><dt className="text-slate-500">Training device</dt><dd className="mt-1 font-bold">{status.device.toUpperCase()}</dd></div>
        <div><dt className="text-slate-500">Last worker check</dt><dd className="mt-1 font-bold">{date(status.worker_checked_at)}</dd></div>
      </dl>
      {!status.worker_checked_at && status.enabled && <p className="mt-3 text-xs text-slate-500">Waiting for the training worker to connect.</p>}
      {status.note && <p className="mt-3 text-xs text-slate-500">{status.note}</p>}
      {status.last_error && <p role="alert" className="mt-3 text-xs text-amber-700 dark:text-amber-300">{status.last_error}</p>}
      {status.retry_at && <p className="mt-2 text-xs text-slate-500">Retry after {date(status.retry_at)}.</p>}
      {Object.keys(status.positions).length > 0 && <div className="mt-5 overflow-x-auto">
        <table className="w-full text-left text-xs"><thead className="text-slate-500"><tr><th className="pb-2">Position</th><th>Candidate avg miss</th><th>Previous avg miss</th><th>Decision</th></tr></thead>
          <tbody>{Object.entries(status.positions).map(([position, result]) => <tr key={position} className="border-t border-slate-100">
            <th className="py-3">{position === 'DST' ? 'D/ST' : position}</th><td>{points(result.candidate_mae)}</td><td>{points(result.incumbent_mae)}</td>
            <td className="max-w-xs py-3"><p className="font-bold">{result.promote ? 'Promoted' : 'Kept current model'}</p><p className="mt-1 text-slate-500">{result.error ?? result.reason}{result.count != null ? ` ${result.count} evaluation games.` : ''}</p></td>
          </tr>)}</tbody>
        </table>
        <p className="mt-2 text-xs leading-5 text-slate-500">These errors use the same held-out player games for both models. They are separate from the live forecast history on the Accuracy page.</p>
      </div>}
    </>}
  </section>
}
