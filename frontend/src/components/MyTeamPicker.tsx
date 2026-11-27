import { useState } from 'react'
import type { ESPNTeamSummary } from '../types/api'

type Props = {
  teams: ESPNTeamSummary[]
  value: number | null
  onChange: (teamId: number | null) => Promise<void>
  onOpen: () => void
}

export function MyTeamPicker({ teams, value, onChange, onOpen }: Props) {
  const [draft, setDraft] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  async function save(next: string) {
    setDraft(next); setBusy(true); setError(null); setSaved(false)
    try { await onChange(next ? Number(next) : null); setSaved(true) }
    catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Your team could not be saved. Try again.')
    } finally { setBusy(false); setDraft(null) }
  }

  return <div className="mx-auto max-w-7xl px-4 pb-4 sm:px-8">
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3">
      <label className="flex w-full min-w-0 items-center gap-3 sm:w-auto">
        <span className="shrink-0 text-xs font-black text-slate-300">My team</span>
        <select aria-label="My team" value={draft ?? (value === null ? '' : String(value))} disabled={busy} onChange={(event) => void save(event.target.value)}
          className="h-10 min-w-0 max-w-full flex-1 rounded-lg border border-white/15 bg-slate-900 px-3 text-xs font-bold text-white outline-none focus:border-lime-300 sm:w-64 sm:max-w-xs">
          <option value="">Choose your team</option>
          {teams.map((team) => <option key={team.team_id} value={team.team_id}>{team.team_name}</option>)}
        </select>
      </label>
      <button type="button" disabled={busy || value === null} onClick={onOpen}
        className="rounded-lg border border-lime-300/30 px-3 py-2 text-xs font-bold text-lime-300 disabled:opacity-40">Go to my team</button>
      <p role="status" className="min-w-0 flex-1 text-[11px] text-slate-400">{busy ? 'Saving your team...' : saved ? 'My team saved.' : 'Saved for this league. Browsing other teams keeps this choice.'}</p>
    </div>
    {error && <p role="alert" className="mt-2 text-xs text-rose-300">{error}</p>}
  </div>
}
