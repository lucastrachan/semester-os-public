import { useCallback, useState } from 'react'
import { useAuth } from '../context/AuthContext'
// LMS onboarding helpers (the internal planning notes, Phase A). Semester OS never asks for, sees or stores a school password.
export type Lms = 'blackboard' | 'canvas' | 'other'

/** Map the campus config (`tenant.lms.type`) to a preselected choice, or null when unknown. */
export function lmsFromTenant(tenant: { lms?: { type?: string } } | null | undefined): Lms | null {
  const t = String(tenant?.lms?.type ?? '').toLowerCase()
  if (t.startsWith('blackboard')) return 'blackboard'
  if (t === 'canvas') return 'canvas'
  if (t === 'other' || t === 'none') return 'other'
  return null
}

/**
 * Canvas scan is not available yet: the backend contract (store a personal access token encrypted, run the scan,
 * report progress) does not exist. This is the ONE place to wire it up later. While false, the UI never asks for a
 * token and never sends one anywhere.
 */
export const CANVAS_SCAN_LIVE = false

type AuthFetch = (path: string, init?: RequestInit) => Promise<Response>

export interface CanvasScanResult { ok: boolean; message?: string }

export async function canvasScan(_authFetch: AuthFetch, _token: string): Promise<CanvasScanResult> {
  if (!CANVAS_SCAN_LIVE) return { ok: false, message: 'Canvas scanning is coming soon.' }
  // Future: POST /lms/canvas/token { token } then POST /lms/scan, then poll the scan status (see the Canvas contract when written).
  return { ok: false, message: 'Canvas scanning is coming soon.' }
}


const LMS_KEY = 'sos:lms'
const asLms = (v: unknown): Lms | null => (v === 'blackboard' || v === 'canvas' || v === 'other' ? v : null)

/**
 * The student's learning system: profile.lms when the backend has it, else what they picked on this device (localStorage),
 * else the campus default (tenant.lms.type), else null (we ask). Choosing saves to PATCH /me {lms} and to localStorage.
 */
export function useLmsChoice(): { lms: Lms | null; setLms: (v: Lms) => void } {
  const { profile, tenant, authFetch, setProfile } = useAuth()
  const [local, setLocal] = useState<Lms | null>(() => { try { return asLms(localStorage.getItem(LMS_KEY)) } catch { return null } })
  const lms = asLms(profile?.lms) ?? local ?? lmsFromTenant(tenant)
  const setLms = useCallback((v: Lms) => {
    setLocal(v)
    try { localStorage.setItem(LMS_KEY, v) } catch { /* storage unavailable */ }
    if (profile) setProfile({ ...profile, lms: v }, tenant)
    authFetch('/me', { method: 'PATCH', body: JSON.stringify({ lms: v }) }).catch(() => { /* the device copy still works */ })
  }, [profile, tenant, authFetch, setProfile])
  return { lms, setLms }
}
