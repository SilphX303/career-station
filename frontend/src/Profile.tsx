import { useEffect, useState } from 'react'
import { api, type Profile } from './api'

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
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.profile().then((x) => {
      setP(x); setMd(x.markdown); setCve(x.cv_engineer); setCvm(x.cv_management); setWatch(lines(x.watchlist)); setTerms(lines(x.search_terms)); setLocs(lines(x.filters.locations))
      setExcl(lines(x.filters.exclude_terms)); setFloor(String(x.filters.salary_floor ?? '')); setThr(String(x.threshold))
    }).catch((e) => setErr(String(e)))
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

      <section>
        <div className="lcars-label mb-1">Watchlist, one per line</div>
        <p className="mb-2 text-sm text-dim">Companies you want. A name followed by a careers-page URL on Greenhouse, Lever, Ashby or Workable is crawled directly. A plain name flags that company wherever it appears. Watchlist roles ping at ten points below the threshold.</p>
        <textarea value={watch} onChange={(e) => setWatch(e.target.value)} rows={6} className={box} placeholder={'Monzo https://boards.greenhouse.io/monzo\nOctopus Energy https://jobs.lever.co/octoenergy\nCloudflare'} />
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
