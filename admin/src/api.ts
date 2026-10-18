import { fetchAuthSession } from 'aws-amplify/auth'

export interface AdminConfig { region: string; adminUserPoolId: string; adminClientId: string; apiUrl: string }

let config: AdminConfig | null = null
export const setConfig = (c: AdminConfig) => { config = c }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

/** Calls the admin API with the ID token (it carries `aud`, `email` and `cognito:groups`). */
export async function api<T = any>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  if (!config) throw new Error('not configured')
  const session = await fetchAuthSession()
  const token = session.tokens?.idToken?.toString()
  if (!token) throw new ApiError(401, 'Signed out')
  const res = await fetch(`${config.apiUrl}${path}`, {
    method: init.method ?? 'GET',
    headers: { Authorization: `Bearer ${token}`, ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
    body: init.body ? JSON.stringify(init.body) : undefined,
  })
  let data: any = null
  try { data = await res.json() } catch { /* empty body */ }
  if (!res.ok) throw new ApiError(res.status, data?.message || data?.error || `Request failed (${res.status})`)
  return data as T
}

export const timezones: string[] = (() => {
  try { return (Intl as any).supportedValuesOf('timeZone') as string[] } catch { return ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles'] }
})()
