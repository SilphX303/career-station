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
  reasons: string[]
  state: string | null
}

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
  sources: () => j<SourceHealth[]>(fetch('/api/sources')),
  setStatus: (id: number, state: string) =>
    j<{ ok: boolean }>(fetch(`/api/roles/${id}/status`, {
      method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ state }),
    })),
  crawl: () => j<Record<string, unknown>>(fetch('/api/crawl', { method: 'POST' })),
}
