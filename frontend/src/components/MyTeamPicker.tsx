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

  return <div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="grid w-full min-w-0 gap-2 sm:w-auto">
        <span className="text-xs font-black text-slate-500">My team</span>
        <select aria-label="My team" value={draft ?? (value === null ? '' : String(value))} disabled={busy} onChange={(event) => void save(event.target.value)}
          className="h-11 w-full min-w-0 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100 sm:w-80">
          <option value="">Choose your team</option>
          {teams.map((team) => <option key={team.team_id} value={team.team_id}>{team.team_name}</option>)}
        </select>
      </label>
      <button type="button" disabled={busy || value === null} onClick={onOpen}
        className="h-11 rounded-lg bg-emerald-600 px-4 text-sm font-bold text-white disabled:opacity-40">Go to my team</button>
    </div>
    <p role="status" className="mt-3 text-xs text-slate-500">{busy ? 'Saving your team...' : saved ? 'My team saved.' : 'Changes save automatically. Browsing other teams keeps this choice.'}</p>
    {error && <p role="alert" className="mt-2 text-sm text-rose-700 dark:text-rose-300">{error}</p>}
  </div>
}
