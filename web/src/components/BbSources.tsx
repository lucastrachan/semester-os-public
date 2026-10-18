import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { safeHttps } from '../lib/market'

export interface AnySource { materialId?: string; title: string; url?: string; path?: string }

/** Has the Semester OS browser helper said anything on this page? (any {source:'blackboard'} message). Module-level, so every chat sees the same answer. */
let helperSeen = false
let helperBuild: string | null = null // from {source:'blackboard', type:'hello', build}
const subs = new Set<() => void>()
if (typeof window !== 'undefined') {
  window.addEventListener('message', e => {
    if (e.source !== window || e.origin !== window.location.origin) return
    const d = e.data as { source?: unknown; type?: unknown; build?: unknown } | null
    if (d?.source !== 'blackboard') return
    let changed = false
    if (!helperSeen) { helperSeen = true; changed = true }
    if (d.type === 'hello' && typeof d.build === 'string' && /^[\w .:+-]{1,40}$/.test(d.build) && d.build !== helperBuild) { helperBuild = d.build; changed = true }
    if (changed) subs.forEach(f => f())
  })
}
export const isHelperSeen = () => helperSeen
/** Blackboard urls an auto-fetch was already tried for in this session: never retried, so it cannot loop. */
export const triedUrls = new Set<string>()
function useHelperSeen() {
  return useHelperInfo().seen
}

/** Is the helper there, and which build is it? Updates when its hello arrives. */
export function useHelperInfo(): { seen: boolean; build: string | null } {
  const [, bump] = useState(0)
  useEffect(() => { const f = () => bump(n => n + 1); subs.add(f); return () => { subs.delete(f) } }, [])
  return { seen: helperSeen, build: helperBuild }
}

/** A tiny muted badge: which helper build is running, or that none was detected. */
export function HelperBadge() {
  const { seen, build } = useHelperInfo()
  return <span className="helper-badge" data-on={seen}>{seen ? (build ? `Helper ${build}` : 'Helper detected') : 'Helper not detected'}</span>
}

/** https links only (no javascript:, data: or http:). Source urls come from the index text built by the helper, so any https host is allowed. */
export function bbUrl(url: string | undefined, _lmsBase?: string | undefined): string | null {
  return safeHttps(url)
}

export type LinkKind = 'blackboard' | 'gdoc' | 'onedrive' | 'link'
/** What kind of place a link points to, from its host. Used only for the label. */
export function linkKind(href: string, lmsBase: string | undefined): LinkKind {
  let host = ''
  try { host = new URL(href).hostname.toLowerCase() } catch { return 'link' }
  let lmsHost = ''
  try { lmsHost = new URL(lmsBase ?? '').hostname.toLowerCase() } catch { /* none */ }
  if (host === 'blackboard.com' || host.endsWith('.blackboard.com') || (lmsHost && (host === lmsHost || host.endsWith(`.${lmsHost}`)))) return 'blackboard'
  if (host === 'docs.google.com' || host === 'drive.google.com' || host.endsWith('.google.com') && /docs|drive/.test(host)) return 'gdoc'
  if (host === '1drv.ms' || host === 'onedrive.live.com' || host.endsWith('.sharepoint.com') || host.endsWith('.onedrive.com')) return 'onedrive'
  return 'link'
}
export const KIND_LABEL: Record<LinkKind, string> = { blackboard: 'Open in Blackboard', gdoc: 'Open Google Doc', onedrive: 'Open OneDrive link', link: 'Open link' }

type Status = 'fetching' | 'ok' | 'fail'

/** Under an answer: "Open in Blackboard" for each source that points into Blackboard, plus a quiet "Fetch this for the helper" when the helper is present. */
export const LACKED_RE = /don't have|do not have|doesn't include|does not include|not in my course data|upload/i

/** At most 3 "Used" chips (deduped by title), then a quiet "+N more" that expands on click. */
export function UsedChips({ sources }: { sources?: AnySource[] }) {
  const [all, setAll] = useState(false)
  const seen = new Set<string>()
  const used = (sources ?? []).filter(s => s.materialId && !seen.has(s.title.toLowerCase()) && !!seen.add(s.title.toLowerCase()))
  if (used.length === 0) return null
  const shown = all ? used : used.slice(0, 3)
  return (
    <div className="chip-row used-chips" aria-label="Material used">
      {shown.map(s => <span key={s.materialId} className="chip chip-outline">Used: {s.title}</span>)}
      {!all && used.length > 3 && <button type="button" className="link-btn" onClick={() => setAll(true)}>+{used.length - 3} more</button>}
    </div>
  )
}

