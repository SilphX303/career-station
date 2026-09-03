import { useCallback, useEffect, useState } from 'react'
import { api, type Role, type SourceHealth } from './api'
import ProfilePage from './Profile'

const FILTERS: { key: string; label: string }[] = [
  { key: '', label: 'Worth a look' },
  { key: 'shortlisted', label: 'Shortlisted' },
  { key: 'applied', label: 'Applied' },
  { key: 'progressing', label: 'Progressing' },
  { key: 'filtered', label: 'Filtered out' },
]

const FLOOR = 74000

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

      {err && <p className="mb-4 rounded border border-rust px-3 py-2 text-sm text-rust">{err}</p>}

      <p className="mb-2 text-sm text-muted">
        {roles.length === 0 ? 'Nothing here yet.' : `${roles.length} role${roles.length === 1 ? '' : 's'}`}
      </p>

      <ul className="divide-y divide-line border-y border-line">
        {roles.map((r) => (
          <li key={r.id} className="flex gap-4 py-4">
            <div className="w-12 shrink-0 text-right">
              <span className={`tnum text-3xl font-semibold leading-none ${r.score == null ? 'text-line' : r.score >= 75 ? 'text-amber' : 'text-muted'}`}>
                {r.score ?? '–'}
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <a href={r.url} target="_blank" rel="noreferrer" className="block font-medium leading-snug hover:underline">
                {r.title}
                {r.track && (
                  <span className="ml-2 align-middle rounded border border-line px-1.5 py-px text-xs font-normal text-muted">
                    {r.track === 'management' ? 'Mgmt' : r.track === 'engineer' ? 'Eng' : r.track}
                  </span>
                )}
              </a>
              <p className="text-sm text-muted">
                {r.company ?? 'Unknown company'}
                {r.location ? `, ${r.location}` : ''}
                {r.remote_flag && !/remote/i.test(r.location ?? '') ? ' (remote)' : ''}
              </p>
              <p className={`text-sm ${aboveFloor(r) ? 'text-sage' : 'text-muted'}`}>{salary(r)}</p>
              {r.filtered === 1 && r.filter_reason && (
                <p className="mt-1 text-sm text-rust/80">Hidden: {r.filter_reason}</p>
              )}
              {r.reasons.length > 0 && (
                <p className="mt-1 text-sm text-paper/80">{r.reasons.slice(0, 2).join('. ')}</p>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                {r.filtered !== 1 && r.state !== 'shortlisted' && (
                  <button onClick={() => act(r.id, 'shortlisted')} className="text-amber hover:underline">Shortlist</button>
                )}
                {r.filtered !== 1 && r.state !== 'applied' && (
                  <button onClick={() => act(r.id, 'applied')} className="text-paper hover:underline">Applied</button>
                )}
                {r.filtered !== 1 && <button onClick={() => act(r.id, 'dismissed')} className="text-muted hover:underline">Not for me</button>}
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
          {sources.map((s) => (
            <span key={s.id} className="shrink-0" title={s.last_error ?? ''}>
              <span className={`mr-1 inline-block size-2 rounded-full ${s.last_ok === 1 ? 'bg-sage' : s.last_ok === 0 ? 'bg-rust' : 'bg-line'}`} />
              {s.name}{s.last_run ? ` ${ago(s.last_run)}` : ''}{s.last_error ? `: ${s.last_error}` : ''}
            </span>
          ))}
        </div>
      </footer>
    </main>
  )
}
