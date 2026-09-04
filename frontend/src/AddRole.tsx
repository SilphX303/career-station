import { useEffect, useRef, useState } from 'react'
import { api, type IngestItem } from './api'

export default function AddRole({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [text, setText] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [recent, setRecent] = useState<IngestItem[]>([])
  const input = useRef<HTMLInputElement>(null)

  async function loadRecent() { try { setRecent(await api.ingestList()) } catch { setRecent([]) } }
  useEffect(() => { void loadRecent() }, [])
  useEffect(() => {
    if (!recent.some((r) => r.status === 'pending')) return
    const t = setInterval(() => void loadRecent(), 15000)
    return () => clearInterval(t)
  }, [recent])

  async function submit() {
    if (files.length === 0 && !text.trim()) { setErr('A screenshot or some ad text, one or the other'); return }
    setBusy(true); setErr(null)
    try {
      await api.ingest(files, text.trim() || undefined, url.trim() || undefined)
      setFiles([]); setText(''); setUrl('')
      await loadRecent(); onAdded()
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-space/90 backdrop-blur-sm" onClick={onClose}>
      <div className="sheet-enter mt-auto flex max-h-[96dvh] flex-col border-t border-line-hi bg-panel sm:mx-auto sm:mt-6 sm:w-[640px] sm:border" onClick={(e) => e.stopPropagation()}>
        <div className="shrink-0 border-b border-line px-4 pb-3 pt-2">
          <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line-hi sm:hidden" />
          <div className="flex items-center justify-between">
            <h2 className="text-lg text-glow">Add a role</h2>
            <button onClick={onClose} className="lcars-btn lcars-btn-quiet">Close</button>
          </div>
          <p className="mt-1 text-sm text-dim">For LinkedIn, company sites and anything the crawl can't reach. Screenshots go to the bot to read; allow ten minutes.</p>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {err && <p className="border border-alert px-3 py-2 text-xs text-alert">{err}</p>}

          <section>
            <div className="lcars-label mb-1.5">Screenshots</div>
            <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" multiple className="hidden"
              onChange={(e) => setFiles([...files, ...Array.from(e.target.files ?? [])])} />
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => input.current?.click()} className="lcars-btn lcars-btn-primary">Choose images</button>
              {files.map((f, i) => (
                <span key={i} className="lcars-code border border-line-hi px-1.5 py-0.5">{f.name.slice(0, 18)} <button onClick={() => setFiles(files.filter((_, j) => j !== i))} className="text-alert">×</button></span>
              ))}
            </div>
            <p className="lcars-code mt-1 whitespace-normal">Long ads: several screenshots in order are read as one.</p>
          </section>

          <section>
            <div className="lcars-label mb-1.5">Or paste the ad text</div>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} className="lcars-input w-full leading-relaxed" placeholder="Title, company, location, salary, the description. Anything you can copy." />
          </section>

          <section>
            <div className="lcars-label mb-1.5">Link (optional)</div>
            <input value={url} onChange={(e) => setUrl(e.target.value)} inputMode="url" className="lcars-input w-full" placeholder="https://" />
          </section>

          <button onClick={submit} disabled={busy} className="lcars-btn lcars-btn-primary">{busy ? 'Sending' : 'Add to career-station'}</button>

          {recent.length > 0 && (
            <section>
              <div className="lcars-label mb-1.5">Recent</div>
              <ul className="space-y-1 text-sm">
                {recent.slice(0, 8).map((r) => (
                  <li key={r.id} className="flex items-center gap-2">
                    <span className={`lcars-code ${r.status === 'ready' ? 'text-sage' : r.status === 'failed' ? 'text-alert' : 'text-amber'}`}>{r.status}</span>
                    <span className="text-dim">{r.kind === 'image' ? `${r.images.length} screenshot${r.images.length === 1 ? '' : 's'}` : 'pasted text'}</span>
                    {r.status === 'pending' && <span className="alive-dot" />}
                    {r.error && <span className="lcars-code text-alert">{r.error}</span>}
                    {r.role_id && <span className="lcars-code">role #{r.role_id}</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
