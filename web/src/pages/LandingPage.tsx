import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { deriveTheme, isHex } from '../styles/color'

interface Tenant {
  id: string
  name: string
  shortName: string
  domains?: string[]
  theme?: { primary?: string }
}

// Shown first when present, matched by email domain (short names collide: UA is Alabama, Arizona and Akron). The rest fill in alphabetically.
// Nothing here is hard-coded data: it only orders what the API returns.
const FEATURED_FIRST = ['ua.edu', 'auburn.edu', 'gatech.edu', 'vanderbilt.edu', 'utk.edu', 'lsu.edu', 'ufl.edu', 'uga.edu', 'olemiss.edu', 'msstate.edu']
const FEATURED_COUNT = 8
const MAX_RESULTS = 8

const norm = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9.\s]/g, ' ').replace(/\s+/g, ' ').trim()

function Tile({ t }: { t: Tenant }) {
  const primary = isHex(t.theme?.primary) ? (t.theme!.primary as string) : '#4F46E5'
  const ink = deriveTheme(primary, 'light').accentInk
  return (
    <>
      <span className="campus-tile" aria-hidden="true" style={{ background: primary, color: ink }}>{(t.shortName || t.name).replace(/[^A-Za-z0-9]/g, '').slice(0, 3).toUpperCase()}</span>
      <span className="campus-text"><strong>{t.shortName || t.name}</strong><span>{t.name}</span></span>
    </>
  )
}

export default function LandingPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [picked, setPicked] = useState<Tenant | null>(null)

  useEffect(() => {
    const cfg = (window as any).__config
    if (!cfg?.apiUrl) { setLoading(false); return }
    const ac = new AbortController()
    fetch(`${cfg.apiUrl}/public/tenants`, { signal: ac.signal })
      .then(r => r.json())
      .then(d => { setTenants(Array.isArray(d.tenants) ? d.tenants : []); setLoading(false) })
      .catch(() => { if (!ac.signal.aborted) setLoading(false) })
    return () => ac.abort()
  }, [])

  const sorted = useMemo(() => [...tenants].sort((a, b) => (a.shortName || a.name).localeCompare(b.shortName || b.name)), [tenants])
  // Normalise every school once (not on each keystroke): 250+ schools stay instant, and only the few visible rows are rendered.
  const index = useMemo(() => sorted.map(t => ({ t, name: norm(t.name), short: norm(t.shortName || ''), domains: (t.domains ?? []).map(d => d.toLowerCase()) })), [sorted])
  const featured = useMemo(() => {
    const first = FEATURED_FIRST.map(d => index.find(x => x.domains.includes(d))?.t).filter((t): t is Tenant => !!t)
    const ids = new Set(first.map(t => t.id))
    return [...first, ...sorted.filter(t => !ids.has(t.id))].slice(0, FEATURED_COUNT)
  }, [sorted, index])
  const dq = useDeferredValue(q)
  const matches = useMemo(() => {
    const n = norm(dq)
    if (n.length < 2) return []
    // Names that start with the query first, then anywhere in the name or domain; stop as soon as we have enough rows.
    const starts: Tenant[] = [], within: Tenant[] = []
    for (const x of index) {
      if (x.name.startsWith(n) || x.short.startsWith(n)) starts.push(x.t)
      else if (x.name.includes(n) || x.short.includes(n) || x.domains.some(d => d.includes(n))) within.push(x.t)
      if (starts.length > MAX_RESULTS) break
    }
    return [...starts, ...within].slice(0, MAX_RESULTS + 1)
  }, [dq, index])
  const more = Math.max(0, tenants.length - featured.length)

  return (
    <main className="landing">
      <header>
        <h1><img src="/favicon.svg" alt="" />Semester OS</h1>
        <p>Your college chief-of-staff. Connect Blackboard in one click, and get an agent for every class, a calendar that updates itself, a daily plan and your books.</p>
        <div className="hero-actions">
          <Link to="/auth" className="btn-primary">Get started</Link>
          <Link to="/auth?mode=signin" className="btn-ghost">I have an account</Link>
        </div>
      </header>

      <section aria-labelledby="school-h" className="stack">
        <h2 id="school-h">Find your school</h2>
        <div className="school-find">
          <input className="input" type="search" aria-label="Find your school by name or email domain" value={q} autoComplete="off" onChange={e => { setQ(e.target.value); setPicked(null) }} placeholder="Search by school name or email domain, like ua.edu" />
          {loading && <p className="muted" role="status">Loading schools…</p>}
          {dq.trim().length >= 2 && !picked && (
            <ul className="school-results" aria-label="Matching schools">
              {matches.slice(0, MAX_RESULTS).map(t => (
                <li key={t.id}><button type="button" className="campus-badge" style={{ width: '100%', maxWidth: 'none', borderRadius: 'var(--radius)' }} onClick={() => { setPicked(t); setQ(t.name) }}><Tile t={t} /></button></li>
              ))}
              {matches.length === 0 && <li className="muted" style={{ padding: 'var(--s-3)' }}>No school found. Any US college with a .edu email works: sign up and your campus is set up for you.</li>}
              {matches.length > MAX_RESULTS && <li className="muted" style={{ padding: 'var(--s-2) var(--s-3)', fontSize: 'var(--text-sm)' }}>Keep typing to narrow it down.</li>}
            </ul>
          )}
          {picked && (
            <div className="card row" style={{ justifyContent: 'space-between' }}>
              <span className="row" style={{ flexWrap: 'nowrap' }}><span className="campus-badge" style={{ border: 0, background: 'none' }}><Tile t={picked} /></span></span>
              <Link to="/auth" className="btn-primary btn-sm">Sign up with your {picked.domains?.[0] ?? 'school'} email</Link>
            </div>
          )}
        </div>

        {!loading && tenants.length === 0 && <p className="muted">Any US college works: sign up with your .edu email and your campus is set up for you.</p>}
        {featured.length > 0 && (
          <>
            <ul className="campus-chips" aria-label="Featured schools">
              {featured.map(t => <li key={t.id}><button type="button" className="campus-badge" onClick={() => { setPicked(t); setQ(t.name) }}><Tile t={t} /></button></li>)}
            </ul>
            {more > 0 && <p className="muted">and {more} more. Search above, or sign up with your .edu email and we'll find your school.</p>}
          </>
        )}
      </section>
    </main>
  )
}
