import { useCallback, useEffect, useState } from 'react'
import { api, type Doc, type Role, type RoleDetail, type SourceHealth } from './api'
import ProfilePage from './Profile'

const FILTERS: { key: string; label: string }[] = [
  { key: '', label: 'Worth a look' },
  { key: 'shortlisted', label: 'Shortlisted' },
  { key: 'applied', label: 'Applied' },
  { key: 'progressing', label: 'Progressing' },
  { key: 'filtered', label: 'Filtered out' },
]

const FLOOR = 74000
const AGENCY = /recruit|resourc|placement|staffing|talent|search|people|consultancy|personnel|appointments|selection|associates|partners/i

function isAgency(r: Role) {
  return !!r.company && AGENCY.test(r.company)
}

function joinReasons(rs: string[]) {
  return rs.slice(0, 2).map((x) => x.trim().replace(/\.$/, '')).join('. ') + '.'
}

function money(n: number) {
  return `£${Math.round(n / 1000)}k`
}

function salary(r: Role) {
  if (r.salary_min && r.salary_max && r.salary_min !== r.salary_max) return `${money(r.salary_min)} to ${money(r.salary_max)}`
  if (r.salary_max) return money(r.salary_max)
  if (r.salary_min) return money(r.salary_min)
  return r.salary_text ?? 'Salary not stated'
}

function aboveFloor(r: Role) {
  return (r.salary_max ?? r.salary_min ?? 0) >= FLOOR
}

