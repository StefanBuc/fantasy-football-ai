import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { navigate } from '../lib/navigation'
import { getPublicPerformance, type PublicPerformance } from '../lib/publicPerformance'

export function SiteLink({ href, children, className = '', ...rest }: {
  href: string; children: ReactNode; className?: string; 'aria-label'?: string
}) {
  function follow(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(href)
  }
  return <a href={href} onClick={follow} className={className} {...rest}>{children}</a>
}

export function PublicHeader({ authenticated = false }: { authenticated?: boolean }) {
  const [menu, setMenu] = useState(false)
  return <header className="relative z-20 border-b border-white/10 bg-[#080e18] text-white">
    <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-5 sm:px-8">
      <SiteLink href="/" className="flex shrink-0 items-center gap-2 sm:gap-3" aria-label="Fantasy Football AI home">
        <img src="/logo.svg" alt="" className="size-8 sm:size-10" />
        <span><span className="block text-xs font-extrabold tracking-tight sm:text-base">Fantasy Football AI</span><span className="mt-0.5 hidden text-[10px] font-bold uppercase tracking-[0.19em] text-slate-400 sm:block">A clearer view of game day</span></span>
      </SiteLink>
      <nav aria-label="Public navigation" className="hidden items-center gap-7 text-xs font-bold text-slate-300 lg:flex">
        <SiteLink href="/#features" className="transition hover:text-lime-300">Features</SiteLink>
        <SiteLink href="/#how-it-works" className="transition hover:text-lime-300">How it works</SiteLink>
        <SiteLink href="/#performance" className="transition hover:text-lime-300">Model performance</SiteLink>
        <SiteLink href="/#about" className="transition hover:text-lime-300">About</SiteLink>
      </nav>
      <div className="flex items-center gap-2 sm:gap-3">
        <SiteLink href={authenticated ? '/app' : '/login'} className="rounded-lg bg-lime-300 px-3 py-2.5 text-xs font-black text-[#101720] transition hover:bg-lime-200 sm:px-4">{authenticated ? 'Open dashboard' : 'Sign in'}</SiteLink>
        <button type="button" disabled title="Signups are currently closed" aria-describedby="signup-status" className="hidden rounded-lg border border-white/15 px-4 py-2.5 text-xs font-bold text-slate-500 sm:block">Sign up</button>
        <span id="signup-status" className="sr-only">Signups are currently closed.</span>
        <button type="button" aria-label="Toggle navigation" aria-expanded={menu} aria-controls="public-mobile-nav" onClick={() => setMenu(!menu)} className="rounded-lg border border-white/15 p-2 text-slate-300 lg:hidden">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true" className="size-5"><path d={menu ? 'm6 6 12 12M18 6 6 18' : 'M4 6h16M4 12h16M4 18h16'} /></svg>
        </button>
      </div>
    </div>
    {menu && <nav id="public-mobile-nav" aria-label="Mobile public navigation" className="grid gap-4 border-t border-white/10 px-6 py-5 text-sm text-slate-300 lg:hidden">
      {['features', 'how-it-works', 'performance', 'about'].map((id) => <a key={id} href={`/#${id}`} onClick={(event) => { event.preventDefault(); setMenu(false); navigate(`/#${id}`) }}>{id === 'features' ? 'Features' : id === 'how-it-works' ? 'How it works' : id === 'about' ? 'About' : 'Model performance'}</a>)}
      <button type="button" disabled className="text-left text-xs text-slate-500">Sign up · currently closed</button>
    </nav>}
  </header>
}

export function PublicFooter() {
  return <footer className="border-t border-white/10 bg-[#080e18] text-slate-400">
    <div className="mx-auto flex max-w-7xl flex-col justify-between gap-5 px-5 py-8 text-xs leading-6 sm:flex-row sm:px-8">
      <div><p className="font-bold text-slate-200">Fantasy Football AI</p><p>Independent fantasy analysis. Not affiliated with ESPN or the NFL.</p></div>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2"><SiteLink href="/#how-it-works" className="hover:text-white">How it works</SiteLink><SiteLink href="/login" className="hover:text-white">Sign in</SiteLink><span className="rounded-full border border-white/10 px-3 py-1 text-[10px] font-bold uppercase tracking-wider">Signups currently closed</span></div>
    </div>
  </footer>
}

