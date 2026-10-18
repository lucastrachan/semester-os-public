import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useCourses } from '../lib/useCourses'
import { getBriefing, type BriefingResponse } from '../lib/master'
import { TutorError } from '../lib/tutor'
import { classIndexFromHex } from '../styles/color'
import type { Course } from '../lib/api'
import { NamePrompt } from '../components/NameCard'
import { MyAvatar } from '../components/Avatar'
import { greetName } from '../lib/name'
import Robot from '../components/Robot'
import { useToast } from '../components/Toast'

const themeOf = (c?: Course) => {
  const i = c ? classIndexFromHex(c.color) : -1
  return i >= 0 ? `c${i}` : undefined
}
const daysUntil = (iso: string) => Math.floor((new Date(`${iso}T00:00:00`).getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000)
const dueText = (iso: string) => {
  const d = daysUntil(iso)
  if (d < 0) return `Overdue · ${-d}d`
  if (d === 0) return 'Today'
  if (d === 1) return 'Tomorrow'
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

interface Block { key: string; start: string; label: string; sub: string; kind: 'class' | 'study'; course?: Course }

export default function TodayPage() {
  const { authFetch, profile, tenant, user } = useAuth()
  const { push } = useToast()
  const { courses, loading: coursesLoading } = useCourses()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [data, setData] = useState<BriefingResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [regen, setRegen] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  const load = useCallback(async () => {
    try { setData(await getBriefing(fetchRef.current)); setFailed(false) }
    catch { setFailed(true) }
    finally { setLoading(false) }
  }, [])
  const anyReady = courses.some(c => c.status === 'READY')
  useEffect(() => { if (user && anyReady) load() }, [user, anyReady, load])
  useEffect(() => {
    if (cooldown <= 0) return
    const t = window.setTimeout(() => setCooldown(c => c - 1), 1000)
    return () => window.clearTimeout(t)
  }, [cooldown])

  async function regenerate() {
    setRegen(true)
    try { setData(await getBriefing(fetchRef.current, true)) }
    catch (e) {
      const err = e instanceof TutorError ? e : new TutorError('Try again in a moment.')
      push('error', "Couldn't refresh your briefing", err.message)
      if (err.retryAfter) setCooldown(Math.min(err.retryAfter, 120))
    } finally { setRegen(false) }
  }

  const byId = (id: string) => courses.find(c => c.id === id)
  const first = greetName(profile)
  const hr = new Date().getHours()
  const hello = hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening'
  const b = data?.briefing

  const blocks: Block[] = []
  if (b && data) {
    b.classesToday.forEach((c, i) => {
      const course = byId(c.courseId)
      blocks.push({ key: `c${i}`, start: c.time.split('-')[0], label: course?.courseCode ? `${course.courseCode} · ${course.title}` : 'Class', sub: [c.time, c.location].filter(Boolean).join(' · '), kind: 'class', course })
    })
    b.suggestedStudyBlocks.filter(s => s.start.startsWith(data.date)).forEach((s, i) => {
      const course = byId(s.courseId)
      blocks.push({ key: `s${i}`, start: s.start.slice(11, 16), label: `Study: ${course?.courseCode ?? 'class'}`, sub: `${s.start.slice(11, 16)}-${s.end.slice(11, 16)}${s.focus ? ` · ${s.focus}` : ''}`, kind: 'study', course })
    })
    blocks.sort((x, y) => x.start.localeCompare(y.start))
  }

  const noClasses = !coursesLoading && courses.length === 0
  const buildingOnly = !coursesLoading && courses.length > 0 && !anyReady

  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">{tenant?.name ?? 'Today'}{data ? ` · ${data.date}` : ''}</span>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="row" style={{ flexWrap: 'nowrap', gap: 'var(--s-3)' }}><MyAvatar size={44} /><h1>{b?.greeting ? 'Today' : first ? `${hello}, ${first}` : hello}</h1></div>
          {!noClasses && !buildingOnly && <button type="button" className="btn-ghost btn-sm" onClick={regenerate} disabled={regen || cooldown > 0} aria-busy={regen}>{cooldown > 0 ? `Refresh in ${cooldown}s` : 'Refresh briefing'}</button>}
        </div>
      </div>

      <NamePrompt />

      {noClasses ? (
        <div className="empty">
          <Robot name="chief-of-staff" size={72} />
          <div className="empty-title">Connect Blackboard to get started</div>
          <p className="empty-body">One click builds a class agent for each of your classes, with its deadlines. Your briefing shows up here.</p>
          <Link to="/onboarding" className="btn-primary">Connect Blackboard</Link>
        </div>
      ) : buildingOnly ? (
        <div className="empty">
          <Robot name="state-building" size={72} />
          <div className="empty-title">Your class agents are getting ready</div>
          <p className="empty-body">They're reading your syllabus. Your first briefing appears here in a minute.</p>
          <Link to="/study" className="btn-primary">Watch them build</Link>
        </div>
      ) : loading ? (
        <div className="stack" aria-busy="true" aria-label="Loading your briefing"><div className="skeleton-briefing" /><div className="skeleton-block" /></div>
      ) : failed || !b ? (
        <div className="warning" role="alert"><span>We couldn't load your briefing.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div>
      ) : (
        <section className="window" aria-label="Morning briefing">
          <div className="window-bar">
            <span className="window-dots" aria-hidden="true"><i /><i /><i /></span>
            <span className="window-title">chief-of-staff — briefing</span>
            <span className="badge" data-status="ready">Ready</span>
          </div>
          <div className="window-body briefing">
            <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
              <Robot name="chief-of-staff" size={56} />
              <p className="briefing-greeting">{b.greeting}</p>
            </div>
            {data?.source === 'computed' && <p className="muted">Basic briefing: the AI summary is paused, so this is built from your calendar only.</p>}

            <div className="briefing-grid">
              <div className="briefing-block">
                <h3>Your day</h3>
                {blocks.length === 0 ? <p className="muted">No classes today. A good day to get ahead.</p> : (
                  <div className="timeline">
                    {blocks.map(bl => (
                      <div key={bl.key} className="tl-item">
                        <span className="tl-time">{bl.start}</span>
                        <div className="tl-block" data-theme={themeOf(bl.course)} data-kind={bl.kind}>
                          <span className="tl-title">{bl.label}</span>
                          <span className="tl-sub">{bl.sub}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {b.classesToday.some(c => (c.prep ?? []).length > 0) && (
                  <div className="stack" style={{ gap: 'var(--s-2)', marginTop: 'var(--s-3)' }}>
                    {b.classesToday.map((c, i) => (c.prep ?? []).length > 0 && (
                      <div key={i} className="chip-row" data-theme={themeOf(byId(c.courseId))}>
                        {c.prep!.map((p, k) => <span key={k} className="chip">{p}</span>)}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="briefing-block">
                <h3>Priorities</h3>
                {b.priorities.length === 0 ? <p className="muted">Nothing urgent. Nice.</p> : <ol className="priority-list">{b.priorities.map((p, i) => <li key={i}>{p}</li>)}</ol>}
                {b.warnings.length > 0 && (
                  <div className="stack" style={{ gap: 'var(--s-2)', marginTop: 'var(--s-3)' }}>
                    {b.warnings.map((w, i) => <div key={i} className="warning" role="note">{w}</div>)}
                  </div>
                )}
              </div>
            </div>

            <div className="briefing-block">
              <h3>Due soon</h3>
              {b.dueSoon.length === 0 ? <p className="muted">Nothing due in the next week.</p> : (
                <div className="stack" style={{ gap: 'var(--s-2)' }}>
                  {b.dueSoon.map(d => {
                    const c = byId(d.courseId)
                    const left = daysUntil(d.dueDate)
                    return (
                      <div key={d.assignmentId} className="agenda-item" data-theme={themeOf(c)}>
                        <span className="agenda-time">{c?.courseCode ?? ''}</span>
                        <div className="grow"><div className="agenda-title">{d.title}</div>{d.hint && <div className="agenda-note">{d.hint}</div>}</div>
                        <span className="chip chip-due" data-urgency={left < 0 ? 'overdue' : left <= 3 ? 'soon' : undefined}>{dueText(d.dueDate)}</span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {!noClasses && !buildingOnly && (
        <section className="card row ask-bar" aria-label="Ask your Chief of Staff" style={{ justifyContent: 'space-between' }}>
          <span><strong>Need something planned or explained?</strong> <span className="muted">Ask your Chief of Staff. It hands you to the right class agent.</span></span>
          <button type="button" className="btn-primary" onClick={() => window.dispatchEvent(new CustomEvent('semester:open-chat'))}>Ask</button>
        </section>
      )}
    </div>
  )
}
