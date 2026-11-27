import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import LegacyApp from '../App'
import { LeagueDashboard } from './LeagueDashboard'
import { ThemeToggle } from './ThemeToggle'
import { configureSession, sendJson, setActiveConnection } from '../lib/api'
import { viewCache } from '../lib/viewCache'
import { deleteConnection, getConnections, getSession, importConfiguredLeague, saveConnection,
  saveConnectionPreferences, saveOwnerPreferences, signIn, signOut,
  type DashboardView, type OwnerPreferences, type OwnerSession, type SavedConnection } from '../lib/account'
import type { ESPNLeague } from '../types/api'

const panel = 'rounded-2xl border border-slate-200 bg-white p-6 shadow-sm'
const field = 'mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm outline-none focus:border-emerald-500'
const button = 'rounded-lg bg-emerald-600 px-4 py-3 text-sm font-black text-white disabled:opacity-50'
const secondary = 'rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold disabled:opacity-50'
const message = (error: unknown) => error instanceof Error ? error.message : 'The request could not be completed.'
const currentSeason = new Date().getFullYear()

export default function AccountApp() {
  const [session, setSession] = useState<OwnerSession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [connections, setConnections] = useState<SavedConnection[]>([])
  const [preferences, setPreferences] = useState<OwnerPreferences | null>(null)
  const preferencesRef = useRef<OwnerPreferences | null>(null)
  const queue = useRef<Promise<unknown>>(Promise.resolve())
  const [dashboard, setDashboard] = useState<{ league: ESPNLeague; connection: SavedConnection } | null>(null)
  const [editing, setEditing] = useState<SavedConnection | null>(null)
  const [leagueId, setLeagueId] = useState('')
  const [season, setSeason] = useState(currentSeason)
  const [mode, setMode] = useState<'public' | 'private'>('private')
  const [swid, setSwid] = useState('')
  const [s2, setS2] = useState('')
  const [removeId, setRemoveId] = useState<string | null>(null)
  const mounted = useRef(false)
  const generation = useRef(0)
  const isDark = preferences?.theme === 'dark'
    || ((!preferences || preferences.theme === 'system') && window.matchMedia('(prefers-color-scheme: dark)').matches)

  const refreshSession = useCallback(async () => {
    try {
      const next = await getSession()
      if (!mounted.current) return
      configureSession(next.csrf_token ?? '', next.authenticated)
      setSession(next)
    } catch (caught) {
      if (mounted.current) setError(message(caught))
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    const timer = window.setTimeout(() => { void refreshSession() }, 0)
    const expired = () => {
      generation.current += 1
      configureSession('', false); setActiveConnection(null); viewCache.clear()
      setDashboard(null); setConnections([]); setPassword(''); setSwid(''); setS2('')
      setBusy(false)
      setSession(null); setError('Your session expired. Please sign in again.')
      void refreshSession()
    }
    window.addEventListener('fantasy-session-expired', expired)
    return () => { window.clearTimeout(timer); mounted.current = false; generation.current += 1; window.removeEventListener('fantasy-session-expired', expired) }
  }, [refreshSession])

  useEffect(() => {
    if (session?.auth_enabled) document.documentElement.classList.toggle('dark', isDark)
  }, [isDark, session?.auth_enabled])

  function persistPreferences(updates: Partial<OwnerPreferences>) {
    const previous = preferencesRef.current
    if (!previous) return
    const next = { ...previous, ...updates }
    preferencesRef.current = next; setPreferences(next)
    queue.current = queue.current.then(() => saveOwnerPreferences(next)).catch((caught) => { if (mounted.current) setError(message(caught)) })
  }

  async function openConnection(connection: SavedConnection, persist = true) {
    const version = generation.current
    setBusy(true); setError(null); viewCache.clear(); setActiveConnection(connection.id)
    try {
      const league = await sendJson<ESPNLeague>(`/api/account/connections/${connection.id}/connect`, {})
      if (!mounted.current || generation.current !== version) return
      setDashboard({ league, connection })
      if (persist) persistPreferences({ active_connection: connection.id })
    } catch (caught) {
      if (mounted.current && generation.current === version) { setActiveConnection(null); setError(message(caught)) }
    } finally {
      if (mounted.current && generation.current === version) setBusy(false)
    }
  }

  useEffect(() => {
    if (!session?.authenticated) return
    let active = true
    const load = async () => {
      setBusy(true)
      try {
        const data = await getConnections()
        if (!active) return
        setConnections(data.connections); setPreferences(data.preferences); preferencesRef.current = data.preferences
        const saved = data.connections.find((connection) => connection.id === data.preferences.active_connection)
        if (saved) await openConnection(saved, false)
      } catch (caught) { if (active) setError(message(caught)) }
      finally { if (active) setBusy(false) }
    }
    void load()
    return () => { active = false }
    // Load account state once after sign-in; changing preferences must not reopen a league.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.authenticated])

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      const next = await signIn(username.trim(), password, remember)
      configureSession(next.csrf_token ?? '', true)
      setPassword(''); viewCache.clear(); setSession({ ...session, ...next })
    } catch (caught) { setError(message(caught)); setPassword('') }
    finally { setBusy(false) }
  }

  async function logout(everywhere = false) {
    setBusy(true)
    try { await queue.current; await signOut(everywhere) }
    catch (caught) { setError(message(caught)); setBusy(false); return }
    generation.current += 1
    configureSession('', false); setActiveConnection(null); viewCache.clear()
    setDashboard(null); setConnections([]); setPreferences(null); preferencesRef.current = null
    setSession(null); setPassword(''); setSwid(''); setS2(''); setBusy(false)
    await refreshSession()
  }

  function clearForm() { setEditing(null); setLeagueId(''); setSwid(''); setS2('') }

  async function reloadConnections() {
    const data = await getConnections()
    setConnections(data.connections); setPreferences(data.preferences); preferencesRef.current = data.preferences
  }

  async function submitConnection(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      await saveConnection({ league_id: Number(leagueId), season, mode,
        ...(mode === 'private' ? { swid, espn_s2: s2 } : {}) }, editing?.id)
      clearForm(); viewCache.clear(); await reloadConnections()
    } catch (caught) { setError(message(caught)) }
    finally { setSwid(''); setS2(''); setBusy(false) }
  }

  async function importLeague() {
    setBusy(true); setError(null)
    try { await importConfiguredLeague(); await reloadConnections() }
    catch (caught) { setError(message(caught)) }
    finally { setBusy(false) }
  }

  async function removeConnection(id: string) {
    setBusy(true); setError(null)
    try { await deleteConnection(id); viewCache.clear(); setActiveConnection(null); setRemoveId(null); await reloadConnections() }
    catch (caught) { setError(message(caught)) }
    finally { setBusy(false) }
  }

  if (session && !session.auth_enabled) return <LegacyApp />
  if (dashboard && session?.authenticated) return <>
    {error && <p role="alert" className="bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
    <LeagueDashboard key={dashboard.connection.id} league={dashboard.league}
      connectionMode={dashboard.connection.mode === 'private' ? 'local' : 'public'}
      initialTeamId={dashboard.connection.preferred_team_id} initialView={dashboard.connection.default_view}
      onPreferencesChange={(team, view: DashboardView) => {
        queue.current = queue.current.then(() => saveConnectionPreferences(dashboard.connection.id, team, view))
          .catch((caught) => { if (mounted.current) setError(message(caught)) })
      }}
      onDisconnect={() => { setDashboard(null); setActiveConnection(null); viewCache.clear(); void reloadConnections().catch((caught) => setError(message(caught))) }}
      isDark={isDark} onToggleDark={() => persistPreferences({ theme: isDark ? 'light' : 'dark' })}
      onSignOut={() => void logout()} />
  </>

  const loginOrigin = session?.login_origin ?? session?.public_url
  const wrongOrigin = loginOrigin && new URL(loginOrigin).origin !== window.location.origin
  return <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-white">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4">
      <div className="flex items-center gap-3"><img src="/logo.svg" alt="" className="size-10" /><div><p className="font-black">Fantasy Football AI</p><p className="text-xs text-slate-500">{session?.authenticated ? `Signed in as ${preferences?.username ?? username}` : 'Owner access'}</p></div></div>
      {session?.authenticated && <div className="flex items-center gap-3"><ThemeToggle isDark={isDark} onToggle={() => persistPreferences({ theme: isDark ? 'light' : 'dark' })} /><button type="button" disabled={busy} onClick={() => void logout()} className={secondary}>Sign out</button></div>}
    </div></header>
    <main className="mx-auto max-w-6xl space-y-5 px-5 py-10">
      {error && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}{!session && <button type="button" className="ml-3 font-bold underline" onClick={() => void refreshSession()}>Retry</button>}</div>}
      {!session ? <p role="status" className="text-center text-sm text-slate-500">Checking your session...</p> : !session.authenticated ?
        <section className={`${panel} mx-auto max-w-md`}>
          <h1 className="text-2xl font-black">Sign in</h1>
          {wrongOrigin ? <p className="mt-4 text-sm leading-6">Use a configured address to sign in: <a href={loginOrigin} className="font-bold text-emerald-700 underline">{loginOrigin}</a></p>
            : session.configured === false ? <div className="mt-4 space-y-3 text-sm text-slate-600"><p>Create your owner account from the server terminal. Public signup is disabled.</p><code className="block overflow-x-auto rounded-lg bg-slate-100 p-3 text-xs">docker compose exec backend python -m app.scripts.manage_owner</code><button className={secondary} type="button" onClick={() => void refreshSession()}>Check again</button></div>
            : <form className="mt-5 space-y-4" onSubmit={(event) => void login(event)}>
              <label className="block text-sm font-bold">Username<input className={field} autoComplete="username" required maxLength={100} value={username} onChange={(event) => setUsername(event.target.value)} /></label>
              <label className="block text-sm font-bold">Password<input className={field} type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} className="accent-emerald-600" />Remember me on this device</label>
              <button className={`${button} w-full`} disabled={busy || !session.csrf_token} type="submit">{busy ? 'Signing in...' : 'Sign in'}</button>
              <p className="text-xs leading-5 text-slate-500">Owner account recovery is available through the server terminal.</p>
            </form>}
        </section> : <>
          <section className={panel}><h1 className="text-2xl font-black">Your leagues</h1><p className="mt-2 text-sm leading-6 text-slate-500">Saved connections follow your account across devices. ESPN credentials stay encrypted on the server.</p>
            {busy && <p role="status" className="mt-3 text-sm text-slate-500">Loading or validating your connection...</p>}
            <div className="mt-5 space-y-3">{connections.map((connection) => <article key={connection.id} className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 p-4">
              <div><h2 className="font-black">{connection.name}</h2><p className="mt-1 text-xs text-slate-500">{connection.season} · {connection.mode === 'private' ? 'Private league' : 'Public league'} · ID {connection.league_id}{preferences?.active_connection === connection.id ? ' · Opens automatically' : ''}</p>
                {connection.status === 'reauth_required' && <p className="mt-1 text-xs font-bold text-rose-700">ESPN connection expired. Update its cookies.</p>}</div>
              <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy} onClick={() => void openConnection(connection)}>Open league</button>
                <button type="button" className={secondary} disabled={busy} onClick={() => { setEditing(connection); setLeagueId(String(connection.league_id)); setSeason(connection.season); setMode(connection.mode); setSwid(''); setS2('') }}>Update</button>
                <button type="button" className={secondary} disabled={busy} onClick={() => { if (removeId === connection.id) void removeConnection(connection.id); else setRemoveId(connection.id) }}>{removeId === connection.id ? 'Confirm remove' : 'Remove'}</button></div>
            </article>)}</div>
            {!connections.length && !busy && <p className="mt-5 text-sm text-slate-500">Add your first league below.</p>}
            {removeId && <p className="mt-3 text-xs text-slate-500">Removing a connection stops its automatic league captures and deletes its saved credentials. Existing prediction history is retained. <button type="button" onClick={() => setRemoveId(null)} className="font-bold underline">Cancel removal</button></p>}
          </section>
          <form className={panel} onSubmit={(event) => void submitConnection(event)}>
            <h2 className="text-xl font-black">{editing ? 'Update connection' : 'Add a league'}</h2>
            <div className="mt-5 grid gap-4 sm:grid-cols-3">
              <label className="block text-sm font-bold">League ID<input className={field} type="number" min={1} required value={leagueId} disabled={!!editing} onChange={(event) => setLeagueId(event.target.value)} /></label>
              <label className="block text-sm font-bold">Season<input className={field} type="number" min={2020} max={currentSeason} required value={season} disabled={!!editing} onChange={(event) => setSeason(Number(event.target.value))} /></label>
              <label className="block text-sm font-bold">League access<select className={field} value={mode} onChange={(event) => setMode(event.target.value as 'private' | 'public')}><option value="private">Private</option><option value="public">Public</option></select></label>
            </div>
            {mode === 'private' && <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-bold">ESPN SWID<input className={field} type="password" required autoComplete="off" maxLength={200} value={swid} onChange={(event) => setSwid(event.target.value)} /></label>
              <label className="block text-sm font-bold">ESPN espn_s2<input className={field} type="password" required autoComplete="off" maxLength={8192} value={s2} onChange={(event) => setS2(event.target.value)} /></label>
              <p className="text-xs leading-5 text-slate-500 sm:col-span-2">Use the cookies from your signed-in ESPN session, not your ESPN password. Saved cookie values are never returned to the browser. Re-enter both when renewing a connection.</p>
            </div>}
            <div className="mt-5 flex flex-wrap gap-3"><button className={button} disabled={busy} type="submit">{busy ? 'Checking ESPN...' : 'Validate and save'} </button>{editing && <button type="button" className={secondary} onClick={clearForm}>Cancel update</button>}</div>
          </form>
          <section className={panel}><h2 className="font-black">Account settings</h2><div className="mt-4 flex flex-wrap items-end gap-4">
            <label className="text-sm font-bold">Theme<select className={field} value={preferences?.theme ?? 'system'} onChange={(event) => persistPreferences({ theme: event.target.value as OwnerPreferences['theme'] })}><option value="system">Follow device</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
            <button type="button" className={secondary} disabled={busy} onClick={() => void importLeague()}>Import server-configured league</button>
            <button type="button" className={secondary} disabled={busy} onClick={() => void logout(true)}>Sign out all devices</button>
          </div><p className="mt-3 text-xs leading-5 text-slate-500">Opening a league remembers it for your next visit. Team and tab changes are saved automatically. Each new visit opens at the league's current week.</p></section>
        </>}
    </main>
  </div>
}