function Arrow() {
  return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true" className="size-4"><path d="M4 10h12m-5-5 5 5-5 5" /></svg>
}

const samplePlayers = [
  { name: 'Evan Brooks', position: 'QB', points: 20.4, floor: 12.1, ceiling: 29.7 },
  { name: 'Jordan Ellis', position: 'RB', points: 14.8, floor: 7.2, ceiling: 24.1 },
  { name: 'Miles Carter', position: 'WR', points: 14.2, floor: 5.4, ceiling: 25.9 },
]

function HeroPreview() {
  return <div className="relative mx-auto w-full max-w-lg lg:ml-auto">
    <div aria-hidden="true" className="absolute -inset-10 rounded-full bg-lime-300/[0.06] blur-3xl" />
    <div className="relative overflow-hidden rounded-2xl border border-white/15 bg-[#101b2b] shadow-[0_24px_90px_rgba(0,0,0,0.45)]">
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-4"><span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Your lineup, in focus</span><span className="rounded-full border border-lime-300/20 bg-lime-300/10 px-2.5 py-1 text-[9px] font-bold tracking-wider text-lime-300">SAMPLE DATA</span></div>
      <div className="flex items-end justify-between gap-4 px-5 py-6"><div><p className="text-xs text-slate-400">Example lineup snapshot</p><h2 className="mt-1 text-xl font-black text-white">Ready for the next call.</h2></div><div className="text-right"><p className="text-3xl font-black tabular-nums text-lime-300">49.4</p><p className="mt-1 text-[9px] font-bold uppercase tracking-wider text-slate-500">Projected points</p></div></div>
      {samplePlayers.map((player) => <div key={player.name} className="flex items-center gap-4 border-t border-white/[0.06] px-5 py-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.03] text-xs font-black text-slate-400">{player.position}</span>
        <div className="min-w-0 flex-1"><p className="text-sm font-extrabold text-white">{player.name}</p><p className="mt-1 text-[10px] text-slate-500">Illustrative player outlook</p></div>
        <div className="text-right"><p className="text-[9px] font-bold text-slate-400">Ceiling {player.ceiling.toFixed(1)}</p><p className="my-0.5 text-xl font-black tabular-nums text-white">{player.points.toFixed(1)}</p><p className="text-[9px] font-bold text-slate-500">Floor {player.floor.toFixed(1)}</p></div>
      </div>)}
      <p className="border-t border-white/10 bg-black/10 px-5 py-3 text-[10px] leading-5 text-slate-500">Fictional players and illustrative numbers. No live league data.</p>
    </div>
    <div className="relative mx-5 -mt-1 flex items-center gap-3 rounded-b-xl border border-t-0 border-lime-300/20 bg-[#14231f] px-4 py-3"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-lime-300/10 text-lime-300">↗</span><p className="text-xs font-semibold text-slate-300">See the range behind each projection.</p></div>
  </div>
}

const features = [
  ['01', 'Weekly projections', 'Position-specific models bring recent form and the upcoming NFL matchup into your weekly view.', 'M4 17l5-5 4 3 7-10M4 5v14h16'],
  ['02', 'Matchup insight', 'Compare starting lineups, pregame win estimates, and ESPN live scores as games unfold.', 'M4 7h6M4 12h6M4 17h6m4-12 6 7-6 7'],
  ['03', 'Optimized lineups', 'See who to start or bench, with optional free-agent suggestions and clear projected point gains.', 'M4 7h12m-3-3 3 3-3 3M20 17H8m3-3-3 3 3 3'],
  ['04', 'Trade analysis', 'Compare weekly and remaining-season lineup value, positional needs, and roster depth on both sides.', 'M5 8h14m-4-4 4 4-4 4M19 16H5m4-4-4 4 4 4'],
  ['05', 'Floor and ceiling', 'Add context to the main prediction with an estimated scoring range before kickoff.', 'M5 5v14M19 5v14M5 12h14M9 8v8M15 8v8'],
  ['06', 'Accuracy tracking', 'Save forecasts before kickoff and compare them with published results after games are graded.', 'M5 4h14v16H5zM8 9l2 2 5-5M8 15h8'],
]

