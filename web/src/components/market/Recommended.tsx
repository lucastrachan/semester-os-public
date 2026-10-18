import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCourses } from '../../lib/useCourses'
import { useAuth } from '../../context/AuthContext'
import { kindOf, money, type ListingV2 } from '../../lib/market'

interface Section { id: string; title: string; reason?: string; suggestion?: boolean; listings: { reason: string; listing: ListingV2; courseCode?: string; bookTitle?: string; suggestion?: boolean }[] }

/** "Recommended for you": calm, collapsible, ONE horizontally scrolling row of small cards, each with a one-line reason. */
export default function Recommended({ onOpen, accept, fallback = [] }: { onOpen: (l: ListingV2) => void; accept?: (l: ListingV2) => boolean; fallback?: ListingV2[] }) {
  const { courses, loading: coursesLoading, reload: reloadCourses } = useCourses()
  const courseKey = courses.map(c => c.id).join(',')
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [sections, setSections] = useState<Section[]>([])
  const [open, setOpen] = useState(() => { try { return localStorage.getItem('rec-open') !== '0' } catch { return true } })

  const [loaded, setLoaded] = useState(false)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const load = useCallback(async () => {
    try {
      const r = await fetchRef.current('/listings/for-you')
      if (r.ok && alive.current) {
        const j = await r.json()
        setSections(Array.isArray(j.sections) ? j.sections.filter((s: Section) => s.listings?.length) : [])
      }
    } catch { /* keep what we have */ } finally { if (alive.current) setLoaded(true) }
  }, [])
  // Refetch when the class list changes, and when the tab regains focus.
  useEffect(() => { if (user) void load() }, [user, courseKey, load])
  useEffect(() => {
    const again = () => { if (document.visibilityState === 'visible') { reloadCourses(); void load() } }
    window.addEventListener('focus', again)
    document.addEventListener('visibilitychange', again)
    return () => { window.removeEventListener('focus', again); document.removeEventListener('visibilitychange', again) }
  }, [load, reloadCourses])
  const hasPicks = sections.some(sec => sec.listings.some(c => !accept || accept(c.listing)))
  // No picks yet: look again every 5 s for up to 60 s (the class list may still be arriving from the helper scan).
  useEffect(() => {
    if (!loaded || hasPicks || !user) return
    const start = Date.now()
    const t = window.setInterval(() => {
      if (Date.now() - start > 60000) { window.clearInterval(t); return }
      reloadCourses(); void load()
    }, 5000)
    return () => window.clearInterval(t)
  }, [loaded, hasPicks, user, courseKey, load, reloadCourses])

  const toggle = () => setOpen(o => { try { localStorage.setItem('rec-open', o ? '0' : '1') } catch { /* storage unavailable */ } return !o })
  // one row: cards across sections in order, no stacked section titles
  const flat = sections.flatMap(s => s.listings.slice(0, 6).map(c => ({ s, c }))).filter(({ c }) => !accept || accept(c.listing)).slice(0, 12)

  if (!loaded) return <div className="rec-grid" aria-busy="true" aria-label="Loading recommendations">{[0, 1, 2].map(i => <div key={i} className="skeleton-block" style={{ flex: '0 0 min(15rem, 78vw)', height: '5.25rem' }} />)}</div>
  if (flat.length === 0) {
    // No picks (usually: no classes yet). Show the newest listings of this section instead, plus a quiet nudge to connect classes.
    const newest = [...fallback].sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))).slice(0, 12)
    if (newest.length === 0) return null
    return (
      <section aria-label="New on your campus" className="stack" style={{ gap: 'var(--s-2)' }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span className="eyebrow">New on your campus</span>
          {!coursesLoading && courses.length === 0 && <span className="muted" style={{ fontSize: 'var(--text-sm)' }}>Scan your classes to get picks for your courses. <Link to="/onboarding" className="link-btn">Connect classes</Link></span>}
        </div>
        <div className="rec-grid" role="list" aria-label="New listings">
          {newest.map(l => (
            <button key={l.id} type="button" role="listitem" className="rec-card" onClick={() => onOpen(l)} aria-label={`${l.ticket?.event || l.title}, new`}>
              <span className="rec-reason">{l.campus.shortName}</span>
              <strong>{l.ticket?.event || l.title}</strong>
              <span className="muted">{kindOf(l) === 'service' ? (l.price === 0 ? 'Free' : `${money(l.price)}/hr`) : money(l.price)}</span>
            </button>
          ))}
        </div>
      </section>
    )
  }
  return (
    <section aria-label="Recommended for you" className="stack" style={{ gap: 'var(--s-2)' }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="eyebrow">Recommended for you</span>
        <button type="button" className="link-btn" aria-expanded={open} onClick={toggle}>{open ? 'Hide' : 'Show'}</button>
      </div>
      {open && (
        <div className="rec-grid" role="list" aria-label="Recommended listings">
          {flat.map(({ s, c }) => (
            <button key={`${s.id}-${c.listing.id}`} type="button" role="listitem" className="rec-card" onClick={() => onOpen(c.listing)} aria-label={`${c.listing.title}, ${c.reason}`}>
              <span className="rec-reason">{c.suggestion || s.suggestion ? 'Suggestion · ' : ''}{c.reason}</span>
              <strong>{c.listing.ticket?.event || c.listing.title}</strong>
              <span className="muted">{kindOf(c.listing) === 'service' ? (c.listing.price === 0 ? 'Free' : `${money(c.listing.price)}/hr`) : money(c.listing.price)} · {c.listing.campus.shortName}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
