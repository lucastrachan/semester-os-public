import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useCourses } from '../lib/useCourses'
import { timeAgo, errorMessage, type ActivityItem, type Course } from '../lib/api'
import { classIndexFromHex } from '../styles/color'
import Robot, { type RobotName } from '../components/Robot'
import AddClass from '../components/AddClass'
import { ARCHIVE_CONFIRM, setArchived } from '../lib/archive'
import { useToast } from '../components/Toast'

interface Resource { name: string; description?: string; url?: string }
/** https only: a link from campus data is never trusted to be safe. */
const safeHref = (u?: string) => { try { const x = new URL(u ?? ''); return x.protocol === 'https:' ? x.href : null } catch { return null } }

const STATUS_LABEL: Record<string, string> = { BUILDING: 'Building', READY: 'Ready', ERROR: 'Error' }

function themeOf(color: string): string | undefined {
  const i = classIndexFromHex(color)
  return i >= 0 ? `c${i}` : undefined
}

/** Opens the general agent (command palette) from anywhere. AppShell listens for this event. */
export const openGeneralAgent = () => window.dispatchEvent(new CustomEvent('semester:open-chat'))

function ClassAgentCard({ course, onPaste, onDelete, onArchive }: { course: Course; onPaste: () => void; onDelete: (id: string) => void; onArchive: (id: string) => void }) {
  const [confirming, setConfirming] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const name = course.courseCode || 'New class'
  const robot: RobotName = course.status === 'BUILDING' ? 'state-building' : course.status === 'ERROR' ? 'state-error' : 'class-tutor'
  const k = course.knows ?? {}
  const kx = k as { lastFeedCheckAt?: string | null; lastUpdatedAt?: string | null }
  const showSteps = course.status !== 'READY' && course.pipeline?.length > 0
  return (
    <article className="window agent-card" data-theme={themeOf(course.color)} aria-label={`${name} agent`}>
      <div className="agent-swatch" />
      <div className="window-bar">
        <span className="window-dots" aria-hidden="true"><i /><i /><i /></span>
        <span className="window-title">{(course.courseCode || 'new-class').toLowerCase().replace(/\s+/g, '')}.agent</span>
        <span className="badge" data-status={course.status.toLowerCase()}>{STATUS_LABEL[course.status] ?? course.status}</span>
      </div>
      <div className="window-body">
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <Robot name={robot} size={56} />
          <div className="grow">
            <div className="agent-name truncate">{name}</div>
            <div className="agent-role">{course.title || (course.status === 'BUILDING' ? 'Reading your syllabus…' : '')}{course.instructor ? ` · ${course.instructor}` : ''}</div>
          </div>
        </div>

        {showSteps && (
          <ol className="stepper" aria-label="Build progress">
            {course.pipeline.map(s => (
              <li key={s.key} className="step" data-state={s.state}>
                <span className="step-dot" />
                <span>{s.label}{s.detail ? <span className="step-detail">{s.detail}</span> : null}</span>
              </li>
            ))}
          </ol>
        )}

        {course.status === 'READY' && course.needsSyllabus && <div className="campus-note row" role="note" style={{ justifyContent: 'space-between' }}><span>Add the syllabus for books, grading and policies.</span><Link to={`/study/${course.id}?tab=materials`} className="btn-ghost btn-sm">Add syllabus</Link></div>}

        {course.status === 'ERROR' && <p className="field-error" role="alert">{course.error || "We couldn't build this class."}</p>}

        {course.status === 'READY' && (
          <>
            <div className="knows" aria-label="What this agent knows">
              <div><b>{k.assignmentsCount ?? 0}</b><span>deadlines</span></div>
              <div><b>{k.materialsCount ?? 0}</b><span>materials</span></div>
              <div><b>{k.newItemsCount ?? 0}</b><span>new from Blackboard</span></div>
            </div>
            <div className="agent-meta">
              {kx.lastFeedCheckAt ? `Checked Blackboard ${timeAgo(kx.lastFeedCheckAt)}` : 'Blackboard not connected'}
              {kx.lastUpdatedAt ? ` · updated ${timeAgo(kx.lastUpdatedAt)}` : ''}
            </div>
          </>
        )}

        <div className="row" style={{ marginTop: 'auto' }}>
          <Link to={`/study/${course.id}`} className={`${course.status === 'READY' ? 'btn-primary' : 'btn-ghost'} btn-sm stretch`}>{course.status === 'READY' ? 'Open agent' : course.status === 'BUILDING' ? 'View progress' : 'Details'}</Link>
          {course.status === 'ERROR' && <button type="button" className="btn-ghost btn-sm" onClick={onPaste}>Paste text instead</button>}
          {archiving ? (
            <>
              <span className="muted" style={{ flexBasis: '100%', fontSize: 'var(--text-sm)' }}>{ARCHIVE_CONFIRM}</span>
              <button type="button" className="btn-primary btn-sm" onClick={() => onArchive(course.id)}>Hide class</button>
              <button type="button" className="btn-ghost btn-sm" onClick={() => setArchiving(false)}>Keep</button>
            </>
          ) : confirming ? (
            <>
              <button type="button" className="btn-danger btn-sm" onClick={() => onDelete(course.id)}>Yes, delete</button>
              <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirming(false)}>Keep</button>
            </>
          ) : (
            <>
              <button type="button" className="btn-ghost btn-sm" onClick={() => setArchiving(true)} aria-label={`Archive ${name}`}>Archive</button>
              <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirming(true)} aria-label={`Delete ${name}`}>Delete</button>
            </>
          )}
        </div>
      </div>
    </article>
  )
}

