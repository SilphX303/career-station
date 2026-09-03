import { useEffect, useRef, useState } from 'react'
import { api, type Doc, type Research, type Role, type RoleDetail } from './api'
import { agoLong, isAgency, joinReasons, money, salary, trackBorder, trackCode, trackText } from './format'

type Props = {
  role: Role
  threshold: number
  onClose: () => void
  onStatus: (id: number, state: string) => void
}

export default function RoleSheet({ role, threshold, onClose, onStatus }: Props) {
  const [detail, setDetail] = useState<RoleDetail | null>(null)
  const [docs, setDocs] = useState<Doc[]>([])
  const [research, setResearch] = useState<Research | null>(null)
  const [showDoc, setShowDoc] = useState<Doc | null>(null)
  const [copied, setCopied] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [dragY, setDragY] = useState(0)
  const [loadingAd, setLoadingAd] = useState(false)
  const [rescored, setRescored] = useState(false)
  const startY = useRef<number | null>(null)
  const scroller = useRef<HTMLDivElement>(null)

  async function loadDocs() {
    try { setDocs(await api.docs(role.id)) } catch { setDocs([]) }
  }
  async function loadResearch() {
    try { setResearch(await api.research(role.id)) } catch { setResearch(null) }
  }
  async function brief() {
    try { await api.requestResearch(role.id); await loadResearch() } catch (e) { setErr(String(e)) }
  }

  useEffect(() => {
    let live = true
    api.role(role.id).then((d) => { if (live) setDetail(d) }).catch((e) => setErr(String(e)))
    void loadDocs()
    void loadResearch()
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role.id])

  useEffect(() => {
    const pend = docs.some((d) => d.status === 'pending') || research?.status === 'pending'
    if (!pend) return
    const t = setInterval(() => { void loadDocs(); void loadResearch() }, 20000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docs, research])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [onClose])

  // Swipe down to dismiss, only when the sheet is scrolled to the top
  function onTouchStart(e: React.TouchEvent) {
    if ((scroller.current?.scrollTop ?? 0) > 0) return
    startY.current = e.touches[0].clientY
  }
  function onTouchMove(e: React.TouchEvent) {
    if (startY.current == null) return
    const dy = e.touches[0].clientY - startY.current
    if (dy > 0) setDragY(dy)
  }
  function onTouchEnd() {
    if (dragY > 110) onClose()
    setDragY(0); startY.current = null
  }

  async function loadAd() {
    setLoadingAd(true)
    try {
      const r = await api.loadDescription(role.id)
      setDetail((d) => d ? { ...d, description: r.description, truncated: r.truncated } : d)
      if (!r.ok) setErr('Could not fetch more of this ad; open it on the board.')
    } catch (e) { setErr(String(e)) } finally { setLoadingAd(false) }
  }
  async function rescore() {
    try { await api.rescore(role.id); setRescored(true) } catch (e) { setErr(String(e)) }
  }

  async function draft(kind: 'cv' | 'cover') {
    try { await api.requestDoc(role.id, kind); await loadDocs() } catch (e) { setErr(String(e)) }
  }
  async function copy(text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1200) } catch { setErr('Copy failed') }
  }

  const above = role.score != null && role.score >= threshold
  const state = role.state ?? 'new'

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-space/90 backdrop-blur-sm" onClick={onClose}>
      <div
        className="sheet-enter mt-auto flex h-[96dvh] flex-col border-t border-line-hi bg-panel sm:mx-auto sm:mt-6 sm:h-auto sm:max-h-[92dvh] sm:w-[720px] sm:border"
        style={{ transform: dragY ? `translateY(${dragY}px)` : undefined, transition: dragY ? 'none' : undefined }}
        onClick={(e) => e.stopPropagation()}
        onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}
      >
        {/* grab handle + header */}
        <div className={`shrink-0 border-b border-line border-l-2 px-4 pb-3 pt-2 ${trackBorder(role.track)}`}>
          <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line-hi sm:hidden" />
          <div className="flex items-start gap-4">
            <div className="w-14 shrink-0 text-right">
              <div className={`lcars-readout text-4xl leading-none ${role.score == null ? 'text-faint' : above ? 'text-amber' : 'text-dim'}`}>
                {role.score ?? '--'}
              </div>
              <div className={`lcars-code mt-1 ${trackText(role.track)}`}>{trackCode(role.track) ?? 'UNSCORED'}</div>
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-lg leading-tight text-glow">{role.title}</h2>
              <p className="mt-1 text-sm text-dim">
                {isAgency(role) && <span className="lcars-code mr-2 border border-line-hi px-1">Agency</span>}
                {role.company ?? 'Unknown company'}{role.location ? `, ${role.location}` : ''}
              </p>
              <p className={`lcars-readout mt-0.5 text-sm ${(role.salary_max ?? role.salary_min ?? 0) >= 74000 ? 'text-sage' : 'text-dim'}`}>{salary(role)}</p>
            </div>
            <button onClick={onClose} className="lcars-btn lcars-btn-quiet hidden sm:block" aria-label="Close">Close</button>
          </div>
        </div>

        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-4 py-4 space-y-6">
          {err && <p className="border border-alert px-3 py-2 text-xs text-alert">{err}</p>}

          {role.reasons.length > 0 && (
            <section>
              <div className="lcars-label mb-1.5">Fit</div>
              <p className="text-sm leading-relaxed text-glow">{joinReasons(role.reasons)}</p>
            </section>
          )}

          <section>
            <div className="lcars-label mb-1.5">Brief</div>
            {!research && <button onClick={brief} className="lcars-btn lcars-btn-primary">Brief me</button>}
            {research?.status === 'pending' && (
              <span className="lcars-btn opacity-70"><span className="alive-dot mr-2 inline-block align-middle" />Researching, requested {agoLong(research.requested_at)}</span>
            )}
            {research?.status === 'failed' && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="lcars-code text-alert">{research.brief?.error ?? 'Research failed'}</span>
                <button onClick={brief} className="lcars-btn">Retry</button>
              </div>
            )}
            {research?.status === 'ready' && research.brief && (
              <div className="space-y-3">
                {research.brief.verdict && <p className="text-sm leading-relaxed text-glow">{research.brief.verdict}</p>}
                <div className="flex flex-wrap gap-2">
                  <span className={`lcars-code border px-1.5 py-0.5 ${research.brief.ai_interview === 'yes' ? 'border-alert text-alert' : research.brief.ai_interview === 'no' ? 'border-sage text-sage' : 'border-line-hi'}`}>
                    AI interview: {research.brief.ai_interview ?? 'unknown'}
                  </span>
                  {research.brief.glassdoor?.rating != null && (
                    <span className="lcars-code border border-line-hi px-1.5 py-0.5">Glassdoor {research.brief.glassdoor.rating}{research.brief.glassdoor.reviews ? ` (${research.brief.glassdoor.reviews})` : ''}</span>
                  )}
                  {research.brief.company?.size && <span className="lcars-code border border-line-hi px-1.5 py-0.5">{research.brief.company.size}</span>}
                </div>
                {(research.brief.flags ?? []).length > 0 && (
                  <ul className="space-y-1 text-sm">
                    {research.brief.flags!.map((f, i) => (
                      <li key={i} className="flex gap-2">
                        <span className={`lcars-code mt-1 shrink-0 ${f.kind === 'red' ? 'text-alert' : f.kind === 'green' ? 'text-sage' : 'text-amber'}`}>{f.kind === 'red' ? 'RED' : f.kind === 'green' ? 'GRN' : 'AMB'}</span>
                        <span className="text-salmon">{f.text}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {research.brief.salary_honesty && <p className="text-sm text-salmon"><span className="lcars-code mr-2">Salary</span>{research.brief.salary_honesty}</p>}
                {research.brief.hiring_process && <p className="text-sm text-salmon"><span className="lcars-code mr-2">Process</span>{research.brief.hiring_process}</p>}
                {(research.brief.glassdoor?.themes ?? []).length > 0 && <p className="text-sm text-salmon"><span className="lcars-code mr-2">Reviews</span>{research.brief.glassdoor!.themes!.join('; ')}</p>}
                {(research.brief.stack ?? []).length > 0 && <p className="text-sm text-salmon"><span className="lcars-code mr-2">Stack</span>{research.brief.stack!.join(', ')}</p>}
                {(research.brief.news ?? []).length > 0 && <p className="text-sm text-salmon"><span className="lcars-code mr-2">News</span>{research.brief.news!.join('; ')}</p>}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  {(research.brief.sources ?? []).slice(0, 6).map((u, i) => <a key={i} href={u} target="_blank" rel="noreferrer" className="lcars-code text-lavender hover:underline">{new URL(u).hostname.replace('www.', '')}</a>)}
                  <button onClick={brief} className="lcars-code text-dim hover:text-lavender">redo</button>
                  {research.generated_at && <span className="lcars-code">briefed {agoLong(research.generated_at)}</span>}
                </div>
              </div>
            )}
          </section>

          {detail && detail.gaps.length > 0 && (
            <section>
              <div className="lcars-label mb-1.5">Gaps to address</div>
              <ul className="space-y-1 text-sm text-salmon">
                {detail.gaps.map((g, i) => <li key={i} className="flex gap-2"><span className="text-faint">·</span>{g}</li>)}
              </ul>
            </section>
          )}

          {detail?.note && (
            <section>
              <div className="lcars-label mb-1.5">Pipeline</div>
              <p className="lcars-readout text-sm text-salmon">{detail.note}</p>
            </section>
          )}

          <section>
            <div className="lcars-label mb-2">Status: <span className="text-lavender">{state}</span></div>
            <div className="flex flex-wrap gap-2">
              {state !== 'shortlisted' && state !== 'applied' && state !== 'progressing' && (
                <button onClick={() => onStatus(role.id, 'shortlisted')} className="lcars-btn lcars-btn-primary">Shortlist</button>
              )}
              {state !== 'applied' && state !== 'progressing' && (
                <button onClick={() => onStatus(role.id, 'applied')} className="lcars-btn">Mark applied</button>
              )}
              {state === 'applied' && <button onClick={() => onStatus(role.id, 'progressing')} className="lcars-btn">Progressing</button>}
              {(state === 'applied' || state === 'progressing') && (
                <button onClick={() => onStatus(role.id, 'rejected')} className="lcars-btn lcars-btn-quiet">Rejected</button>
              )}
              {state !== 'dismissed' && <button onClick={() => onStatus(role.id, 'dismissed')} className="lcars-btn lcars-btn-quiet">Not for me</button>}
              {role.url && <a href={role.url} target="_blank" rel="noreferrer" className="lcars-btn">Open ad</a>}
            </div>
          </section>

          <section>
            <div className="lcars-label mb-2">Documents</div>
            <div className="flex flex-wrap gap-2">
              {(['cv', 'cover'] as const).map((k) => {
                const d = docs.find((x) => x.kind === k)
                const label = k === 'cv' ? 'CV' : 'Cover note'
                if (!d) return <button key={k} onClick={() => draft(k)} className="lcars-btn lcars-btn-primary">Draft {label}</button>
                if (d.status === 'pending') return (
                  <span key={k} className="lcars-btn opacity-70">
                    <span className="alive-dot mr-2 inline-block align-middle" />{label} drafting, requested {agoLong(d.requested_at)}
                  </span>
                )
                if (d.status === 'failed') return <button key={k} onClick={() => draft(k)} className="lcars-btn text-alert">{label} failed, retry</button>
                return (
                  <span key={k} className="flex gap-2">
                    <button onClick={() => setShowDoc(showDoc?.id === d.id ? null : d)} className="lcars-btn">{showDoc?.id === d.id ? `Hide ${label}` : `View ${label}`}</button>
                    <a href={`/api/documents/${d.id}.pdf`} className="lcars-btn lcars-btn-primary">{label} PDF</a>
                    <button onClick={() => draft(k)} className="lcars-btn lcars-btn-quiet">Redo</button>
                  </span>
                )
              })}
            </div>
            {docs.some((d) => d.status === 'ready' && d.generated_at) && (
              <p className="lcars-code mt-2">
                {docs.filter((d) => d.status === 'ready' && d.generated_at).map((d) => `${d.kind === 'cv' ? 'CV' : 'Cover note'} drafted ${agoLong(d.generated_at!)}`).join(' · ')}
              </p>
            )}
            {docs.find((d) => d.status === 'failed')?.content && (
              <p className="lcars-code mt-2 whitespace-normal text-alert">{docs.find((d) => d.status === 'failed')!.content}</p>
            )}
            {showDoc?.content && (
              <div className="lcars-panel mt-3 p-3">
                <div className="mb-2 flex justify-end">
                  <button onClick={() => copy(showDoc.content!)} className="lcars-code text-lavender">{copied ? 'Copied' : 'Copy markdown'}</button>
                </div>
                <div className="lcars-prose">{showDoc.content}</div>
              </div>
            )}
          </section>

          <section>
            <div className="lcars-label mb-1.5">The ad</div>
            {!detail && <p className="text-sm text-dim">Loading</p>}
            {detail && (
              <div className="lcars-prose">
                {detail.description || (role.url ? 'No description captured for this one; open the ad.' : 'Added from the inbox sweep; no ad on file.')}
              </div>
            )}
            {detail?.truncated && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="lcars-code text-amber/80">Partial ad{detail.desc_reason ? `: ${detail.desc_reason}` : ''}</span>
                <button onClick={loadAd} disabled={loadingAd} className="lcars-btn">{loadingAd ? 'Loading' : 'Load full ad'}</button>
              </div>
            )}
            {detail && !detail.truncated && role.score != null && (
              <div className="mt-3">
                {rescored
                  ? <span className="lcars-code text-lavender">Queued for rescoring; the bot picks it up within the hour</span>
                  : <button onClick={rescore} className="lcars-btn lcars-btn-quiet">Rescore with full ad</button>}
              </div>
            )}
          </section>

          <div className="lcars-code pb-2">{role.source} · first seen {role.first_seen.slice(0, 10)}{role.posted_at ? ` · posted ${String(role.posted_at).slice(0, 10)}` : ''}{role.salary_max ? ` · max ${money(role.salary_max)}` : ''}</div>
        </div>
      </div>
    </div>
  )
}
