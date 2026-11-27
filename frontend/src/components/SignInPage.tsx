import type { FormEvent } from 'react'
import type { OwnerSession } from '../lib/account'
import { PublicFooter, PublicHeader, SiteLink } from './PublicSite'

type Props = {
  session: OwnerSession | null
  error: string | null
  busy: boolean
  username: string
  password: string
  remember: boolean
  onUsername: (value: string) => void
  onPassword: (value: string) => void
  onRemember: (value: boolean) => void
  onSubmit: (event: FormEvent) => void
  onRetry: () => void
}

const field = 'mt-2 w-full rounded-xl border border-white/15 bg-[#0c1522] px-4 py-3.5 text-sm text-white outline-none transition focus:border-lime-300/60 focus:ring-4 focus:ring-lime-300/5'

export function SignInPage({ session, error, busy, username, password, remember,
  onUsername, onPassword, onRemember, onSubmit, onRetry }: Props) {
  const origin = session?.login_origin ?? session?.public_url
  const wrongOrigin = origin && new URL(origin).origin !== window.location.origin
  return <div className="public-site min-h-screen bg-[#080e18] text-white"><PublicHeader authenticated={session?.authenticated} />
    <main className="relative mx-auto grid min-h-[75vh] max-w-6xl items-center gap-12 px-5 py-14 sm:px-8 lg:grid-cols-2 lg:gap-20 lg:py-24">
      <div><SiteLink href="/" className="text-xs font-bold text-slate-400 hover:text-lime-300">← Back to the public site</SiteLink><p className="mt-10 text-[10px] font-black uppercase tracking-[0.2em] text-lime-300">Welcome back</p><h1 className="mt-5 text-4xl font-black leading-tight tracking-tight text-white sm:text-5xl">Your league.<br />Your next decision.</h1><p className="mt-6 max-w-md text-sm leading-7 text-slate-400">Sign in to open your saved leagues, compare your options, and follow the week as it unfolds.</p><div className="mt-8 flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-lime-300"><path d="M6 10h12v10H6zM8 10V7a4 4 0 0 1 8 0v3m-4 4v3" /></svg><p className="text-xs leading-6 text-slate-400">Saved private leagues stay in your account. The public preview never displays your roster or ESPN credentials.</p></div></div>
      <section className="rounded-2xl border border-white/15 bg-[#101b2b] p-6 shadow-2xl shadow-black/20 sm:p-8" aria-labelledby="sign-in-title">
        <div className="flex items-center justify-between gap-4"><h2 id="sign-in-title" className="text-2xl font-black text-white">Sign in</h2><img src="/logo.svg" alt="" className="size-9" /></div><p className="mt-2 text-sm text-slate-400">Continue to your dashboard.</p>
        {error && <div role="alert" className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/5 p-4 text-sm leading-6 text-rose-200">{error}{!session && <button type="button" onClick={onRetry} className="ml-2 font-bold underline">Try again</button>}</div>}
        {!session ? <p role="status" className="py-10 text-sm text-slate-400">{error ? 'You can still browse the public preview while sign-in is unavailable.' : 'Checking your session...'}</p>
          : wrongOrigin ? <p className="mt-6 text-sm leading-7 text-slate-300">Use a configured address to sign in: <a href={`${origin}/login`} className="font-bold text-lime-300 underline">{origin}</a></p>
          : session.configured === false ? <div className="mt-6 space-y-4 text-sm leading-7 text-slate-400"><p>This installation is waiting for its owner account. Finish the one-time account setup in the server terminal, then check again.</p><button type="button" onClick={onRetry} className="rounded-lg border border-white/15 px-4 py-2 text-xs font-bold text-white">Check again</button></div>
          : session.authenticated ? <p role="status" className="py-10 text-sm text-slate-400">Opening your dashboard...</p>
          : <form onSubmit={onSubmit} className="mt-7 space-y-5">
            <label className="block text-xs font-bold text-slate-300">Username<input className={field} required autoComplete="username" maxLength={100} value={username} onChange={(event) => onUsername(event.target.value)} /></label>
            <label className="block text-xs font-bold text-slate-300">Password<input className={field} type="password" required autoComplete="current-password" maxLength={256} value={password} onChange={(event) => onPassword(event.target.value)} /></label>
            <label className="flex items-center gap-2.5 text-xs text-slate-400"><input type="checkbox" checked={remember} onChange={(event) => onRemember(event.target.checked)} className="size-4 accent-lime-300" />Remember me on this device</label>
            <button type="submit" disabled={busy || !session.csrf_token} className="w-full rounded-xl bg-lime-300 px-5 py-3.5 text-sm font-black text-[#101720] transition hover:bg-lime-200 disabled:opacity-50">{busy ? 'Signing in...' : 'Sign in'}</button>
            <p className="text-[11px] leading-6 text-slate-500">Account recovery is available through the installation's administrator.</p>
          </form>}
        <p className="mt-7 border-t border-white/10 pt-5 text-xs text-slate-500">New here? Signups are currently closed. <SiteLink href="/#preview" className="font-bold text-slate-300 hover:text-lime-300">Explore the preview</SiteLink></p>
      </section>
    </main>
    <PublicFooter />
  </div>
}
