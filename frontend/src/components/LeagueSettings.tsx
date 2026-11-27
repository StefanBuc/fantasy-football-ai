import type { ESPNLeague } from '../types/api'
import { MyTeamPicker } from './MyTeamPicker'

type Props = {
  league: ESPNLeague
  myTeamId: number | null
  onMyTeamChange: (teamId: number | null) => Promise<void>
  onOpenMyTeam: () => void
}

export function LeagueSettings({ league, myTeamId, onMyTeamChange, onOpenMyTeam }: Props) {
  return <div className="max-w-3xl space-y-5">
    <div>
      <h1 className="text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">Settings</h1>
      <p className="mt-2 text-sm text-slate-500">Preferences for {league.league_name} · {league.season} season.</p>
    </div>
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6" aria-labelledby="my-team-settings">
      <h2 id="my-team-settings" className="font-black">Your team</h2>
      <p className="mt-2 text-sm leading-6 text-slate-500">Choose the team you manage. The My team tab opens this roster, and your choice is saved to your account for this league.</p>
      <div className="mt-5">
        <MyTeamPicker teams={league.teams} value={myTeamId} onChange={onMyTeamChange} onOpen={onOpenMyTeam} />
      </div>
    </section>
  </div>
}
