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
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.profile().then((x) => {
      setP(x); setMd(x.markdown); setCve(x.cv_engineer); setCvm(x.cv_management); setTerms(lines(x.search_terms)); setLocs(lines(x.filters.locations))
      setExcl(lines(x.filters.exclude_terms)); setFloor(String(x.filters.salary_floor ?? '')); setThr(String(x.threshold))
    }).catch((e) => setErr(String(e)))
  }, [])

  async function save() {
    try {
      await api.saveProfile({
        markdown: md, cv_engineer: cve, cv_management: cvm, search_terms: split(terms), threshold: Number(thr) || 75,
        filters: { salary_floor: Number(floor) || undefined, locations: split(locs), exclude_terms: split(excl) },
      })
      setSaved(true); setTimeout(() => setSaved(false), 1500)
    } catch (e) { setErr(String(e)) }
  }

  if (!p) return <p className="text-sm text-muted">{err ?? 'Loading'}</p>

  const box = 'w-full rounded border border-line bg-surface px-3 py-2 text-sm text-paper focus:border-amber focus:outline-none'
  return (
    <div className="space-y-6">
      {err && <p className="rounded border border-rust px-3 py-2 text-sm text-rust">{err}</p>}

      <section>
        <h2 className="mb-1 font-medium">About me</h2>
        <p className="mb-2 text-sm text-muted">What the scoring reads. Roles, stacks, scale, what you want, what you won't do.</p>
        <textarea value={md} onChange={(e) => setMd(e.target.value)} rows={14} className={`${box} font-mono text-xs leading-relaxed`} />
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm">Base CV, engineer track (markdown)</span>
          <textarea value={cve} onChange={(e) => setCve(e.target.value)} rows={10} className={`${box} font-mono text-xs leading-relaxed`} />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm">Base CV, management track (markdown)</span>
          <textarea value={cvm} onChange={(e) => setCvm(e.target.value)} rows={10} className={`${box} font-mono text-xs leading-relaxed`} />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm">Search terms, one per line</span>
          <textarea value={terms} onChange={(e) => setTerms(e.target.value)} rows={8} className={box} />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm">Locations that count as reachable</span>
          <textarea value={locs} onChange={(e) => setLocs(e.target.value)} rows={8} className={box} />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm">Hide roles mentioning</span>
          <textarea value={excl} onChange={(e) => setExcl(e.target.value)} rows={5} className={box} />
        </label>
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm">Salary floor (£)</span>
            <input value={floor} onChange={(e) => setFloor(e.target.value)} inputMode="numeric" className={box} />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm">Notify me at score</span>
            <input value={thr} onChange={(e) => setThr(e.target.value)} inputMode="numeric" className={box} />
          </label>
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button onClick={save} className="rounded-full bg-paper px-4 py-1.5 text-sm font-medium text-ink">Save changes</button>
        <button onClick={onDone} className="text-sm text-muted hover:text-paper">Back to roles</button>
        {saved && <span className="text-sm text-sage">Saved</span>}
      </div>
    </div>
  )
}
