import { useCallback, useEffect, useState } from 'react'
import { api, type Role, type SourceHealth } from './api'
import { ago, aboveFloor, isAgency, salaryShort, trackBg, trackCode, trackText } from './format'
import ProfilePage from './Profile'
import RoleSheet from './RoleSheet'

const FILTERS: { key: string; label: string; code: string }[] = [
  { key: '', label: 'Worth a look', code: '01' },
  { key: 'shortlisted', label: 'Shortlisted', code: '02' },
  { key: 'applied', label: 'Applied', code: '03' },
  { key: 'progressing', label: 'Progressing', code: '04' },
  { key: 'filtered', label: 'Filtered out', code: '05' },
]

export default function App() {
  const [filter, setFilter] = useState('')
  const [view, setView] = useState<'roles' | 'profile'>('roles')
  const [directOnly, setDirectOnly] = useState(false)
  const [trackFilter, setTrackFilter] = useState<'all' | 'engineer' | 'management'>('all')
  const [roles, setRoles] = useState<Role[]>([])
  const [sources, setSources] = useState<SourceHealth[]>([])
  const [threshold, setThreshold] = useState(75)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      const [r, s, p] = await Promise.all([api.roles(filter || undefined), api.sources(), api.profile()])
      setRoles(r); setSources(s); setThreshold(p.threshold); setErr(null)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [filter])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get('role'))
    if (id) {
      // The deep-linked role may not be in the current tab; fetch it directly
      api.role(id).then((d) => { setRoles((rs) => rs.some((r) => r.id === id) ? rs : [d, ...rs]); setOpenId(id) }).catch(() => undefined)
    }
  }, [])

  async function act(id: number, state: string, reason?: string, note?: string) {
    setOpenId(null)
    setRoles((rs) => rs.filter((r) => r.id !== id))
    try { await api.setStatus(id, state, reason, note) } catch (e) { setErr(String(e)); void load() }
  }

  async function crawl() {
    setBusy(true)
    try { await api.crawl(); await load() } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const shown = roles.filter((r) => (!directOnly || !isAgency(r)) && (trackFilter === 'all' || r.track === trackFilter))
  const openRole = openId != null ? roles.find((r) => r.id === openId) ?? null : null

  return (
    <main className="mx-auto max-w-3xl px-3 pb-16 pt-3 sm:px-4">
      {/* frame top */}
      <header className="mb-3 flex items-end justify-between border-b border-line-hi pb-2">
        <div>
          <h1 className="whitespace-nowrap text-lg leading-none text-amber sm:text-xl">Career Station</h1>
          <div className="lcars-code mt-1">CS-{new Date().toISOString().slice(2, 10).replace(/-/g, '')} · {roles.length} in view</div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <button onClick={() => setView(view === 'roles' ? 'profile' : 'roles')} className="lcars-btn lcars-btn-quiet">{view === 'roles' ? 'Profile' : 'Roles'}</button>
          {view === 'roles' && <button onClick={crawl} disabled={busy} className="lcars-btn">{busy ? 'Searching' : 'Search'}</button>}
        </div>
      </header>

      {view === 'profile' && <ProfilePage onDone={() => { setView('roles'); void load() }} />}

      {view === 'roles' && (
        <>
          <nav className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`lcars-pill shrink-0 px-3 py-1.5 text-xs uppercase tracking-[0.14em] ${filter === f.key ? 'border-lavender bg-blue-faint text-lavender' : 'text-dim'}`}
              >
                <span className="lcars-code mr-1.5 text-faint">{f.code}</span>{f.label}
              </button>
            ))}
          </nav>

          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <label className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-dim">
              <input type="checkbox" checked={directOnly} onChange={(e) => setDirectOnly(e.target.checked)} className="accent-lavender" />
              Direct employers only
            </label>
            <div className="flex gap-1">
              {(['all', 'engineer', 'management'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTrackFilter(t)}
                  className={`lcars-pill px-2 py-1 text-[11px] uppercase tracking-[0.14em] ${
                    trackFilter === t ? (t === 'all' ? 'border-lavender text-lavender' : `${trackText(t)} border-current`) : 'text-dim'
                  }`}
                >
                  {t === 'all' ? 'All' : trackCode(t)}
                </button>
              ))}
            </div>
          </div>

          {err && <p className="mb-3 border border-alert px-3 py-2 text-xs text-alert">{err}</p>}

          <div className="lcars-panel">
            {shown.length === 0 && <p className="px-4 py-6 text-sm text-dim">Nothing here yet.</p>}
            <ul className="divide-y divide-line">
              {shown.map((r) => {
                const above = r.score != null && r.score >= threshold
                return (
                  <li key={r.id}>
                    <button onClick={() => setOpenId(r.id)} className="relative flex w-full items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-panel-2 sm:px-4">
                      <span className={`absolute inset-y-0 left-0 w-[2px] ${trackBg(r.track)}`} />
                      <div className="w-11 shrink-0 text-right">
                        <span className={`lcars-readout text-2xl leading-none ${r.score == null ? 'text-faint' : above ? 'text-amber' : 'text-dim'}`}>{r.score ?? '--'}</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-2">
                          <span className="truncate text-[15px] text-glow">{r.title}</span>
                          {r.watch === 1 && <span className="lcars-code shrink-0 text-lavender">WATCH</span>}
                          {r.track && <span className={`lcars-code shrink-0 ${trackText(r.track)}`}>{trackCode(r.track)}</span>}
                          {(r.doc_cv === 'ready' || r.doc_cover === 'ready') && (
                            <span className="lcars-code shrink-0 text-lavender">{[r.doc_cv === 'ready' && 'CV', r.doc_cover === 'ready' && 'CN'].filter(Boolean).join('+')}</span>
                          )}
                          {(r.doc_cv === 'pending' || r.doc_cover === 'pending') && <span className="alive-dot shrink-0" />}
                          {r.desc_quality === 'partial' && <span className="lcars-code shrink-0 text-amber/70">PARTIAL</span>}
                          {r.brief_status === 'ready' && (r.red_flags ?? 0) > 0 && <span className="lcars-code shrink-0 text-alert">{r.ai_interview === 'yes' ? 'AI-INT' : `${r.red_flags} RED`}</span>}
                          {r.brief_status === 'ready' && (r.red_flags ?? 0) === 0 && <span className="lcars-code shrink-0 text-sage">BRIEF</span>}
                          {r.brief_status === 'pending' && <span className="alive-dot shrink-0" />}
                        </div>
                        <div className="truncate text-xs text-dim">
                          {isAgency(r) && <span className="lcars-code mr-1.5">AGY</span>}
                          {r.company ?? 'Unknown company'}{r.location ? `, ${r.location}` : ''}
                          {r.filtered === 1 && r.filter_reason ? <span className="text-alert"> · hidden: {r.filter_reason}</span> : null}
                        </div>
                      </div>
                      <div className="w-[76px] shrink-0 text-right sm:w-auto">
                        <div className={`lcars-readout truncate text-xs ${aboveFloor(r) ? 'text-sage' : 'text-dim'}`}>{salaryShort(r)}</div>
                        <div className="lcars-code mt-0.5">{r.source} {ago(r.first_seen)}</div>
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        </>
      )}

      {openRole && <RoleSheet role={openRole} threshold={threshold} onClose={() => setOpenId(null)} onStatus={act} />}

      <footer className="fixed inset-x-0 bottom-0 border-t border-line bg-space/95 px-3 py-1.5 backdrop-blur sm:px-4">
        <div className="mx-auto flex max-w-3xl gap-4 overflow-x-auto">
          {sources.filter((s) => s.kind !== 'manual').map((s) => (
            <span key={s.id} className="lcars-code shrink-0" title={s.last_error ?? ''}>
              <span className={`mr-1.5 inline-block size-1.5 rounded-full align-middle ${s.last_ok === 1 ? 'bg-sage' : s.last_ok === 0 ? 'bg-alert' : 'bg-faint'}`} />
              {s.name} {s.last_ok == null ? 'not set up' : `${s.last_run ? ago(s.last_run) : ''}${s.last_error ? `: ${s.last_error}` : ''}`}
            </span>
          ))}
        </div>
      </footer>
    </main>
  )
}