function ago(iso: string) {
  const h = Math.max(0, (Date.now() - new Date(iso).getTime()) / 36e5)
  if (h < 1) return 'just now'
  if (h < 24) return `${Math.floor(h)}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function App() {
  const [filter, setFilter] = useState('')
  const [view, setView] = useState<'roles' | 'profile'>('roles')
  const [directOnly, setDirectOnly] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const [detail, setDetail] = useState<RoleDetail | null>(null)
  const [docs, setDocs] = useState<Doc[]>([])
  const [showDoc, setShowDoc] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)

  async function loadDocs(id: number) {
    try { setDocs(await api.docs(id)) } catch { setDocs([]) }
  }

  async function draft(id: number, kind: 'cv' | 'cover') {
    try { await api.requestDoc(id, kind); await loadDocs(id) } catch (e) { setErr(String(e)) }
  }

  async function copyDoc(text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1200) } catch { setErr('Copy failed') }
  }

  async function toggle(id: number) {
    if (open === id) { setOpen(null); setDetail(null); return }
    setOpen(id); setDetail(null); setDocs([]); setShowDoc(null)
    try { setDetail(await api.role(id)) } catch (e) { setErr(String(e)) }
    void loadDocs(id)
  }
  const [roles, setRoles] = useState<Role[]>([])
  const [sources, setSources] = useState<SourceHealth[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([api.roles(filter || undefined), api.sources()])
      setRoles(r)
      setSources(s)
      setErr(null)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [filter])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (open == null || !docs.some((d) => d.status === 'pending')) return
    const t = setInterval(() => void loadDocs(open), 20000)
    return () => clearInterval(t)
  }, [open, docs])

  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get('role'))
    if (id) void toggle(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function act(id: number, state: string) {
    setRoles((rs) => rs.filter((r) => r.id !== id))
    try { await api.setStatus(id, state) } catch (e) { setErr(String(e)); void load() }
  }

  async function crawl() {
    setBusy(true)
    try { await api.crawl(); await load() } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  return (
    <main className="mx-auto max-w-2xl px-4 pb-24 pt-6">
      <header className="mb-5 flex items-baseline justify-between">
        <h1 className="text-lg font-semibold tracking-tight">career-station</h1>
        <div className="flex gap-2">
          <button onClick={() => setView(view === 'roles' ? 'profile' : 'roles')} className="rounded-full border border-line px-3 py-1 text-sm text-muted hover:text-paper">
            {view === 'roles' ? 'Profile' : 'Roles'}
          </button>
          {view === 'roles' && (
            <button onClick={crawl} disabled={busy} className="rounded-full border border-line px-3 py-1 text-sm text-muted hover:text-paper disabled:opacity-50">
              {busy ? 'Searching' : 'Search now'}
            </button>
          )}
        </div>
      </header>

      {view === 'profile' && <ProfilePage onDone={() => { setView('roles'); void load() }} />}
      {view === 'roles' && <>

      <nav className="mb-4 flex gap-2 overflow-x-auto">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`shrink-0 rounded-full px-3 py-1 text-sm ${
              filter === f.key ? 'bg-paper text-ink' : 'border border-line text-muted'
            }`}
          >
            {f.label}
          </button>
        ))}
      </nav>

      <label className="mb-3 flex items-center gap-2 text-sm text-muted">
        <input type="checkbox" checked={directOnly} onChange={(e) => setDirectOnly(e.target.checked)} className="accent-amber" />
        Direct employers only
      </label>

      {err && <p className="mb-4 rounded border border-rust px-3 py-2 text-sm text-rust">{err}</p>}

      <p className="mb-2 text-sm text-muted">
        {roles.length === 0 ? 'Nothing here yet.' : `${roles.length} role${roles.length === 1 ? '' : 's'}`}
      </p>

      <ul className="divide-y divide-line border-y border-line">
        {roles.filter((r) => !directOnly || !isAgency(r)).map((r) => (
          <li key={r.id} className="flex gap-4 py-4">
            <div className="w-12 shrink-0 text-right">
              <span className={`tnum text-3xl font-semibold leading-none ${r.score == null ? 'text-line' : r.score >= 75 ? 'text-amber' : 'text-muted'}`}>
                {r.score ?? '–'}
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <button onClick={() => toggle(r.id)} className="block w-full text-left font-medium leading-snug">
                {r.title}
                {r.track && (
                  <span className="ml-2 align-middle rounded border border-line px-1.5 py-px text-xs font-normal text-muted">
                    {r.track === 'management' ? 'Mgmt' : r.track === 'engineer' ? 'Eng' : r.track}
                  </span>
                )}
              </button>
              <p className="text-sm text-muted">
                {isAgency(r) && <span className="mr-1.5 rounded bg-line px-1 py-px text-xs">Agency</span>}
                {r.company ?? 'Unknown company'}
                {r.location ? `, ${r.location}` : ''}
                {r.remote_flag && !/remote/i.test(r.location ?? '') ? ' (remote)' : ''}
              </p>
              <p className={`text-sm ${aboveFloor(r) ? 'text-sage' : 'text-muted'}`}>{salary(r)}</p>
              {r.filtered === 1 && r.filter_reason && (
                <p className="mt-1 text-sm text-rust/80">Hidden: {r.filter_reason}</p>
              )}
              {r.reasons.length > 0 && (
                <p className="mt-1 text-sm text-paper/80">{joinReasons(r.reasons)}</p>
              )}
              {open === r.id && (
                <div className="mt-3 space-y-3 border-l-2 border-line pl-3 text-sm">
                  {!detail && <p className="text-muted">Loading</p>}
                  {detail && detail.gaps.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs uppercase tracking-wide text-muted">Gaps to address</p>
                      <ul className="list-disc space-y-0.5 pl-4 text-paper/80">{detail.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul>
                    </div>
                  )}
                  {detail && detail.note && <p className="text-muted">{detail.note}</p>}
                  {detail && (
                    <div>
                      <p className="mb-1 text-xs uppercase tracking-wide text-muted">Documents</p>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        {(['cv', 'cover'] as const).map((k) => {
                          const d = docs.find((x) => x.kind === k)
                          const label = k === 'cv' ? 'CV' : 'Cover note'
                          if (!d) return <button key={k} onClick={() => draft(r.id, k)} className="text-amber hover:underline">Draft {label}</button>
                          if (d.status === 'pending') return <span key={k} className="text-muted">{label}: drafting, usually under 10 min</span>
                          if (d.status === 'failed') return <button key={k} onClick={() => draft(r.id, k)} className="text-rust hover:underline">{label} failed, retry</button>
                          return (
                            <span key={k} className="flex gap-2">
                              <button onClick={() => setShowDoc(showDoc === d.id ? null : d.id)} className="text-sage hover:underline">{showDoc === d.id ? `Hide ${label}` : `View ${label}`}</button>
                              <a href={`/api/documents/${d.id}.pdf`} className="text-paper hover:underline">PDF</a>
                              <button onClick={() => draft(r.id, k)} className="text-muted hover:underline">redo</button>
                            </span>
                          )
                        })}
                      </div>
                      {showDoc != null && docs.find((d) => d.id === showDoc)?.content && (
                        <div className="mt-2 rounded border border-line bg-surface p-3">
                          <div className="mb-2 flex justify-end">
                            <button onClick={() => copyDoc(docs.find((d) => d.id === showDoc)!.content!)} className="text-xs text-amber hover:underline">{copied ? 'Copied' : 'Copy markdown'}</button>
                          </div>
                          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-paper/90">{docs.find((d) => d.id === showDoc)!.content}</pre>
                        </div>
                      )}
                    </div>
                  )}
                  {detail && (
                    <div>
                      <p className="mb-1 text-xs uppercase tracking-wide text-muted">The ad</p>
                      <p className="whitespace-pre-line leading-relaxed text-paper/80">{detail.description || (r.url ? 'No description captured for this one; open the ad.' : 'Added from the inbox sweep; no ad on file.')}</p>
                    </div>
                  )}
                </div>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                {r.filtered !== 1 && r.state !== 'shortlisted' && (
                  <button onClick={() => act(r.id, 'shortlisted')} className="text-amber hover:underline">Shortlist</button>
                )}
                {r.filtered !== 1 && r.state !== 'applied' && (
                  <button onClick={() => act(r.id, 'applied')} className="text-paper hover:underline">Applied</button>
                )}
                {r.filtered !== 1 && <button onClick={() => act(r.id, 'dismissed')} className="text-muted hover:underline">Not for me</button>}
                {r.url && <a href={r.url} target="_blank" rel="noreferrer" className="text-muted hover:underline">Open ad</a>}
                <span className="ml-auto text-xs text-muted">{r.source}, {ago(r.first_seen)}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>

      </>}

      <footer className="fixed inset-x-0 bottom-0 border-t border-line bg-ink/95 px-4 py-2 text-xs text-muted backdrop-blur">
        <div className="mx-auto flex max-w-2xl gap-4 overflow-x-auto">
          {sources.length === 0 && <span>No sources have run yet.</span>}
          {sources.filter((s) => s.kind !== 'manual').map((s) => (
            <span key={s.id} className="shrink-0" title={s.last_error ?? ''}>
              <span className={`mr-1 inline-block size-2 rounded-full ${s.last_ok === 1 ? 'bg-sage' : s.last_ok === 0 ? 'bg-rust' : 'bg-line'}`} />
              {s.name} {s.last_ok == null ? 'not set up' : `${s.last_run ? ago(s.last_run) : ''}${s.last_error ? `: ${s.last_error}` : ''}`}
            </span>
          ))}
        </div>
      </footer>
    </main>
  )
}
