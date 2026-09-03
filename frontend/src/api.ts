export type Role = {
  id: number
  title: string
  company: string | null
  location: string | null
  remote_flag: number
  salary_min: number | null
  salary_max: number | null
  salary_text: string | null
  url: string
  posted_at: string | null
  first_seen: string
  source: string
  score: number | null
  track: string | null
  reasons: string[]
  state: string | null
  filtered: number
  filter_reason: string | null
  doc_cv?: string | null
  doc_cover?: string | null
  desc_quality?: string | null
  brief_status?: string | null
  red_flags?: number
  ai_interview?: string | null
}

export type Doc = {
  id: number
  kind: 'cv' | 'cover'
  status: 'pending' | 'ready' | 'failed'
  content: string | null
  requested_at: string
  generated_at: string | null
}

export type Flag = { kind: 'red' | 'amber' | 'green'; text: string; source?: string }
export type Brief = {
  verdict?: string
  ai_interview?: 'yes' | 'no' | 'unknown'
  salary_honesty?: string
  hiring_process?: string
  glassdoor?: { rating?: number | null; reviews?: number | null; themes?: string[] }
  flags?: Flag[]
  stack?: string[]
  news?: string[]
  company?: { size?: string; sector?: string; hq?: string }
  sources?: string[]
  error?: string
}
export type Research = { role_id: number; status: 'pending' | 'ready' | 'failed'; brief: Brief | null; requested_at: string; generated_at: string | null }

export type Profile = {
  markdown: string
  cv_engineer: string
  cv_management: string
  search_terms: string[]
  filters: { salary_floor?: number; locations?: string[]; exclude_terms?: string[] }
  threshold: number
  updated_at: string
}

export type RoleDetail = Role & { description: string | null; gaps: string[]; note: string | null; truncated?: boolean; desc_reason?: string | null }

export type SourceHealth = {
  id: number
  name: string
  kind: string
  enabled: number
  last_run: string | null
  last_ok: number | null
  last_error: string | null
}

async function j<T>(r: Promise<Response>): Promise<T> {
  const res = await r
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

export const api = {
  roles: (state?: string) => j<Role[]>(fetch(`/api/roles${state ? `?state=${state}` : ''}`)),
  role: (id: number) => j<RoleDetail>(fetch(`/api/roles/${id}`)),
  sources: () => j<SourceHealth[]>(fetch('/api/sources')),
  setStatus: (id: number, state: string) =>
    j<{ ok: boolean }>(fetch(`/api/roles/${id}/status`, {
      method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ state }),
    })),
  loadDescription: (id: number) => j<{ ok: boolean; description: string | null; truncated: boolean }>(fetch(`/api/roles/${id}/description`, { method: 'POST' })),
  rescore: (id: number) => j<{ ok: boolean }>(fetch(`/api/roles/${id}/score`, { method: 'DELETE' })),
  research: (id: number) => j<Research | null>(fetch(`/api/roles/${id}/research`)),
  requestResearch: (id: number) => j<{ ok: boolean }>(fetch(`/api/roles/${id}/research`, { method: 'POST' })),
  docs: (id: number) => j<Doc[]>(fetch(`/api/roles/${id}/documents`)),
  requestDoc: (id: number, kind: 'cv' | 'cover') =>
    j<{ id: number; status: string }>(fetch(`/api/roles/${id}/documents`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ kind }) })),
  profile: () => j<Profile>(fetch('/api/profile')),
  saveProfile: (p: Partial<Profile>) =>
    j<Profile>(fetch('/api/profile', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(p) })),
  crawl: () => j<Record<string, unknown>>(fetch('/api/crawl', { method: 'POST' })),
}
