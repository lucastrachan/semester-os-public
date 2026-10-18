import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { applyClassTheme } from '../styles/theme'
import { useAuth } from '../context/AuthContext'
import { ToastProvider } from './Toast'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useCourses } from '../lib/useCourses'
import CommandPalette from './CommandPalette'
import { MyAvatar } from './Avatar'
import CampusBadge from './CampusBadge'

const Icon = ({ children }: { children: ReactNode }) => (
  <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true">{children}</svg>
)

const NAV: { to: string; label: string; icon: ReactNode; secondary?: boolean }[] = [
  { to: '/today', label: 'Today', icon: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></> },
  { to: '/study', label: 'Study', icon: <><rect x="3" y="4" width="18" height="14" rx="2" /><path d="M8 21h8M12 18v3M7 9l2 2-2 2M12 13h4" /></> },
  { to: '/marketplace', label: 'Market', icon: <><path d="M3 8l2-4h14l2 4M3 8v12h18V8M3 8h18" /><path d="M9 12a3 3 0 0 0 6 0" /></> },
  { to: '/calendar', label: 'Calendar', icon: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></> },
  { to: '/settings', label: 'Settings', icon: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></> },
]

/** The account menu: closes on outside pointerdown, Escape, route change, choosing an item, and when focus leaves it. */
function AvatarMenu({ onSignOut }: { onSignOut: () => void }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const { pathname } = useLocation()
  useEffect(() => { setOpen(false) }, [pathname])
  useEffect(() => {
    if (!open) return
    const down = (e: PointerEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', down)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('pointerdown', down); document.removeEventListener('keydown', key) }
  }, [open])
  return (
    <div className="avatar-menu" ref={box} onBlur={e => { if (!box.current?.contains(e.relatedTarget as Node | null)) setOpen(false) }}>
      <button type="button" className="avatar-link" aria-haspopup="menu" aria-expanded={open} aria-label="Your account menu" onClick={() => setOpen(o => !o)}><MyAvatar size={32} /></button>
      {open && (
        <div className="avatar-pop" role="menu" onClick={() => setOpen(false)}>
          <NavLink to="/orders" role="menuitem">Orders</NavLink>
          <NavLink to="/settings" role="menuitem">Settings</NavLink>
          <button type="button" role="menuitem" onClick={onSignOut}>Sign out</button>
        </div>
      )}
    </div>
  )
}

export default function AppShell() {
  const { profile, authFetch, setProfile, signOut } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const campusPrimary = useAuth().tenant?.theme?.primary
  // The campus colour is the base everywhere; a class colour only lives on its own class page.
  useEffect(() => { if (!/^\/study\/[^/]+/.test(pathname)) applyClassTheme(null, campusPrimary) }, [pathname, campusPrimary])
  const { courses } = useCourses()
  const [palette, setPalette] = useState(false)
  const [unread, setUnread] = useState(0)
  // The Semester OS browser helper (content script on this site) posts {source:'blackboard', type:'sending'|'done'|'failed', count?} to this window.
  const [helper, setHelper] = useState<null | { type: 'sending' | 'done' | 'failed' | 'stuck'; count?: number; percent?: number }>(null)
  const muted = useRef(false)      // the student dismissed this scan run: stay quiet until a new run starts
  const lastHelperMsg = useRef(0)
  const finishedRun = useRef(false)               // latched when a run hits 100% / done, until a new run starts
  const sigRef = useRef({ s: '', at: 0 })         // same message and percent for 90 s: hide
  useEffect(() => {
    let t: number | undefined
    const onMsg = (e: MessageEvent) => {
      if (e.source !== window || e.origin !== window.location.origin) return
      const d = e.data as { source?: unknown; type?: unknown; count?: unknown } | null
      if (!d || d.source !== 'blackboard') return
      if (d.type !== 'sending' && d.type !== 'progress' && d.type !== 'done' && d.type !== 'failed' && d.type !== 'cancelled') return // class lists are shown on the onboarding page
      const type = d.type === 'done' || d.type === 'failed' ? d.type : 'sending'
      const now = Date.now()
      if (muted.current && now - lastHelperMsg.current > 30000) muted.current = false // a gap means a new run
      lastHelperMsg.current = now
      if (muted.current) return
      const count = typeof d.count === 'number' && d.count >= 0 && d.count < 1000 ? Math.floor(d.count) : undefined
      const p = (d as { percent?: unknown }).percent
      const percent = typeof p === 'number' && Number.isFinite(p) ? Math.max(0, Math.min(100, Math.round(p))) : undefined
      const phase = typeof (d as { phase?: unknown }).phase === 'string' ? (d as { phase: string }).phase : ''
      if (phase === 'fetch') return // fetch progress belongs to the chat's fetch card, never to this scan banner
      // A cancelled scan (or an idle phase at 0%) hides everything at once: no green "finished", and the latch and the 90 s rule start fresh.
      if (d.type === 'cancelled' || (phase === 'idle' && !(percent !== undefined && percent >= 100))) {
        finishedRun.current = false; sigRef.current = { s: '', at: 0 }; muted.current = false
        window.clearTimeout(t); setHelper(null)
        return
      }
      const isDone = d.type === 'done' || (percent !== undefined && percent >= 100) || phase === 'done'
      if (d.type !== 'failed') {
        if (finishedRun.current && d.type !== 'done') { if (isDone) return; finishedRun.current = false } // ignore later progress of a finished run
        if (isDone) {
          finishedRun.current = true
          setHelper({ type: 'done', count })
          window.clearTimeout(t)
          t = window.setTimeout(() => setHelper(null), 8000)
          return
        }
        const sg = `${d.type}|${percent}|${(d as { line?: unknown }).line ?? ''}`
        if (sigRef.current.s !== sg) sigRef.current = { s: sg, at: now }
        else if (now - sigRef.current.at > 90000) { muted.current = true; setHelper(null); return }
      }
      setHelper({ type, count, percent })
      window.clearTimeout(t)
      // A running scan that goes quiet for 60 s is shown as stuck; done disappears after a while, failed and stuck stay until dismissed.
      t = window.setTimeout(() => setHelper(h => (h?.type === 'sending' ? { type: 'stuck' } : null)), type === 'sending' ? 60000 : type === 'done' ? 8000 : 30000)
    }
    window.addEventListener('message', onMsg)
    return () => { window.removeEventListener('message', onMsg); window.clearTimeout(t) }
  }, [])
  // Safety: Escape dismisses the helper banner; the Ask palette never survives a page change; no stale "pending" UI state is ever restored.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !document.querySelector('[role="dialog"][aria-modal="true"]')) { muted.current = true; setHelper(null) } }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => { setPalette(false) }, [pathname])
  useEffect(() => {
    for (const store of [sessionStorage, localStorage]) {
      try { Object.keys(store).filter(k => /pending|sending|stuck|palette-open|scan-state/i.test(k)).forEach(k => store.removeItem(k)) } catch { /* storage unavailable */ }
    }
  }, [])
  // Class chats + marketplace chats, polled quietly every 60s while the tab is visible. Any failure counts as 0.
  useEffect(() => {
    let alive = true
    const poll = async () => {
      if (document.visibilityState !== 'visible') return
      let n = 0
      try { const r = await authFetch('/conversations/unread'); if (r.ok) n += (await r.json()).unread ?? 0 } catch { /* ignore */ }
      try { const r = await authFetch('/rooms'); if (r.ok) n += (await r.json()).unreadTotal ?? 0 } catch { /* ignore */ }
      if (alive) setUnread(n)
    }
    poll()
    const t = window.setInterval(poll, 60000)
    return () => { alive = false; window.clearInterval(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(p => !p) } }
    const open = () => setPalette(true)
    document.addEventListener('keydown', onKey)
    window.addEventListener('semester:open-chat', open)
    return () => { document.removeEventListener('keydown', onKey); window.removeEventListener('semester:open-chat', open) }
  }, [])
  // Load profile + tenant once so the campus theme and chip are right on any page (not only /today).
  useEffect(() => {
    if (profile) return
    authFetch('/me')
      .then(async r => {
        if (r.status === 401) { await signOut().catch(() => {}); navigate('/auth?mode=signin&expired=1', { replace: true }); return }
        const d = await r.json()
        if (!d.error) setProfile({ ...d.profile, needsName: d.needsName ?? d.profile?.needsName }, d.tenant)
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return (
    <ToastProvider>
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="app-shell">
        <header className="app-header">
          <NavLink to="/today" className="brand"><img src="/favicon.svg" width={24} height={24} alt="" />Semester <span className="brand-os">OS</span></NavLink>
          <CampusBadge />
          <NavLink to="/messages" className="icon-btn" aria-label={unread > 0 ? `Messages, ${unread} unread` : 'Messages'} title="Messages">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.5-4.6A8 8 0 1 1 21 12z" /></svg>
            {unread > 0 && <span className="icon-badge" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
          </NavLink>
          <button type="button" className="btn-ghost-sm" onClick={() => setPalette(true)} aria-keyshortcuts="Control+K Meta+K">Ask <span className="mono muted">Ctrl K</span></button>
          <AvatarMenu onSignOut={() => { signOut().catch(() => {}).finally(() => navigate('/')) }} />
        </header>
        <nav className="app-nav" aria-label="Primary">
          {NAV.map(n => (
            <NavLink key={n.to} to={n.to} className={`nav-item${n.secondary ? ' nav-secondary' : ''}`}>
              <Icon>{n.icon}</Icon><span className="nav-label">{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <main className="app-main" id="main" tabIndex={-1}>
          {helper && !pathname.startsWith('/onboarding') && ( // the onboarding card shows scan progress itself: never two copies of one message
          <div className="campus-note row" role="status" aria-live="polite" style={{ marginBottom: 'var(--s-4)' }}>
            {helper.type === 'sending' && <span className="spin" aria-hidden="true" />}
            <span className={helper.type === 'failed' || helper.type === 'stuck' ? 'field-error' : helper.type === 'done' ? 'scan-done-text' : undefined}>{helper.type === 'sending' ? `Semester OS helper is scanning your classes…${helper.percent != null ? ` ${helper.percent}%` : ''}` : helper.type === 'done' ? `Scan finished${helper.count ? `. ${helper.count} class${helper.count === 1 ? '' : 'es'} added` : ''}.` : helper.type === 'stuck' ? 'The scan seems stuck. Open the helper panel on your school site and press Cancel scan, then try again.' : 'The helper could not finish the scan. Open it on your school site and press Scan my classes again.'}</span>
            <button type="button" className="btn-ghost-sm" style={{ marginLeft: 'auto' }} aria-label="Dismiss this message" onClick={() => { muted.current = true; setHelper(null) }}>✕ Dismiss</button>
          </div>
        )}
          <Outlet />
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} courses={courses} />
    </ToastProvider>
  )
}
