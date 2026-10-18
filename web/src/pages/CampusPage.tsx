import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useCourses } from '../lib/useCourses'
import Robot from '../components/Robot'

interface Resource { name: string; description?: string; url?: string }

/** https only: a campus resource link from data is never trusted to be safe. */
const safeHref = (u?: string) => { try { const x = new URL(u ?? ''); return x.protocol === 'https:' ? x.href : null } catch { return null } }

const LMS: Record<string, string> = {
  ical_feed: 'Calendar feed', pending_admin_approval: 'Waiting for school approval', none: 'Not connected',
}

export default function CampusPage() {
  const { tenant, profile } = useAuth()
  const { courses } = useCourses()
  const [slow, setSlow] = useState(false)
  useEffect(() => { const t = window.setTimeout(() => setSlow(true), 8000); return () => window.clearTimeout(t) }, [])

  if (!tenant) return slow
    ? <div className="page"><div className="warning" role="alert"><span>We couldn't load your school. Check your connection and refresh the page.</span></div></div>
    : <div className="page" aria-busy="true"><div className="skeleton-block" style={{ height: '10rem' }} /><div className="skeleton-block" style={{ height: '14rem' }} /></div>

  const tutoring: Resource[] = Array.isArray(tenant.tutoringResources) ? tenant.tutoringResources : []
  const spots: string[] = Array.isArray(tenant.pickupSpots) ? tenant.pickupSpots : []
  const categories: string[] = Array.isArray(tenant.categories) ? tenant.categories : []
  const domains: string[] = Array.isArray(tenant.domains) ? tenant.domains : []
  const lms = LMS[tenant.lms?.connector as string] ?? 'Not connected'
  const ready = courses.find(c => c.status === 'READY')
  const hasClasses = courses.length > 0

  const steps = [
    { done: hasClasses, title: 'Add your classes', note: 'Drop in your syllabi and each class gets its own tutor.', to: '/onboarding', cta: hasClasses ? 'Add another' : 'Add classes' },
    { done: false, title: 'Subscribe to your calendar', note: 'See every deadline in Google, Apple or Outlook calendar.', to: '/calendar', cta: 'Set up' },
    { done: false, title: 'Try your first study session', note: ready ? `Open your ${ready.courseCode || 'class'} tutor.` : 'Available once a class finishes building.', to: ready ? `/study/${ready.id}` : '/study', cta: ready ? 'Open tutor' : 'See agents' },
  ]

  return (
    <div className="page">
      <section className="campus-hero" aria-label="Your school">
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <Robot name="chief-of-staff" size={64} />
          <div className="grow">
            <span className="eyebrow">Your campus</span>
            <h1 className="campus-name">{tenant.name}</h1>
          </div>
        </div>
        <div className="campus-meta">
          {tenant.shortName && <span className="badge">{tenant.shortName}</span>}
          {domains.map(d => <span key={d} className="chip chip-outline mono">{d}</span>)}
          {tenant.autoCreated && <span className="badge badge-info">Auto-created</span>}
        </div>
        {(tenant.colorStatus === 'placeholder' || tenant.colorStatus === 'needs_review' || (tenant.autoCreated && !tenant.colorStatus)) && (
          <p className="campus-note" role="note">{tenant.colorStatus === 'needs_review' ? "Your school's colour is waiting for a quick review." : "Your school's colour is a placeholder until it's verified. Everything works the same."}</p>
        )}
        {profile?.displayName && <p className="muted">Signed in as {profile.displayName}</p>}
      </section>

      <section aria-labelledby="setup-h">
        <div className="section-head"><h2 id="setup-h">What's set up</h2></div>
        <div className="config-grid">
          <div className="config-item" data-state="set">
            <h3>Time zone <span className="badge badge-ok">Set</span></h3>
            <p className="config-value mono">{tenant.timezone ?? 'Not set'}</p>
            <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>Your briefings and deadlines use this.</p>
          </div>

          <div className="config-item" data-state="set">
            <h3>Class calendar link <span className="badge">{lms}</span></h3>
            <p className="config-value">Connect your Blackboard calendar feed to keep deadlines up to date. Coming soon in Settings.</p>
          </div>

          <div className="config-item" data-state={tutoring.length ? 'set' : 'empty'}>
            <h3>Tutoring {tutoring.length ? <span className="badge badge-ok">{tutoring.length}</span> : <span className="badge badge-warn">Not set up yet</span>}</h3>
            {tutoring.length ? (
              <ul className="config-list">
                {tutoring.map((r, i) => {
                  const href = safeHref(r.url)
                  return <li key={i}><strong>{r.name}</strong>{r.description ? <div className="muted">{r.description}</div> : null}{href && <a href={href} target="_blank" rel="noopener noreferrer">Visit site</a>}</li>
                })}
              </ul>
            ) : <p className="config-value">No tutoring resources yet. Your school's admin can add them.</p>}
          </div>

          <div className="config-item" data-state={spots.length ? 'set' : 'empty'}>
            <h3>Pickup spots {spots.length ? <span className="badge badge-ok">{spots.length}</span> : <span className="badge badge-warn">Not set up yet</span>}</h3>
            {spots.length ? <ul className="config-list">{spots.map(s => <li key={s}>{s}</li>)}</ul>
              : <p className="config-value">No campus meetup spots yet. Until then, meet in a public, well-lit place.</p>}
          </div>

          <div className="config-item" data-state="set">
            <h3>Marketplace <span className="badge badge-ok">{tenant.openToNetwork ? 'Open to other campuses' : 'Campus only'}</span></h3>
            {categories.length > 0 && <div className="chip-row">{categories.map(c => <span key={c} className="chip chip-outline">{c}</span>)}</div>}
            <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>Every listing shows which campus it's from.</p>
          </div>
        </div>
      </section>

      <section aria-labelledby="next-h">
        <div className="section-head"><h2 id="next-h">Next steps</h2></div>
        <ol className="next-steps">
          {steps.map(s => (
            <li key={s.title} className="next-step" data-done={s.done}>
              <div><div className="next-title">{s.title}</div><div className="muted" style={{ fontSize: 'var(--text-sm)' }}>{s.note}</div></div>
              <Link to={s.to} className={s.done ? 'btn-ghost btn-sm' : 'btn-primary btn-sm'}>{s.cta}</Link>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
