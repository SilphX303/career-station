import { useEffect, useState } from 'react'
import { api, type Band, type Dismissals, type Market, type Profile } from './api'

const lines = (a: string[] | undefined) => (a ?? []).join('\n')
const split = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean)

export default function ProfilePage({ onDone }: { onDone: () => void }) {
  const [p, setP] = useState<Profile | null>(null)
  const [terms, setTerms] = useState('')
  const [locs, setLocs] = useState('')
  const [excl, setExcl] = useState('')
  const [floor, setFloor] = useState('')
  const [thr, setThr] = useState('')
  const [md, setMd] = useState('')
  const [cve, setCve] = useState('')
  const [cvm, setCvm] = useState('')
  const [watch, setWatch] = useState('')
  const [saved, setSaved] = useState(false)
  const [resolving, setResolving] = useState(false)
  const [resolveMsg, setResolveMsg] = useState<string | null>(null)
  const [dis, setDis] = useState<Dismissals | null>(null)
  const [mkt, setMkt] = useState<Market | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.profile().then((x) => {
      setP(x); setMd(x.markdown); setCve(x.cv_engineer); setCvm(x.cv_management); setWatch(lines(x.watchlist)); setTerms(lines(x.search_terms)); setLocs(lines(x.filters.locations))
      setExcl(lines(x.filters.exclude_terms)); setFloor(String(x.filters.salary_floor ?? '')); setThr(String(x.threshold))
    }).catch((e) => setErr(String(e)))
    api.dismissals().then(setDis).catch(() => undefined)
    api.market().then(setMkt).catch(() => undefined)
  }, [])

  async function save() {
    try {
      await api.saveProfile({
        markdown: md, cv_engineer: cve, cv_management: cvm, watchlist: split(watch), search_terms: split(terms), threshold: Number(thr) || 75,
        filters: { salary_floor: Number(floor) || undefined, locations: split(locs), exclude_terms: split(excl) },
      })
      setSaved(true); setTimeout(() => setSaved(false), 1500)
    } catch (e) { setErr(String(e)) }
  }

  async function findFeeds() {
    setResolving(true); setResolveMsg(null)
    try {
      await api.saveProfile({ watchlist: split(watch) })
      const r = await api.resolveWatchlist()
      setWatch(lines(r.watchlist))
      const found = r.resolved.map((x) => x.name).join(', ')
      setResolveMsg(`${r.resolved.length} found${found ? ` (${found})` : ''}; ${r.unresolved.length} left for the bot to look up`)
    } catch (e) { setErr(String(e)) } finally { setResolving(false) }
  }

  const k = (n: number) => `£${Math.round(n / 1000)}k`
  const Row = ({ label, b }: { label: string; b: Band }) => b ? (
    <li className="flex items-baseline gap-3">
      <span className="w-44 shrink-0 truncate text-dim">{label}</span>
      <span className="lcars-readout text-salmon">{k(b.p25)} · <span className="text-amber">{k(b.median)}</span> · {k(b.p75)}</span>
      <span className="lcars-code">n={b.n} max {k(b.max)}</span>
    </li>
  ) : null

  if (!p) return <p className="text-sm text-dim">{err ?? 'Loading'}</p>

  const box = 'lcars-input w-full'
  return (
    <div className="space-y-6">
      {err && <p className="border border-alert px-3 py-2 text-xs text-alert">{err}</p>}

      <section>
        <div className="lcars-label mb-1">About me</div>
        <p className="mb-2 text-sm text-dim">What the scoring reads. Roles, stacks, scale, what you want, what you won't do.</p>
        <textarea value={md} onChange={(e) => setMd(e.target.value)} rows={14} className={`${box} leading-relaxed`} />
      </section>

      {mkt && mkt.roles_with_stated_salary > 0 && (
        <section>
          <div className="lcars-label mb-1">Market, last {mkt.days} days</div>
          <p className="mb-2 text-sm text-dim">Stated salaries only, estimates excluded, one row per cluster. Lower quartile · median · upper quartile. {mkt.at_or_above_floor} of {mkt.roles_with_stated_salary} roles reach your £{Math.round((mkt.floor ?? 0) / 1000)}k floor.</p>
          <ul className="space-y-1 text-sm">
            <Row label="Engineer track" b={mkt.by_track.engineer} />
            <Row label="Management track" b={mkt.by_track.management} />
            <Row label="Good fit (score 60+)" b={mkt.good_fit_60_plus} />
            <Row label="Remote" b={mkt.remote} />
            <Row label="On site or hybrid" b={mkt.onsite} />
            {Object.entries(mkt.by_family).map(([n, b]) => <Row key={n} label={n} b={b} />)}
          </ul>
        </section>
      )}

      {dis && dis.total > 0 && (
        <section>
          <div className="lcars-label mb-1">What you've been saying no to</div>
          <p className="mb-2 text-sm text-dim">The scoring bot reads this. Three or more of one reason becomes a pattern it scores against.</p>
          <ul className="space-y-1 text-sm">
            {Object.entries(dis.by_reason).sort((a, b) => b[1].count - a[1].count).map(([k, v]) => (
              <li key={k} className="flex gap-3">
                <span className="lcars-readout w-6 text-right text-amber">{v.count}</span>
                <span className="w-16 uppercase tracking-[0.14em] text-dim">{k}</span>
                <span className="text-salmon">{v.examples.map((e) => e.title).join(', ')}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <div className="lcars-label mb-1">Watchlist, one per line</div>
        <p className="mb-2 text-sm text-dim">Companies you want. A name followed by a careers-page URL on Greenhouse, Lever, Ashby or Workable is crawled directly. A plain name flags that company wherever it appears. Watchlist roles ping at ten points below the threshold.</p>
        <textarea value={watch} onChange={(e) => setWatch(e.target.value)} rows={6} className={box} placeholder={'Monzo https://boards.greenhouse.io/monzo\nOctopus Energy https://jobs.lever.co/octoenergy\nCloudflare'} />
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <button onClick={findFeeds} disabled={resolving} className="lcars-btn">{resolving ? 'Checking feeds' : 'Find feeds for names'}</button>
          {resolveMsg && <span className="lcars-code text-lavender">{resolveMsg}</span>}
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="lcars-label mb-1 block">Base CV, engineer track (markdown)</span>
          <textarea value={cve} onChange={(e) => setCve(e.target.value)} rows={10} className={`${box} leading-relaxed`} />
        </label>
        <label className="block">
          <span className="lcars-label mb-1 block">Base CV, management track (markdown)</span>
          <textarea value={cvm} onChange={(e) => setCvm(e.target.value)} rows={10} className={`${box} leading-relaxed`} />
        </label>
        <label className="block">
          <span className="lcars-label mb-1 block">Search terms, one per line</span>
          <textarea value={terms} onChange={(e) => setTerms(e.target.value)} rows={8} className={box} />
        </label>
        <label className="block">
          <span className="lcars-label mb-1 block">Locations that count as reachable</span>
          <textarea value={locs} onChange={(e) => setLocs(e.target.value)} rows={8} className={box} />
        </label>
        <label className="block">
          <span className="lcars-label mb-1 block">Hide roles mentioning</span>
          <textarea value={excl} onChange={(e) => setExcl(e.target.value)} rows={5} className={box} />
        </label>
        <div className="space-y-4">
          <label className="block">
            <span className="lcars-label mb-1 block">Salary floor (£)</span>
            <input value={floor} onChange={(e) => setFloor(e.target.value)} inputMode="numeric" className={box} />
          </label>
          <label className="block">
            <span className="lcars-label mb-1 block">Notify me at score</span>
            <input value={thr} onChange={(e) => setThr(e.target.value)} inputMode="numeric" className={box} />
          </label>
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button onClick={save} className="lcars-btn lcars-btn-primary">Save changes</button>
        <button onClick={onDone} className="lcars-btn lcars-btn-quiet">Back to roles</button>
        {saved && <span className="lcars-code text-sage">Saved</span>}
      </div>
    </div>
  )
}
