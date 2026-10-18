import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage, type Course } from '../lib/api'
import { callTutor, TutorError, type Flashcard, type QuizQuestion } from '../lib/tutor'
import { applyClassTheme } from '../styles/theme'
import { ARCHIVE_CONFIRM, setArchived } from '../lib/archive'
import { classIndexFromHex } from '../styles/color'
import Robot from '../components/Robot'
import ChatPanel from '../components/ChatPanel'
import Quiz from '../components/Quiz'
import FlashDeck from '../components/FlashDeck'
import MaterialsTab from '../components/class/MaterialsTab'
import BlackboardTab from '../components/class/BlackboardTab'
import MemoryTab from '../components/class/MemoryTab'
import TutorsSection from '../components/class/TutorsSection'
import { TUTORS_FOR_CLASS_LIVE } from '../lib/market'
import { useToast } from '../components/Toast'
import { fetchOpening, type Opening } from '../lib/history'

interface Assignment {
  id: string; title: string; type: string; dueDate: string | null; dueTime: string | null
  dueText?: string; dateSource?: 'stated' | 'resolved' | 'manual' | 'feed' | null; weight?: number | null; done: boolean; notes?: string
}
type Tab = 'chat' | 'materials' | 'deadlines' | 'blackboard' | 'books' | 'memory' | 'syllabus'
const TABS: { id: Tab; label: string }[] = [
  { id: 'chat', label: 'Chat' }, { id: 'materials', label: 'Materials' }, { id: 'deadlines', label: 'Deadlines' },
  { id: 'blackboard', label: 'Blackboard' }, { id: 'books', label: 'Books' }, { id: 'memory', label: 'Memory' }, { id: 'syllabus', label: 'Syllabus' },
]
type ChatMode = 'explain' | 'quiz' | 'flashcards' | 'cram'
const MODES: { id: ChatMode; label: string }[] = [
  { id: 'explain', label: 'Explain' }, { id: 'quiz', label: 'Quiz' }, { id: 'flashcards', label: 'Cards' }, { id: 'cram', label: 'Cram' },
]

