import { useEffect, useState } from 'react'
import { autoThemeFromName, isHex } from '../styles/color'

export type ResolveState = 'idle' | 'resolving' | 'resolved' | 'unknown'
export interface Resolved { state: ResolveState; name?: string; color?: string; colorStatus?: 'placeholder' | 'needs_review' | 'verified' }

const DOMAIN_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/

/** Domain part of what the student typed, or null until it looks like a real domain. */
export function domainOf(email: string): string | null {
  const at = email.lastIndexOf('@')
  if (at < 0) return null
  const d = email.slice(at + 1).trim().toLowerCase()
  return d.length <= 100 && DOMAIN_RE.test(d) ? d : null
}

/**
 * GET /public/resolve?domain=... (AUTO_CAMPUS.md). Defensive: the route may not exist yet and its exact shape is not final,
 * so ANY error, odd shape or missing name means "unknown school" and the page keeps its default theme.
 */
export function useResolveDomain(email: string): Resolved {
  const domain = domainOf(email)
  const [res, setRes] = useState<Resolved>({ state: 'idle' })

  useEffect(() => {
    if (!domain) { setRes({ state: 'idle' }); return }
    // Rule: only .edu addresses are supported, so anything else is "unknown" without asking the server.
    if (!domain.endsWith('.edu')) { setRes({ state: 'unknown' }); return }
    const api = (window as any).__config?.apiUrl as string | undefined
    if (!api) { setRes({ state: 'idle' }); return }
    const ctl = new AbortController()
    setRes(r => (r.state === 'resolved' ? r : { state: 'resolving' }))
    const t = window.setTimeout(async () => {
      try {
        const r = await fetch(`${api}/public/resolve?domain=${encodeURIComponent(domain)}`, { signal: ctl.signal })
        // A .edu domain the server says it doesn't know (404 / found:false) is "unknown". Any other failure (route not
        // deployed yet, 401/5xx, network) must NOT claim the school is unsupported: stay neutral and let sign-up go ahead.
        if (r.status === 404) { setRes({ state: 'unknown' }); return }
        if (!r.ok) throw new Error('unavailable')
        const j = await r.json()
        const campus = j?.campus ?? j?.tenant ?? j
        const name = typeof campus?.name === 'string' ? campus.name.slice(0, 80) : ''
        if (j?.found === false) { setRes({ state: 'unknown' }); return }
        if (!name) throw new Error('unavailable')
        const primary = campus?.theme?.primary
        const cs = campus?.colorStatus ?? j?.colorStatus
        setRes({ state: 'resolved', name, color: isHex(primary) ? primary : autoThemeFromName(name), colorStatus: cs === 'placeholder' || cs === 'needs_review' || cs === 'verified' ? cs : undefined })
      } catch (e) {
        if ((e as Error).name !== 'AbortError') setRes({ state: 'idle' })
      }
    }, 400) // debounce while the student is still typing
    return () => { window.clearTimeout(t); ctl.abort() }
  }, [domain])

  return res
}
