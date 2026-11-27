import { sendJson } from './api.ts'

export type DashboardView = 'team' | 'optimized' | 'trade' | 'matchup' | 'players' | 'league' | 'accuracy'
export type OwnerPreferences = { username: string; theme: 'system' | 'light' | 'dark'; active_connection: string | null }
export type OwnerSession = { auth_enabled: boolean; authenticated: boolean; configured?: boolean;
  csrf_token?: string; public_url?: string; login_origin?: string; owner?: OwnerPreferences | null }
export type SavedConnection = { id: string; league_id: number; season: number; name: string;
  mode: 'public' | 'private'; preferred_team_id: number | null; my_team_id: number | null; default_view: DashboardView;
  status: 'connected' | 'reauth_required' }
export type ConnectionInput = { league_id: number; season: number; mode: 'public' | 'private'; swid?: string; espn_s2?: string }

let pendingSession: Promise<OwnerSession> | null = null
export function getSession() {
  if (!pendingSession) pendingSession = sendJson<OwnerSession>('/api/auth/session', undefined, 'GET')
    .finally(() => { pendingSession = null })
  return pendingSession
}
export const signIn = (username: string, password: string, remember: boolean) =>
  sendJson<OwnerSession>('/api/auth/login', { username, password, remember })
export const signOut = (everywhere = false) => sendJson(`/api/auth/logout?everywhere=${everywhere}`, {})
export const getConnections = () => sendJson<{ connections: SavedConnection[]; preferences: OwnerPreferences }>('/api/account/connections', undefined, 'GET')
export const saveConnection = (input: ConnectionInput, id?: string) => sendJson<SavedConnection>(
  id ? `/api/account/connections/${id}` : '/api/account/connections', input, id ? 'PUT' : 'POST')
export const deleteConnection = (id: string) => sendJson(`/api/account/connections/${id}`, {}, 'DELETE')
export const importConfiguredLeague = () => sendJson<SavedConnection>('/api/account/import-configured-league', {})
export const saveOwnerPreferences = (input: OwnerPreferences) => sendJson<OwnerPreferences>('/api/account/preferences', input, 'PATCH')
export const saveConnectionPreferences = (id: string, preferred_team_id: number, default_view: DashboardView) =>
  sendJson<SavedConnection>(`/api/account/connections/${id}/preferences`, { preferred_team_id, default_view }, 'PATCH')
export const saveMyTeam = (id: string, team_id: number | null) =>
  sendJson<SavedConnection>(`/api/account/connections/${id}/my-team`, { team_id }, 'PATCH')
