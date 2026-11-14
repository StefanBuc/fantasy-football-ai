import type { AutomationJob, AutomationStatus } from '../types/api'

function time(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Not yet'
}

function JobStatus({ title, job }: { title: string; job: AutomationJob | null }) {
  return <div className="rounded-xl border border-slate-200 p-4">
    <h3 className="text-sm font-black">{title}{job?.state === 'running' && <span role="status" className="ml-2 text-emerald-600 dark:text-emerald-300">Running...</span>}</h3>
    <p className="mt-2 text-xs text-slate-500">Last success: <span className="font-bold">{time(job?.last_success_at ?? null)}</span></p>
    {job?.last_finished_at && <p className="mt-1 text-xs text-slate-500">Last attempt finished: {time(job.last_finished_at)}</p>}
    {job?.state === 'success' && job.result && <p className="mt-2 text-xs text-slate-500">
      {'saved_count' in job.result ? `${job.result.saved_count} pregame predictions saved${job.week ? ` for Week ${job.week}` : ''}.`
        : `${job.result.checked_count} predictions compared; ${job.result.updated_count} results added or corrected.`}
    </p>}
    {job?.last_error && <p role="alert" className="mt-2 text-xs font-bold text-amber-700 dark:text-amber-300">{job.last_error}</p>}
    {job?.state === 'error' && job.next_run_at && <p className="mt-1 text-xs text-slate-500">Retry due: {time(job.next_run_at)}</p>}
  </div>
}

export function AccuracyAutomation({ status, error }: { status: AutomationStatus | null; error: string | null }) {
  return <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" aria-label="Automatic tracking status">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-black">Automatic tracking</h2>
      <span className="text-xs font-bold text-slate-500">{status ? status.enabled ? 'Enabled' : 'Disabled' : 'Status unavailable'}</span>
    </div>
    {error && <p role="alert" className="mt-2 text-sm text-amber-700 dark:text-amber-300">{error}</p>}
    {status && <>
      <p className="mt-2 text-xs leading-5 text-slate-500">{status.note}</p>
      {status.capture_enabled && <p className="mt-1 text-xs leading-5 text-slate-500">Captures every {status.capture_interval_minutes} minutes during the {status.capture_window_hours} hours before kickoff, including league rosters and available players. Weekly history covers all six positions. Results sync from 8 a.m. Eastern the following day, at least 12 hours after kickoff, then every {status.sync_interval_hours} hours for two weeks.</p>}
      <p className="mt-2 text-xs text-slate-500">Last scheduler check: {time(status.last_checked_at)}. Status and history refresh every minute while this page is open.</p>
      {status.worker_error && <p role="alert" className="mt-2 text-xs font-bold text-amber-700 dark:text-amber-300">{status.worker_error}</p>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <JobStatus title="Pregame capture" job={status.capture} />
        <JobStatus title="Results sync" job={status.sync} />
      </div>
    </>}
  </section>
}