export default function StudyPage() {
  const { authFetch, user, tenant } = useAuth()
  const resources: Resource[] = Array.isArray(tenant?.tutoringResources) ? tenant.tutoringResources : []
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch // authFetch is a new function every render: never put it in effect deps
  const { push } = useToast()
  const { courses, loading, error, reload } = useCourses()
  const [adding, setAdding] = useState(false)
  const [startTab, setStartTab] = useState<'pdf' | 'text'>('pdf')
  const [activity, setActivity] = useState<ActivityItem[]>([])

  useEffect(() => {
    if (!user) return
    let alive = true
    ;(async () => {
      try {
        const r = await fetchRef.current('/activity?limit=15')
        if (r.ok) { const j = await r.json(); if (alive) setActivity(Array.isArray(j.activity) ? j.activity : []) }
      } catch { /* no activity yet */ }
    })()
    return () => { alive = false }
  }, [user, courses.length])

  async function deleteCourse(id: string) {
    try {
      const r = await fetchRef.current(`/courses/${id}`, { method: 'DELETE' })
      if (!r.ok) { push('error', "Couldn't delete the class", await errorMessage(r)); return }
      push('success', 'Class deleted')
      reload()
    } catch { push('error', "Couldn't delete the class", 'Network problem. Try again.') }
  }

  async function archiveCourse(id: string) {
    const problem = await setArchived(fetchRef.current, id, true)
    if (problem) { push('error', "Couldn't archive the class", problem); return }
    push('success', 'Class hidden', 'Restore it any time in Settings.')
    reload()
  }

  const openAdd = (tab: 'pdf' | 'text') => { setStartTab(tab); setAdding(true) }
  const themeFor = (agentId: string) => { const c = courses.find(x => x.id === agentId); return c ? themeOf(c.color) : undefined }

  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">Study</span>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h1>Your class agents</h1>
          {!adding && <div className="row"><Link to="/onboarding" className="btn-primary">Connect Blackboard</Link><button type="button" className="btn-ghost" onClick={() => openAdd('text')}>Add a class with a syllabus</button></div>}
        </div>
        <p>Every class has its own agent with its own memory, materials, deadlines and Blackboard checks.</p>
      </div>

      {adding && <AddClass key={startTab} startTab={startTab} onAdded={reload} onClose={() => setAdding(false)} />}

      {error && (
        <div className="warning" role="alert">
          <span>{error}</span>
          <button type="button" className="btn-ghost-sm" onClick={reload}>Try again</button>
        </div>
      )}

      {courses.length > 0 && courses.every(c => c.status === 'READY') && courses.length <= 2 && (
        <p className="campus-note" role="note">Your {courses.length === 1 ? 'agent is' : 'agents are'} ready. Open one and try asking: “What's due this week?”, or tap Quiz me.</p>
      )}

      <section className="window" aria-label="General agent">
        <div className="window-body row" style={{ flexWrap: 'nowrap' }}>
          <Robot name="chief-of-staff" size={64} />
          <div className="grow">
            <div className="agent-name">Chief of Staff</div>
            <div className="agent-role">Your general help agent. Ask about your day, or mention a class and I'll bring you to its agent with the material.</div>
          </div>
          <div className="stack" style={{ gap: 'var(--s-2)', alignItems: 'flex-end' }}>
            <button type="button" className="btn-primary btn-sm" onClick={openGeneralAgent}>Ask now</button>
            <Link to="/today" className="btn-ghost btn-sm">Today</Link>
          </div>
        </div>
      </section>

      <section aria-labelledby="classes-h">
        <div className="section-head"><h2 id="classes-h">Class agents</h2></div>
        {loading ? (
          <div className="agent-grid" aria-busy="true" aria-label="Loading classes">
            {[0, 1].map(i => <div key={i} className="skeleton-block" style={{ height: '14rem' }} />)}
          </div>
        ) : courses.length === 0 ? (
          <div className="empty">
            <Robot name="base" size={72} />
            <div className="empty-title">No class agents yet</div>
            <p className="empty-body">Connect Blackboard and the Semester OS helper builds a class agent for each of your classes in one click, with its deadlines. Each agent has its own tutor, memory and books.</p>
            <Link to="/onboarding" className="btn-primary">Connect Blackboard</Link>
            <button type="button" className="link-btn" onClick={() => openAdd('text')}>Or add one class with its syllabus (or try a sample)</button>
          </div>
        ) : (
          <div className="agent-grid">
            {courses.map(c => <ClassAgentCard key={c.id} course={c} onPaste={() => openAdd('text')} onDelete={deleteCourse} onArchive={archiveCourse} />)}
          </div>
        )}
      </section>

      <section aria-labelledby="help-h">
        <div className="section-head"><h2 id="help-h">Campus help{tenant?.shortName ? ` at ${tenant.shortName}` : ''}</h2><Link to="/marketplace" className="btn-ghost btn-sm">Find a peer tutor</Link></div>
        {resources.length === 0 ? (
          <div className="config-item" data-state="empty">
            <h3>No campus help listed yet <span className="badge badge-warn">Not set up yet</span></h3>
            <p className="config-value">Your school's admin can add tutoring centers and help desks. Until then, ask your instructor, or look for a peer tutor in the marketplace.</p>
          </div>
        ) : (
          <div className="config-grid">
            {resources.map((r, i) => {
              const href = safeHref(r.url)
              return (
                <div key={i} className="config-item" data-state="set">
                  <h3>{r.name}</h3>
                  {r.description && <p className="config-value">{r.description}</p>}
                  {href && <a className="btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} href={href} target="_blank" rel="noopener noreferrer">Visit {new URL(href).hostname}</a>}
                </div>
              )
            })}
          </div>
        )}
      </section>

      {activity.length > 0 && (
        <section className="window" aria-label="Recent activity">
          <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">activity</span></div>
          <div className="window-body">
            <div className="activity">
              {activity.map(a => (
                <div key={a.id} className="activity-item" data-theme={themeFor(a.agentId)}>
                  <span className="activity-dot" aria-hidden="true" />
                  <span>{a.text}</span>
                  <span className="activity-time">{timeAgo(a.at)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