export function PerformanceTiles({ data, error, loading }: { data: PublicPerformance | null; error: string | null; loading: boolean }) {
  const updated = data?.last_result_update ? new Date(data.last_result_update) : null
  const updatedLabel = updated && Number.isFinite(updated.getTime()) ? updated.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'
  const tiles = [
    ['Average miss', data?.mae != null ? `${data.mae.toFixed(2)} pts` : '—', 'Average absolute error · lower is better'],
    ['Within 5 points', data?.within_five_pct != null ? `${data.within_five_pct.toFixed(1)}%` : '—', 'Share of graded forecasts within five points'],
    ['Forecasts graded', data ? data.compared.toLocaleString() : '—', 'Published results compared with saved forecasts'],
    ['Latest result update', updatedLabel, updated && Number.isFinite(updated.getTime()) ? updated.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : 'Shown once results have been collected'],
  ]
  return <div>
    <div className="grid gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-4">
      {tiles.map(([label, value, detail]) => <div key={label} className="bg-[#0d1726] p-6"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">{label}</p><p className="mt-4 text-3xl font-black tabular-nums tracking-tight text-white">{value}</p><p className="mt-3 text-[11px] leading-5 text-slate-500">{detail}</p></div>)}
    </div>
    {loading && !data && <p role="status" className="mt-4 text-xs text-slate-400">Loading saved model results...</p>}
    {error && <p role="status" className="mt-4 text-xs text-amber-300">Model performance is temporarily unavailable.{data ? ' Showing the last loaded results.' : ' The preview below is still available.'}</p>}
    {!error && data?.state === 'collecting' && <p className="mt-4 text-sm leading-6 text-slate-400">Collecting results. {data.saved ? `${data.saved.toLocaleString()} forecasts saved; graded results will appear after eligible games are published and synced.` : 'Performance figures will appear as pregame forecasts and published results are collected.'}</p>}
    {data?.state === 'ready' && <p className="mt-4 text-xs text-slate-400">{data.pending.toLocaleString()} saved forecasts awaiting results.{data.latest_week !== null ? ` Latest graded week: ${data.latest_week}.` : ''}</p>}
  </div>
}

function PerformanceSection() {
  const [data, setData] = useState<PublicPerformance | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    let pending = false
    async function update() {
      if (pending || document.hidden) return
      pending = true
      try {
        const next = await getPublicPerformance()
        if (!cancelled) { setData(next); setError(null) }
      } catch (caught) { if (!cancelled) setError(caught instanceof Error ? caught.message : 'Results unavailable.') }
      finally { pending = false; if (!cancelled) setLoading(false) }
    }
    void update()
    const timer = window.setInterval(() => { void update() }, 300_000)
    const visible = () => { if (!document.hidden) void update() }
    document.addEventListener('visibilitychange', visible)
    return () => { cancelled = true; window.clearInterval(timer); document.removeEventListener('visibilitychange', visible) }
  }, [])
  return <section id="performance" className="scroll-mt-8 border-y border-white/10 bg-[#0a1220]">
    <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8 sm:py-16">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><p className="text-[10px] font-black uppercase tracking-[0.2em] text-lime-300">Track the prediction. Learn from the result.</p><h2 className="mt-3 text-2xl font-black tracking-tight text-white sm:text-3xl">Performance, with the context included.</h2></div><span className="rounded-full border border-white/10 px-3 py-1.5 text-[10px] font-bold text-slate-400">{data ? `${data.season} season · NFL-wide tracking` : 'NFL-wide tracking'}</span></div>
      <PerformanceTiles data={data} error={error} loading={loading} />
      <p className="mt-5 max-w-4xl text-[11px] leading-6 text-slate-500">Figures use saved NFL-wide forecasts, including model and fallback estimates. Full-PPR offense and the app's K/DST scoring apply. Only forecasts with published results enter error calculations. Private league history stays in the signed-in dashboard.</p>
    </div>
  </section>
}

