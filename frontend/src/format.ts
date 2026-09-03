import type { Role } from './api'

export const FLOOR = 74000
const AGENCY = /recruit|resourc|placement|staffing|talent|search|people|consultancy|personnel|appointments|selection|associates|partners/i

export function isAgency(r: Role) {
  return !!r.company && AGENCY.test(r.company)
}

export function money(n: number) {
  return `£${Math.round(n / 1000)}k`
}

export function salary(r: Role) {
  if (r.salary_min && r.salary_max && r.salary_min !== r.salary_max) return `${money(r.salary_min)} to ${money(r.salary_max)}${r.salary_text === 'estimated' ? ' est.' : ''}`
  if (r.salary_max) return money(r.salary_max)
  if (r.salary_min) return money(r.salary_min)
  return r.salary_text ?? 'Salary not stated'
}

export function salaryShort(r: Role) {
  const k = (n: number) => Math.round(n / 1000)
  if (r.salary_min && r.salary_max && r.salary_min !== r.salary_max) return `£${k(r.salary_min)}-${k(r.salary_max)}k`
  if (r.salary_max) return money(r.salary_max)
  if (r.salary_min) return money(r.salary_min)
  return '--'
}

export function aboveFloor(r: Role) {
  return (r.salary_max ?? r.salary_min ?? 0) >= FLOOR
}

export function ago(iso: string) {
  const h = Math.max(0, (Date.now() - new Date(iso).getTime()) / 36e5)
  if (h < 1) return 'now'
  if (h < 24) return `${Math.floor(h)}h`
  return `${Math.floor(h / 24)}d`
}

export function joinReasons(rs: string[]) {
  return rs.slice(0, 2).map((x) => x.trim().replace(/\.$/, '')).join('. ') + '.'
}

export type Track = 'engineer' | 'management'

export function trackCode(t: string | null | undefined) {
  return t === 'management' ? 'MGMT' : t === 'engineer' ? 'ENG' : null
}

/* track colours: engineer teal, management ember */
export function trackText(t: string | null | undefined) {
  return t === 'management' ? 'text-orange' : t === 'engineer' ? 'text-teal' : 'text-faint'
}
export function trackBorder(t: string | null | undefined) {
  return t === 'management' ? 'border-orange' : t === 'engineer' ? 'border-teal' : 'border-transparent'
}
export function trackBg(t: string | null | undefined) {
  return t === 'management' ? 'bg-orange' : t === 'engineer' ? 'bg-teal' : 'bg-transparent'
}

export function agoLong(iso: string) {
  const m = Math.max(0, (Date.now() - new Date(iso).getTime()) / 6e4)
  if (m < 1) return 'just now'
  if (m < 60) return `${Math.floor(m)} min ago`
  const h = m / 60
  if (h < 24) return `${Math.floor(h)}h ago`
  return `${Math.floor(h / 24)}d ago`
}