const daysTo = (iso: string) => Math.floor((new Date(`${iso}T00:00:00`).getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000)
function dueLabel(a: Assignment): string {
  if (!a.dueDate) return a.dueText ? `Date unknown: ${a.dueText}` : 'No date yet'
  const d = new Date(`${a.dueDate}T00:00:00`)
  const day = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  return a.dueTime ? `${day}, ${a.dueTime}` : day
}
const urgency = (a: Assignment): 'soon' | 'overdue' | undefined => {
  if (!a.dueDate || a.done) return undefined
  const d = daysTo(a.dueDate)
  return d < 0 ? 'overdue' : d <= 3 ? 'soon' : undefined
}

interface Chip { label: string; mode: ChatMode; prompt?: string }
/** The agent's first message, computed from the deadlines the student already has (a server-written opening can replace it later). */
function openingFor(course: Course, items: Assignment[]): { text: string; chips: Chip[] } {
  const code = course.courseCode || 'this class'
  const upcoming = items.filter(a => !a.done && a.dueDate && daysTo(a.dueDate) >= 0).sort((a, b) => a.dueDate!.localeCompare(b.dueDate!))
  const big = upcoming.find(a => ['exam', 'quiz', 'project', 'paper'].includes(a.type) && daysTo(a.dueDate!) <= 14)
  const overdue = items.filter(a => !a.done && a.dueDate && daysTo(a.dueDate) < 0).length
  const chips: Chip[] = [{ label: "What's due this week?", mode: 'explain', prompt: `What's due this week in ${code}?` }]
  let text = `Hi, I'm your ${code} agent. I know your syllabus and deadlines. What do you want to work on?`
  if (big) {
    const d = daysTo(big.dueDate!)
    text = `${big.title} is ${d === 0 ? 'today' : d === 1 ? 'tomorrow' : `in ${d} days`}. Want a study plan, or should we practice first?`
    chips.unshift({ label: `Plan for ${big.title}`.slice(0, 40), mode: 'cram', prompt: `Help me make a study plan for ${big.title}.` })
  } else if (overdue > 0) {
    text = `You have ${overdue} overdue item${overdue === 1 ? '' : 's'} in ${code}. Want to sort those out first?`
  }
  chips.push({ label: 'Quiz me', mode: 'quiz' }, { label: 'Make flashcards', mode: 'flashcards' },
    { label: 'How is my grade calculated?', mode: 'explain', prompt: `How is my grade calculated in ${code}, and what matters most?` })
  return { text, chips }
}

export default function ClassPage() {
  const { id = '' } = useParams()
  const goBack = useNavigate()
  // Escape leaves the class agent for the class list (unless a dialog or menu has focus and wants Escape).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return
      goBack('/study')
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [goBack])
  const { authFetch, tenant } = useAuth()
  const { push } = useToast()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [archiveAsk, setArchiveAsk] = useState(false)
  async function archive() {
    const problem = await setArchived(fetchRef.current, id, true)
    if (problem) { push('error', "Couldn't archive the class", problem); return }
    push('success', 'Class hidden', 'Restore it any time in Settings.')
    goBack('/study')
  }
  const [course, setCourse] = useState<Course | null>(null)
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [state, setState] = useState<'loading' | 'ok' | 'missing' | 'error'>('loading')
  const [qs] = useSearchParams()
  const wanted = qs.get('tab') as Tab | null
  const [tab, setTab] = useState<Tab>(wanted && TABS.some(t => t.id === wanted) ? wanted : 'chat')
  const [mode, setMode] = useState<ChatMode>('explain')
  const [auto, setAuto] = useState<{ id: number; text: string } | null>(null)
  const [serverOpening, setServerOpening] = useState<Opening | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await fetchRef.current(`/courses/${id}`)
      if (r.status === 404) { setState('missing'); return }
      if (!r.ok) throw new Error(String(r.status))
      const j = await r.json()
      setCourse(j.course); setAssignments(j.assignments ?? []); setState('ok')
    } catch { setState('error') }
  }, [id])
  useEffect(() => { load() }, [load])
  // Proactive opening message and chips from the server (falls back to the ones computed from deadlines).
  useEffect(() => {
    let alive = true
    fetchOpening(fetchRef.current, id).then(o => { if (alive) setServerOpening(o) })
    return () => { alive = false }
  }, [id])

  // Whole-UI re-theme to the class colour; restore the campus theme on the way out.
  const campusPrimary = tenant?.theme?.primary
  useEffect(() => {
    if (!course) return
    const idx = classIndexFromHex(course.color)
    if (idx >= 0) applyClassTheme(idx, campusPrimary)
    return () => applyClassTheme(null, campusPrimary)
  }, [course?.color, campusPrimary]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (course?.status !== 'BUILDING') return
    const t = window.setTimeout(load, 2000)
    return () => window.clearTimeout(t)
  }, [course, load])

  async function toggleDone(a: Assignment) {
    const done = !a.done
    setAssignments(xs => xs.map(x => (x.id === a.id ? { ...x, done } : x))) // optimistic
    try {
      const r = await fetchRef.current(`/assignments/${a.id}`, { method: 'PATCH', body: JSON.stringify({ done }) })
      if (!r.ok) throw new Error(await errorMessage(r))
    } catch (e) {
      setAssignments(xs => xs.map(x => (x.id === a.id ? { ...x, done: a.done } : x)))
      push('error', "Couldn't update that deadline", e instanceof Error ? e.message : 'Try again.')
    }
  }

  function runChip(c: Chip) {
    setTab('chat'); setMode(c.mode)
    if (c.prompt && (c.mode === 'explain' || c.mode === 'cram')) setAuto({ id: Date.now(), text: c.prompt })
  }

  if (state === 'loading') return <div className="page" aria-busy="true"><div className="skeleton-block" style={{ height: '5rem' }} /><div className="skeleton-block" style={{ height: '20rem' }} /></div>
  if (state === 'missing') return (
    <div className="page"><div className="empty"><Robot name="state-error" size={72} /><div className="empty-title">Class not found</div><p className="empty-body">This class may have been deleted.</p><Link to="/study" className="btn-primary">Back to Study</Link></div></div>
  )
  if (state === 'error' || !course) return (
    <div className="page"><div className="warning" role="alert"><span>We couldn't load this class.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div></div>
  )

  const ready = course.status === 'READY'
  const code = course.courseCode || 'New class'
  const k = course.knows ?? {}
  const sorted = [...assignments].sort((a, b) => (a.dueDate ?? '9999').localeCompare(b.dueDate ?? '9999'))
  const dated = sorted.filter(a => a.dueDate)
  const undated = sorted.filter(a => !a.dueDate)
  const computed = openingFor(course, assignments)
  const opening = serverOpening && serverOpening.chips.length ? { text: serverOpening.message, chips: serverOpening.chips as Chip[] } : computed

  return (
    <div className="page">
      <div>
        <div className="class-back"><Link to="/study" className="btn-ghost btn-sm" aria-label="Back to Study, all your classes">← Study</Link><span className="muted class-back-hint">Esc to go back</span></div>
        <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'center' }}>
          <Robot name={ready ? 'class-tutor' : course.status === 'ERROR' ? 'state-error' : 'state-building'} size={64} />
          <div className="grow">
            <span className="eyebrow">{course.term || 'Class agent'}</span>
            <h1 className="truncate">{code}{course.title ? ` · ${course.title}` : ''}</h1>
            <p className="muted">{course.instructor}</p>
          </div>
          <span className="badge" data-status={course.status.toLowerCase()}>{ready ? 'Ready' : course.status === 'BUILDING' ? 'Building' : 'Error'}</span>
          {archiveAsk ? (
            <span className="row" role="group" aria-label="Archive this class"><span className="muted" style={{ fontSize: 'var(--text-sm)' }}>{ARCHIVE_CONFIRM}</span><button type="button" className="btn-primary btn-sm" onClick={archive}>Hide class</button><button type="button" className="btn-ghost btn-sm" onClick={() => setArchiveAsk(false)}>Keep</button></span>
          ) : <button type="button" className="btn-ghost btn-sm" onClick={() => setArchiveAsk(true)}>Archive</button>}
        </div>
        {ready && (
          <div className="chip-row" style={{ marginTop: 'var(--s-3)' }} aria-label="What this agent knows">
            <span className="chip">{k.assignmentsCount ?? assignments.length} deadlines</span>
            <span className="chip">{k.materialsCount ?? 0} materials</span>
            {course.courseCode && <Link to={`/messages?code=${encodeURIComponent(course.courseCode)}`} className="chip" style={{ textDecoration: 'none' }}>Class chat</Link>}
            {(k.newItemsCount ?? 0) > 0 && <span className="badge badge-count">{k.newItemsCount} new from Blackboard</span>}
          </div>
        )}
      </div>

      {!ready ? (
        <div className="card stack">
          <strong>{course.status === 'ERROR' ? "We couldn't build this class" : 'Your class agent is still being built'}</strong>
          {course.status === 'ERROR' && <p className="field-error" role="alert">{course.error}</p>}
          <ol className="stepper" aria-label="Build progress">
            {course.pipeline.map(s => <li key={s.key} className="step" data-state={s.state}><span className="step-dot" /><span>{s.label}{s.detail ? <span className="step-detail">{s.detail}</span> : null}</span></li>)}
          </ol>
        </div>
      ) : (
        <>
          <div className="tabs" role="tablist" aria-label={`${code} agent`}>
            {TABS.map(t => <button key={t.id} role="tab" type="button" className="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} onClick={() => setTab(t.id)}>{t.label}</button>)}
          </div>
          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="stack">
            {tab === 'chat' && (
              <>
                <div className="segmented" role="group" aria-label="Mode" style={{ alignSelf: 'flex-start' }}>
                  {MODES.map(m => <button key={m.id} type="button" aria-pressed={mode === m.id} onClick={() => setMode(m.id)}>{m.label}</button>)}
                </div>
                {mode === 'explain' && <ChatPanel key="explain" courseId={id} mode="explain" storageKey={`chat:explain:${id}`} onChanged={load} agentName={`${code} agent`} autoSend={auto}
                  placeholder={`Ask about ${code}…`} intro={`Hi, I'm your ${code} agent. How can I help?`} />}
                {mode === 'cram' && <ChatPanel key="cram" courseId={id} mode="cram" storageKey={`chat:cram:${id}`} onChanged={load} agentName={`${code} agent`} autoSend={auto}
                  placeholder="Which exam are you cramming for?" confirmLabel="Put these study blocks in my calendar"
                  intro="Tell me which exam is coming and how many days you have. I'll draft a day-by-day plan, and add study blocks only after you confirm." />}
                {mode === 'quiz' && <QuizTab courseId={id} />}
                {mode === 'flashcards' && <CardsTab courseId={id} />}
              </>
            )}

            {tab === 'materials' && <MaterialsTab courseId={id} courseCode={code} />}

            {tab === 'deadlines' && (
              <div className="stack" style={{ gap: 'var(--s-2)' }}>
                {assignments.length === 0 && <div className="empty"><div className="empty-title">No deadlines found</div><p className="empty-body">The syllabus didn't list any dated work.</p></div>}
                {dated.map(a => <DeadlineRow key={a.id} a={a} onToggle={toggleDone} />)}
                {undated.length > 0 && <div className="undated stack" style={{ gap: 'var(--s-2)' }}><span className="eyebrow">Needs a date</span>{undated.map(a => <DeadlineRow key={a.id} a={a} onToggle={toggleDone} />)}</div>}
              </div>
            )}

            {tab === 'blackboard' && <BlackboardTab courseId={id} courseCode={code} onChanged={load} />}

            {tab === 'books' && <><BooksList course={course} />{TUTORS_FOR_CLASS_LIVE && <TutorsSection courseId={id} courseCode={code} />}</>}

            {tab === 'memory' && <MemoryTab courseId={id} courseCode={code} />}

            {tab === 'syllabus' && (
              <section className="window">
                <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">syllabus</span></div>
                <div className="window-body stack">{course.summary && <p>{course.summary}</p>}<Facts course={course} /></div>
              </section>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function DeadlineRow({ a, onToggle }: { a: Assignment; onToggle: (a: Assignment) => void }) {
  const u = urgency(a)
  return (
    <div className="agenda-item" data-done={a.done} data-estimated={a.dateSource === 'resolved'}>
      <input type="checkbox" checked={a.done} onChange={() => onToggle(a)} aria-label={`Mark ${a.title} ${a.done ? 'not done' : 'done'}`} />
      <div className="grow">
        <div className="agenda-title">{a.title}</div>
        <div className="agenda-note">
          <span className="chip-due" data-urgency={u}>{a.dateSource === 'resolved' ? '~ ' : ''}{dueLabel(a)}</span>
          {a.dateSource === 'resolved' && <span> · estimated, confirm with your professor</span>}
          {a.dateSource === 'feed' && <span> · from Blackboard</span>}
          {a.weight ? <span> · {a.weight}%</span> : null}
        </div>
      </div>
      <span className="chip chip-outline">{a.type}</span>
    </div>
  )
}

function BooksList({ course }: { course: Course & { books?: { title: string; author?: string; edition?: string; required?: boolean }[] } }) {
  const books = course.books ?? []
  if (books.length === 0) return <div className="empty"><div className="empty-title">No books in this syllabus</div><p className="empty-body">If your instructor uses a book that isn't listed, you can still look for it in the marketplace.</p><Link to="/marketplace" className="btn-primary">Open Books</Link></div>
  return (
    <div className="stack">
      {books.map((b, i) => (
        <div key={i} className="listing" style={{ gridTemplateColumns: '1fr auto' }}>
          <div><strong>{b.title}</strong><div className="muted" style={{ fontSize: 'var(--text-sm)' }}>{[b.author, b.edition].filter(Boolean).join(' · ')}</div></div>
          <span className={`badge ${b.required ? '' : 'badge-info'}`}>{b.required ? 'Required' : 'Optional'}</span>
        </div>
      ))}
      <Link to="/marketplace" className="btn-primary" style={{ alignSelf: 'flex-start' }}>Find these on the marketplace</Link>
    </div>
  )
}

function Facts({ course }: { course: Course & { officeHours?: string; grading?: { item: string; percent: number }[]; policies?: Record<string, string> } }) {
  const grading = course.grading ?? []
  const pol = course.policies ?? {}
  return (
    <>
      {course.officeHours && <div><span className="eyebrow">Office hours</span><p>{course.officeHours}</p></div>}
      {grading.length > 0 && (
        <div>
          <span className="eyebrow">Grading</span>
          <ul className="stack" style={{ gap: 'var(--s-2)', marginTop: 'var(--s-2)' }}>
            {grading.map((g, i) => (
              <li key={i}>
                <div className="row" style={{ justifyContent: 'space-between' }}><span>{g.item}</span><span className="mono">{g.percent}%</span></div>
                <div className="progress" style={{ ['--value' as string]: `${Math.min(100, g.percent)}%` }}><i /></div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {pol.ai && <div className="quiz-explain"><strong>AI policy.</strong> {pol.ai}</div>}
      {(['late', 'attendance', 'other'] as const).map(k => pol[k] ? <div key={k}><span className="eyebrow">{k === 'late' ? 'Late work' : k === 'attendance' ? 'Attendance' : 'Other policies'}</span><p>{pol[k]}</p></div> : null)}
    </>
  )
}

function useGenerator<T>(courseId: string, mode: 'quiz' | 'flashcards', pick: (r: Awaited<ReturnType<typeof callTutor>>) => T | null) {
  const { authFetch } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [data, setData] = useState<T | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function run(topic: string, count: number) {
    setBusy(true); setError(null)
    try {
      const res = await callTutor(fetchRef.current, courseId, { mode, topic: topic.trim() || undefined, count })
      const out = pick(res)
      if (!out) throw new TutorError("I couldn't make that. Try again.")
      setData(out)
    } catch (e) {
      setError(e instanceof TutorError ? e.message : 'Something went wrong. Try again.')
    } finally { setBusy(false) }
  }
  return { data, setData, busy, error, run }
}

function StartForm({ label, busy, error, onRun, min, max, def }: { label: string; busy: boolean; error: string | null; onRun: (topic: string, count: number) => void; min: number; max: number; def: number }) {
  const [topic, setTopic] = useState('')
  const [count, setCount] = useState(def)
  return (
    <form className="card stack" onSubmit={e => { e.preventDefault(); onRun(topic, count) }}>
      <div className="field"><label htmlFor="topic">Topic (optional)</label><input id="topic" value={topic} maxLength={120} onChange={e => setTopic(e.target.value)} placeholder="Leave blank to cover the whole class" /></div>
      <div className="field"><label htmlFor="count">How many?</label><input id="count" type="number" min={min} max={max} value={count} onChange={e => setCount(Math.max(min, Math.min(max, Number(e.target.value) || def)))} /></div>
      {error && <p className="field-error" role="alert">{error}</p>}
      <button type="submit" className="btn-primary" style={{ alignSelf: 'flex-start' }} disabled={busy} aria-busy={busy}>{busy ? 'Making it…' : label}</button>
    </form>
  )
}

function QuizTab({ courseId }: { courseId: string }) {
  const g = useGenerator<QuizQuestion[]>(courseId, 'quiz', r => r.quiz?.questions ?? null)
  if (g.data) return <Quiz questions={g.data} onDone={() => g.setData(null)} />
  return <StartForm label="Start quiz" busy={g.busy} error={g.error} onRun={g.run} min={3} max={10} def={5} />
}

function CardsTab({ courseId }: { courseId: string }) {
  const g = useGenerator<Flashcard[]>(courseId, 'flashcards', r => r.flashcards?.cards ?? null)
  if (g.data) return <FlashDeck cards={g.data} courseId={courseId} onDone={() => g.setData(null)} />
  return <StartForm label="Make flashcards" busy={g.busy} error={g.error} onRun={g.run} min={5} max={20} def={10} />
}
