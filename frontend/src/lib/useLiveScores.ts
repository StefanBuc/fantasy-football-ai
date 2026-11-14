import { useEffect, useState } from 'react'
import { getLiveScores } from './api'
import type { LivePlayerDescriptor, LiveScoreResponse } from '../types/api'

export function useLiveScores(leagueId: number, season: number, week: number,
  mode: 'public' | 'local', players: LivePlayerDescriptor[]) {
  const descriptorKey = JSON.stringify(players.map(({ espn_id, player_id, position, team }) =>
    ({ espn_id, player_id, position, team })).sort((a, b) => a.espn_id - b.espn_id))
  const key = JSON.stringify([leagueId, season, week, mode, descriptorKey])
  const [loaded, setLoaded] = useState<{ key: string; data: LiveScoreResponse | null; error: string | null; observedAt: number } | null>(null)

  useEffect(() => {
    let cancelled = false
    let pending = false
    const descriptors: LivePlayerDescriptor[] = JSON.parse(descriptorKey)
    async function update() {
      if (pending || document.hidden || descriptors.length === 0) return
      pending = true
      try {
        const data = await getLiveScores({ league_id: leagueId, season, week, players: descriptors }, mode)
        if (!cancelled) setLoaded({ key, data, error: null, observedAt: Date.now() })
      } catch (caught) {
        if (!cancelled) setLoaded((previous) => ({ key,
          data: previous?.key === key ? previous.data : null,
          error: caught instanceof Error ? caught.message : 'Live score updates unavailable.',
          observedAt: Date.now(),
        }))
      } finally {
        pending = false
      }
    }
    void update()
    const timer = window.setInterval(() => { void update() }, 30_000)
    const visible = () => { if (!document.hidden) void update() }
    document.addEventListener('visibilitychange', visible)
    return () => { cancelled = true; window.clearInterval(timer); document.removeEventListener('visibilitychange', visible) }
  }, [key, descriptorKey, leagueId, season, week, mode])

  const current = loaded?.key === key ? loaded : null
  const stale = current?.data && current.observedAt - new Date(current.data.checked_at).getTime() > 90_000
  return { data: current?.data ?? null, error: current?.error ?? null,
    scores: new Map(current?.data?.players.map((player) => [player.espn_id,
      stale && player.game_state === 'pregame' ? { ...player, game_state: 'unknown' as const } : player]) ?? []) }
}