function InteractivePreview() {
  const [tab, setTab] = useState<'outlook' | 'lineup' | 'trade'>('outlook')
  const [selected, setSelected] = useState(0)
  const player = samplePlayers[selected]
  return <section id="preview" className="mx-auto max-w-7xl scroll-mt-8 px-5 py-16 sm:px-8 sm:py-24">
    <div className="grid items-start gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
      <div><p className="text-[10px] font-black uppercase tracking-[0.2em] text-lime-300">Take a look inside</p><h2 className="mt-4 text-3xl font-black leading-tight tracking-tight text-white sm:text-4xl">A little more clarity.<br />Every week.</h2><p className="mt-5 max-w-md text-sm leading-7 text-slate-400">Explore a few of the decisions the dashboard helps you make. Switch between a player outlook, a lineup recommendation, and a trade comparison.</p><p className="mt-5 rounded-xl border border-white/10 bg-white/[0.02] p-4 text-xs leading-6 text-slate-400"><span className="font-bold text-slate-200">Preview only.</span> These are fictional players and illustrative numbers. They are not current NFL projections or measured model performance.</p><SiteLink href="/login" className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-lime-300">Sign in to connect your league <Arrow /></SiteLink></div>
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#101b2b] shadow-2xl shadow-black/20">
        <div role="tablist" aria-label="Dashboard preview" className="flex border-b border-white/10 bg-black/10 px-2">
          {([['outlook', 'Player outlook'], ['lineup', 'Lineup decisions'], ['trade', 'Trade impact']] as const).map(([value, label]) => <button key={value} type="button" role="tab" id={`preview-tab-${value}`} aria-selected={tab === value} aria-controls={`preview-panel-${value}`} tabIndex={tab === value ? 0 : -1} onClick={() => setTab(value)} onKeyDown={(event) => {
            const keys = ['ArrowRight', 'ArrowLeft', 'Home', 'End']
            if (!keys.includes(event.key)) return
            event.preventDefault()
            const values = ['outlook', 'lineup', 'trade'] as const
            const index = values.indexOf(value)
            const next = event.key === 'Home' ? values[0] : event.key === 'End' ? values[2] : values[(index + (event.key === 'ArrowRight' ? 1 : 2)) % 3]
            setTab(next); document.getElementById(`preview-tab-${next}`)?.focus()
          }} className={`flex-1 border-b-2 px-2 py-4 text-xs font-bold transition sm:px-4 ${tab === value ? 'border-lime-300 text-lime-300' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>{label}</button>)}
        </div>
        <div role="tabpanel" id={`preview-panel-${tab}`} aria-labelledby={`preview-tab-${tab}`} className="p-5 sm:p-7">
          {tab === 'outlook' && <>
            <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-black text-white">The range behind the number</h3><span className="text-[9px] font-black tracking-wider text-slate-500">SAMPLE DATA</span></div>
            <div className="mt-5 flex flex-wrap gap-2">{samplePlayers.map((item, index) => <button type="button" key={item.name} onClick={() => setSelected(index)} aria-pressed={selected === index} className={`rounded-lg border px-3 py-2 text-xs font-bold ${selected === index ? 'border-lime-300/30 bg-lime-300/10 text-lime-300' : 'border-white/10 text-slate-400'}`}>{item.position} · {item.name}</button>)}</div>
            <div className="mt-6 flex flex-wrap items-center justify-between gap-5 rounded-xl border border-white/10 bg-[#0c1522] p-6"><div><p className="text-xs text-slate-500">Example pregame outlook</p><p className="mt-2 text-xl font-black text-white">{player.name}</p><p className="mt-2 text-xs text-slate-400">{player.position} · illustrative scoring range</p></div><div className="text-right"><p className="text-xs font-semibold text-slate-400">Ceiling {player.ceiling.toFixed(1)}</p><p className="my-2 text-5xl font-black tabular-nums text-lime-300">{player.points.toFixed(1)}</p><p className="text-xs font-semibold text-slate-400">Floor {player.floor.toFixed(1)}</p></div></div>
            <p className="mt-5 text-xs leading-6 text-slate-500">Before kickoff, the dashboard shows a projection and estimated range. During a game, ESPN fantasy points appear above the saved pregame forecast.</p>
          </>}
          {tab === 'lineup' && <>
            <h3 className="text-lg font-black text-white">Find a useful upgrade</h3><div className="mt-5 grid grid-cols-3 gap-2 rounded-xl border border-white/10 bg-[#0c1522] p-4 text-center"><div><p className="text-[10px] text-slate-500">Before</p><p className="mt-2 text-2xl font-black text-white">87.6</p></div><div><p className="text-[10px] text-slate-500">After</p><p className="mt-2 text-2xl font-black text-white">96.4</p></div><div><p className="text-[10px] text-slate-500">Projected gain</p><p className="mt-2 text-2xl font-black text-lime-300">+8.8</p></div></div>
            <div className="mt-5 space-y-3"><p className="rounded-lg border border-lime-300/20 bg-lime-300/5 p-4 text-sm text-slate-300"><span className="mr-2 font-black text-lime-300">Add + start</span> Theo Reed <span className="text-xs text-lime-300">(Free agent)</span><span className="mt-1 block text-xs text-slate-500">RB · 14.8 projected points · FLEX</span></p><p className="rounded-lg border border-white/10 p-4 text-sm text-slate-300"><span className="mr-2 font-black text-slate-400">Bench</span> Jordan Ellis<span className="mt-1 block text-xs text-slate-500">RB · 6.0 projected points in this example</span></p></div><p className="mt-5 text-xs leading-6 text-slate-500">The manager reviews any pickup, waiver claim, or required drop. Recommendations do not submit changes to ESPN.</p>
          </>}
          {tab === 'trade' && <>
            <h3 className="text-lg font-black text-white">A trade can help both sides</h3><p className="mt-2 text-xs leading-6 text-slate-400">Compare the effect on each roster's best starting lineup.</p><div className="mt-5 grid gap-3 sm:grid-cols-2">{[['Ridge Runners', '438.0', '454.4', '+16.4'], ['Sunday Club', '404.0', '414.4', '+10.4']].map(([name, before, after, change]) => <div key={name} className="rounded-xl border border-white/10 bg-[#0c1522] p-5"><h4 className="text-sm font-extrabold text-white">{name}</h4><p className="mt-4 text-[10px] text-slate-500">Example four-week starter total</p><p className="mt-2 text-lg font-black tabular-nums text-slate-200">{before} → {after}</p><p className="mt-3 text-2xl font-black text-lime-300">{change} <span className="text-xs text-slate-500">pts</span></p></div>)}</div><p className="mt-5 rounded-lg border border-white/10 p-4 text-xs leading-6 text-slate-400">Team needs and bench depth explain the difference. The signed-in analyzer also shows the weekly breakdown and projected power-rank changes.</p>
          </>}
        </div>
      </div>
    </div>
  </section>
}

export function PublicSite({ authenticated = false, page = '/' }: { authenticated?: boolean; page?: string }) {
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { if (window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView() })
    return () => window.cancelAnimationFrame(frame)
  }, [])
  if (page !== '/') return <div className="public-site min-h-screen bg-[#080e18] text-white"><PublicHeader authenticated={authenticated} /><main className="mx-auto flex min-h-[65vh] max-w-xl flex-col items-start justify-center px-6 py-20"><p className="text-xs font-black uppercase tracking-[0.2em] text-lime-300">{page === '/signup' ? 'Registration is closed' : 'Page not found'}</p><h1 className="mt-4 text-4xl font-black">{page === '/signup' ? 'Thanks for your interest.' : 'Let’s get you back on track.'}</h1><p className="mt-5 text-sm leading-7 text-slate-400">{page === '/signup' ? 'New accounts are not available right now. You can explore the public preview or sign in with an existing account.' : 'This address does not have a page. The public preview and product overview are available on the home page.'}</p><div className="mt-8 flex gap-4"><SiteLink href="/" className="rounded-lg bg-lime-300 px-5 py-3 text-sm font-black text-[#101720]">Back to home</SiteLink><SiteLink href="/login" className="rounded-lg border border-white/15 px-5 py-3 text-sm font-bold text-white">Sign in</SiteLink></div></main><PublicFooter /></div>
  return <div className="public-site min-h-screen overflow-x-clip bg-[#080e18] text-white"><PublicHeader authenticated={authenticated} />
    <main>
      <section className="relative overflow-hidden"><div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_75%_40%,rgba(190,242,100,0.07),transparent_50%)]" /><div className="relative mx-auto grid max-w-7xl items-center gap-14 px-5 py-16 sm:px-8 sm:py-24 lg:grid-cols-[1.1fr_0.9fr] lg:gap-16 lg:py-28">
        <div><div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-300"><span className="size-1.5 rounded-full bg-lime-300" />Weekly fantasy, with context</div><h1 className="mt-7 text-5xl font-black leading-[1.04] tracking-[-0.045em] text-white sm:text-6xl xl:text-7xl">Your next move.<br /><span className="text-lime-300">Backed by data.</span></h1><p className="mt-6 max-w-xl text-base leading-8 text-slate-400">Bring projections, matchups, lineup decisions, and trade analysis into one clear view of your fantasy week.</p><div className="mt-8 flex flex-wrap gap-3"><SiteLink href="/#preview" className="inline-flex items-center gap-3 rounded-xl bg-lime-300 px-6 py-3.5 text-sm font-black text-[#101720] transition hover:bg-lime-200">Explore the preview <Arrow /></SiteLink><SiteLink href={authenticated ? '/app' : '/login'} className="inline-flex items-center gap-3 rounded-xl border border-white/15 bg-white/[0.02] px-6 py-3.5 text-sm font-bold text-white transition hover:bg-white/[0.06]">{authenticated ? 'Open your dashboard' : 'Sign in to your league'}</SiteLink></div><p className="mt-4 text-[11px] text-slate-500">Explore freely. New account registration is currently closed.</p><div className="mt-9 flex flex-wrap gap-2">{['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'].map((position) => <span key={position} className="rounded-md border border-white/10 px-2.5 py-1 text-[10px] font-bold text-slate-500">{position}</span>)}</div></div>
        <HeroPreview />
      </div></section>
      <PerformanceSection />
      <section id="features" className="mx-auto max-w-7xl scroll-mt-8 px-5 py-16 sm:px-8 sm:py-24"><div className="flex flex-wrap items-end justify-between gap-5"><div><p className="text-[10px] font-black uppercase tracking-[0.2em] text-lime-300">Built around your weekly decisions</p><h2 className="mt-4 text-3xl font-black tracking-tight text-white sm:text-4xl">From a player outlook to the bigger picture.</h2></div><p className="max-w-sm text-sm leading-7 text-slate-400">A connected view of your league, with the detail behind each recommendation.</p></div><div className="mt-9 grid gap-4 md:grid-cols-2 lg:grid-cols-3">{features.map(([number, title, description, path]) => <article key={title} className="rounded-2xl border border-white/10 bg-[#0d1726] p-6"><div className="flex items-center justify-between"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="size-7 text-lime-300"><path d={path} /></svg><span className="text-[10px] font-bold text-slate-600">{number}</span></div><h3 className="mt-6 text-lg font-extrabold text-white">{title}</h3><p className="mt-3 text-sm leading-7 text-slate-400">{description}</p></article>)}</div></section>
      <InteractivePreview />
      <section id="how-it-works" className="scroll-mt-8 border-y border-white/10 bg-[#0a1220]"><div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 sm:py-20"><p className="text-[10px] font-black uppercase tracking-[0.2em] text-lime-300">How it works</p><h2 className="mt-4 text-3xl font-black tracking-tight text-white sm:text-4xl">Connect. Compare. Keep learning.</h2><div className="mt-10 grid gap-8 md:grid-cols-3">{[
        ['01', 'Connect your league', 'Sign in and save a public or private ESPN league. Your preferred team and dashboard settings follow your account.'],
        ['02', 'Explore the options', 'Compare player projections, estimated ranges, and the effect of lineup or trade decisions on your roster.'],
        ['03', 'Follow the results', 'Pregame predictions are saved before kickoff and compared with published stats as results become available.'],
      ].map(([number, title, description]) => <article key={number} className="border-t border-white/15 pt-5"><span className="text-xs font-black text-lime-300">{number}</span><h3 className="mt-4 text-lg font-extrabold text-white">{title}</h3><p className="mt-3 text-sm leading-7 text-slate-400">{description}</p></article>)}</div></div></section>
      <section id="about" className="mx-auto grid max-w-7xl scroll-mt-8 gap-10 px-5 py-16 sm:px-8 sm:py-24 lg:grid-cols-[0.8fr_1.2fr]"><div><p className="text-[10px] font-black uppercase tracking-[0.2em] text-lime-300">A few things worth knowing</p><h2 className="mt-4 text-3xl font-black tracking-tight text-white">Built to inform your decisions.</h2><p className="mt-5 text-sm leading-7 text-slate-400">Fantasy Football AI combines historical NFL data and position-specific models with league context. Projections are estimates, and football still has plenty of surprises.</p></div><div className="space-y-3">{[
        ['Can I create an account?', 'Signups are currently closed. Existing accounts can sign in; everyone can explore this public preview and the aggregate performance figures.'],
        ['What scoring rules do projections use?', 'AI projections and accuracy tracking use full-PPR offense and the app’s K/DST rules. Live ESPN points follow your league’s scoring, which can differ.'],
        ['How should I use floor and ceiling?', 'They are estimated scoring bounds, not guaranteed minimums or maximums. Use them as context alongside the main projection and player availability.'],
        ['Does the app make changes to my ESPN team?', 'Lineup and trade tools provide recommendations. You review and make any roster moves, drops, waiver claims, or trades in ESPN.'],
      ].map(([question, answer]) => <details key={question} className="rounded-xl border border-white/10 bg-[#0d1726] p-5"><summary className="cursor-pointer text-sm font-bold text-slate-200">{question}</summary><p className="mt-4 text-sm leading-7 text-slate-400">{answer}</p></details>)}</div></section>
      <section className="mx-auto max-w-7xl px-5 pb-16 sm:px-8"><div className="flex flex-wrap items-center justify-between gap-6 rounded-2xl border border-lime-300/15 bg-[#13221f] px-7 py-9"><div><h2 className="text-2xl font-black text-white">Your league is waiting.</h2><p className="mt-2 text-sm text-slate-400">Already have access? Pick up where you left off.</p></div><SiteLink href={authenticated ? '/app' : '/login'} className="inline-flex items-center gap-3 rounded-xl bg-lime-300 px-6 py-3.5 text-sm font-black text-[#101720]">{authenticated ? 'Open dashboard' : 'Sign in'} <Arrow /></SiteLink></div></section>
    </main>
    <PublicFooter />
  </div>
}