export default function BbSources({ sources, courseId }: { sources?: AnySource[]; courseId?: string | null; lacked?: boolean }) {
  const { tenant } = useAuth()
  const seen = useHelperSeen()
  const [status, setStatus] = useState<Record<string, Status>>({})
  const links = (sources ?? []).map(s => ({ s, href: bbUrl(s.url, tenant?.lms?.baseUrl) })).filter((x): x is { s: AnySource; href: string } => !!x.href).filter((x, i, arr) => arr.findIndex(y => y.href === x.href) === i).slice(0, 2)

  useEffect(() => {
    if (!courseId) return
    const onMsg = (e: MessageEvent) => {
      if (e.source !== window || e.origin !== window.location.origin) return
      const d = e.data as { source?: unknown; type?: unknown; courseId?: unknown; ok?: unknown } | null
      if (!d || d.source !== 'blackboard' || d.type !== 'fetched' || d.courseId !== courseId) return
      setStatus(st => {
        const next = { ...st }
        for (const k of Object.keys(next)) if (next[k] === 'fetching') next[k] = d.ok === true ? 'ok' : 'fail'
        return next
      })
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [courseId])

  if (links.length === 0) return null
  // Manual fetch only when the answer has no uploaded-material sources (so a good answer never gets a pointless fetch button).
  const noMaterial = !(sources ?? []).some(x => x.materialId)
  const helperHint = !seen && !!courseId && noMaterial

  function fetchIt(href: string) {
    if (!courseId) return
    setStatus(st => ({ ...st, [href]: 'fetching' }))
    try { window.postMessage({ source: 'sos-site', type: 'fetch', courseId, url: href }, window.location.origin) } catch { setStatus(st => ({ ...st, [href]: 'fail' })) }
    window.setTimeout(() => setStatus(st => (st[href] === 'fetching' ? { ...st, [href]: 'fail' } : st)), 30000)
  }

  return (
    <div className="stack bb-sources" style={{ gap: 'var(--s-1)', marginTop: 'var(--s-2)' }} aria-label="Where this came from">
      {links.map(({ s, href }, idx) => {
        const st = status[href]
        return (
          <div key={href} className="row" style={{ gap: 'var(--s-2)', alignItems: 'center' }}>
            <a className="btn-ghost btn-sm" href={href} target="_blank" rel="noopener noreferrer" title={s.path || s.title}>{KIND_LABEL[linkKind(href, tenant?.lms?.baseUrl)]}: {s.title}{s.path ? ` · ${s.path}` : ''}</a>
            {seen && courseId && noMaterial && idx === 0 && st !== 'ok' && <button type="button" className="link-btn" style={{ fontSize: 'var(--text-xs)' }} disabled={st === 'fetching'} onClick={() => { triedUrls.add(href); fetchIt(href) }}>{st === 'fetching' ? 'Fetching…' : linkKind(href, tenant?.lms?.baseUrl) === 'blackboard' ? 'Fetch from Blackboard' : 'Fetch this link'}</button>}
            {helperHint && idx === 0 && <span className="muted" style={{ fontSize: 'var(--text-xs)' }}>Install/open the helper to let me fetch this</span>}
            {st === 'ok' && <span className="muted" style={{ fontSize: 'var(--text-xs)' }} role="status">Fetched, ask again</span>}
            {st === 'fail' && <span className="muted" style={{ fontSize: 'var(--text-xs)' }} role="status">I could not read that link. Open it.</span>}
          </div>
        )
      })}
    </div>
  )
}


/** The only thing under an answer: a quiet "Sources (N)" that expands to a short list (plain titles, max 5; "Open" only where there is a safe link). */
export function SourcesLine({ sources }: { sources?: AnySource[] }) {
  const { tenant } = useAuth()
  const [open, setOpen] = useState(false)
  const seen = new Set<string>()
  const list = (sources ?? []).filter(s => {
    const key = (s.title || '').toLowerCase().trim() + '|' + (s.url ?? '')
    if (!s.title || seen.has(key)) return false
    seen.add(key); return true
  })
  if (list.length === 0) return null
  return (
    <div className="sources-line">
      <button type="button" className="link-btn" aria-expanded={open} onClick={() => setOpen(o => !o)}>Sources ({list.length})</button>
      {open && (
        <ul className="sources-list">
          {list.slice(0, 5).map((s, i) => {
            const href = bbUrl(s.url, tenant?.lms?.baseUrl)
            return <li key={i}><span>{s.title}{s.path ? ` · ${s.path}` : ''}</span>{href && <a href={href} target="_blank" rel="noopener noreferrer">Open</a>}</li>
          })}
        </ul>
      )}
    </div>
  )
}
