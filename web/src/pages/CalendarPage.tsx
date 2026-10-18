import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { useCourses } from '../lib/useCourses'
import { classIndexFromHex } from '../styles/color'
import { useToast } from '../components/Toast'
import Robot from '../components/Robot'
import UnassignedInbox from '../components/UnassignedInbox'

interface Item {
  id: string; courseId: string; courseCode: string; courseColor: string; title: string; type: string
  dueDate: string | null; dueTime: string | null; weight?: number | null; notes?: string; done: boolean
  dateSource?: 'stated' | 'resolved' | 'manual' | 'feed' | null; dueText?: string
}
type View = 'month' | 'week' | 'agenda'

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
const startOfWeek = (d: Date) => addDays(d, -d.getDay())
const themeOf = (hex: string) => { const i = classIndexFromHex(hex); return i >= 0 ? `c${i}` : undefined }
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export default function CalendarPage() {
  const { authFetch, user } = useAuth()
  const { push } = useToast()
  const allSet = (useLocation().state as { allSet?: boolean } | null)?.allSet === true
  const { courses } = useCourses()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [view, setView] = useState<View>('month')
  const [anchor, setAnchor] = useState(() => new Date())
  const [items, setItems] = useState<Item[]>([])
  const [undated, setUndated] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [selected, setSelected] = useState<Item | null>(null)
  const [adding, setAdding] = useState(false)

  // Visible range: the month grid always starts on a Sunday and covers 6 weeks.
  const gridStart = useMemo(() => startOfWeek(new Date(anchor.getFullYear(), anchor.getMonth(), 1)), [anchor])
  const range = useMemo(() => {
    if (view === 'agenda') return { from: ymd(anchor), to: ymd(addDays(anchor, 41)) }
    return { from: ymd(gridStart), to: ymd(addDays(gridStart, 41)) }
  }, [view, anchor, gridStart])

  const load = useCallback(async () => {
    try {
      const r = await fetchRef.current(`/assignments?from=${range.from}&to=${range.to}`)
      if (!r.ok) throw new Error(String(r.status))
      setItems((await r.json()).assignments ?? [])
      const u = await fetchRef.current('/assignments?undated=include&from=1970-01-01&to=1970-01-02')
      if (u.ok) setUndated(((await u.json()).assignments ?? []).filter((a: Item) => !a.dueDate))
      setError(false)
    } catch { setError(true) } finally { setLoading(false) }
  }, [range.from, range.to])
  useEffect(() => { if (user) load() }, [user, load])

  const byDay = useMemo(() => {
    const m = new Map<string, Item[]>()
    items.forEach(a => { if (a.dueDate) m.set(a.dueDate, [...(m.get(a.dueDate) ?? []), a]) })
    return m
  }, [items])

  async function patch(a: Item, body: Record<string, unknown>) {
    try {
      const r = await fetchRef.current(`/assignments/${a.id}`, { method: 'PATCH', body: JSON.stringify(body) })
      if (!r.ok) throw new Error(await errorMessage(r))
      const { assignment } = await r.json()
      setSelected(assignment)
      await load()
    } catch (e) { push('error', "Couldn't update that item", e instanceof Error ? e.message : 'Try again.') }
  }

  const today = ymd(new Date())
  const shift = (n: number) => setAnchor(a => (view === 'month' ? new Date(a.getFullYear(), a.getMonth() + n, 1) : addDays(a, view === 'week' ? 7 * n : 30 * n)))
  const title = view === 'month' ? anchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
    : view === 'week' ? `Week of ${startOfWeek(anchor).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
    : `From ${anchor.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`

  const cells = useMemo(() => {
    const all = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
    if (view === 'week') { const s = startOfWeek(anchor); return Array.from({ length: 7 }, (_, i) => addDays(s, i)) }
    return all
  }, [gridStart, view, anchor])

  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">Calendar</span>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h1>{title}</h1>
          <div className="row">
            <div className="segmented" role="group" aria-label="View">
              {(['month', 'week', 'agenda'] as View[]).map(v => <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>{v[0].toUpperCase() + v.slice(1)}</button>)}
            </div>
            <button type="button" className="btn-ghost btn-sm" onClick={() => shift(-1)} aria-label="Previous">‹</button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => setAnchor(new Date())}>Today</button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => shift(1)} aria-label="Next">›</button>
            <button type="button" className="btn-primary btn-sm" onClick={() => setAdding(true)} disabled={courses.length === 0}>Add deadline</button>
          </div>
        </div>
      </div>

      {allSet && <div className="campus-note row" role="status" style={{ justifyContent: 'space-between' }}><span><strong>All set.</strong> Every deadline is here. Open Study for your class agents.</span><Link to="/study" className="btn-primary btn-sm">Open Study</Link></div>}

      {error && <div className="warning" role="alert"><span>We couldn't load your calendar.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div>}

      {loading ? <div className="skeleton-block" style={{ height: '24rem' }} aria-busy="true" aria-label="Loading calendar" />
        : courses.length === 0 ? (
          <div className="empty"><Robot name="calendar-sync" size={72} /><div className="empty-title">Nothing on your calendar yet</div><p className="empty-body">Add a class and its deadlines appear here, color-coded.</p><Link to="/study" className="btn-primary">Add a class</Link></div>
        ) : view === 'agenda' ? (
          <Agenda items={items} onSelect={setSelected} today={today} />
        ) : (
          <div className="cal-grid" role="grid" aria-label={title}>
            {DOW.map(d => <div key={d} className="cal-dow" role="columnheader">{d}</div>)}
            {cells.map(d => {
              const key = ymd(d)
              const list = byDay.get(key) ?? []
              return (
                <div key={key} className="cal-cell" role="gridcell" data-outside={view === 'month' && d.getMonth() !== anchor.getMonth()} data-today={key === today}>
                  <span className="cal-date" aria-label={d.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}>{d.getDate()}</span>
                  {list.slice(0, view === 'week' ? 10 : 3).map(a => <EventChip key={a.id} a={a} onSelect={setSelected} />)}
                  {view === 'month' && list.length > 3 && <span className="muted" style={{ fontSize: 'var(--text-xs)' }}>+{list.length - 3} more</span>}
                </div>
              )
            })}
          </div>
        )}

      {selected && <Detail a={selected} onClose={() => setSelected(null)} onPatch={patch} />}

      {undated.length > 0 && (
        <section className="undated stack" style={{ gap: 'var(--s-2)' }} aria-label="Needs a date">
          <span className="eyebrow">Needs a date</span>
          {undated.map(a => <EventRow key={a.id} a={a} onSelect={setSelected} />)}
        </section>
      )}

      <UnassignedInbox onChanged={load} />

      {adding && <AddDeadline courses={courses.map(c => ({ id: c.id, code: c.courseCode || 'Class' }))} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); load() }} />}
      <SubscribePanel />
    </div>
  )
}

function EventChip({ a, onSelect }: { a: Item; onSelect: (a: Item) => void }) {
  return (
    <button type="button" className="cal-event" data-theme={themeOf(a.courseColor)} data-estimated={a.dateSource === 'resolved'} data-done={a.done}
      onClick={() => onSelect(a)} aria-label={`${a.courseCode} ${a.title}${a.dateSource === 'resolved' ? ', estimated date' : ''}${a.done ? ', done' : ''}`}>
      {a.title}
    </button>
  )
}

function EventRow({ a, onSelect }: { a: Item; onSelect: (a: Item) => void }) {
  return (
    <button type="button" className="agenda-item" style={{ textAlign: 'left', width: '100%' }} data-theme={themeOf(a.courseColor)} data-estimated={a.dateSource === 'resolved'} data-done={a.done} onClick={() => onSelect(a)}>
      <span className="agenda-time">{a.dueTime ?? 'all day'}</span>
      <span className="grow"><span className="agenda-title">{a.title}</span><span className="agenda-note" style={{ display: 'block' }}>{a.courseCode}{a.dateSource === 'resolved' ? ' · estimated date' : ''}{a.dueText && !a.dueDate ? ` · ${a.dueText}` : ''}</span></span>
      <span className="chip chip-outline">{a.type}</span>
    </button>
  )
}

function Agenda({ items, onSelect, today }: { items: Item[]; onSelect: (a: Item) => void; today: string }) {
  const days = [...new Set(items.filter(a => a.dueDate).map(a => a.dueDate!))].sort()
  if (days.length === 0) return <div className="empty"><div className="empty-title">Nothing due in this stretch</div><p className="empty-body">Enjoy the breathing room.</p></div>
  return (
    <div className="stack">
      {days.map(day => (
        <div key={day} className="agenda-day stack" style={{ gap: 'var(--s-2)' }}>
          <h3>{day === today ? 'Today' : new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}</h3>
          {items.filter(a => a.dueDate === day).map(a => <EventRow key={a.id} a={a} onSelect={onSelect} />)}
        </div>
      ))}
    </div>
  )
}

function Detail({ a, onClose, onPatch }: { a: Item; onClose: () => void; onPatch: (a: Item, b: Record<string, unknown>) => void }) {
  const [date, setDate] = useState(a.dueDate ?? '')
  const [time, setTime] = useState(a.dueTime ?? '')
  useEffect(() => { setDate(a.dueDate ?? ''); setTime(a.dueTime ?? '') }, [a])
  return (
    <section className="window" data-theme={themeOf(a.courseColor)} aria-label={`${a.title} details`}>
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">{a.courseCode}</span><button type="button" className="btn-ghost-sm" onClick={onClose}>Close</button></div>
      <div className="window-body stack">
        <div><strong>{a.title}</strong><div className="row" style={{ marginTop: 'var(--s-2)' }}>
          <span className="chip chip-outline">{a.type}</span>{a.weight ? <span className="chip chip-outline">{a.weight}% of grade</span> : null}
          {a.dateSource === 'resolved' && <span className="badge badge-warn">Estimated date</span>}
        </div></div>
        {a.dateSource === 'resolved' && <p className="muted">This date was worked out from other dates in the syllabus{a.dueText ? ` (“${a.dueText}”)` : ''}. Confirm it below once you know for sure.</p>}
        {a.notes && <p>{a.notes}</p>}
        <div className="field-row">
          <div className="field"><label htmlFor="d-date">Due date</label><input id="d-date" type="date" value={date} onChange={e => setDate(e.target.value)} /></div>
          <div className="field"><label htmlFor="d-time">Time (optional)</label><input id="d-time" type="time" value={time} onChange={e => setTime(e.target.value)} /></div>
        </div>
        <div className="row">
          <button type="button" className="btn-primary btn-sm" disabled={!date} onClick={() => onPatch(a, { dueDate: date, dueTime: time || null })}>{a.dateSource === 'resolved' ? 'Confirm this date' : 'Save date'}</button>
          <button type="button" className="btn-ghost btn-sm" onClick={() => onPatch(a, { done: !a.done })}>{a.done ? 'Mark not done' : 'Mark done'}</button>
        </div>
      </div>
    </section>
  )
}

function AddDeadline({ courses, onClose, onSaved }: { courses: { id: string; code: string }[]; onClose: () => void; onSaved: () => void }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const [f, setF] = useState({ courseId: courses[0]?.id ?? '', title: '', type: 'homework', dueDate: '', dueTime: '' })
  const [busy, setBusy] = useState(false)
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true)
    try {
      const body: Record<string, unknown> = { courseId: f.courseId, title: f.title.trim(), type: f.type }
      if (f.dueDate) body.dueDate = f.dueDate
      if (f.dueDate && f.dueTime) body.dueTime = f.dueTime
      const r = await authFetch('/assignments', { method: 'POST', body: JSON.stringify(body) })
      if (!r.ok) { push('error', "Couldn't add the deadline", await errorMessage(r)); return }
      push('success', 'Deadline added'); onSaved()
    } catch { push('error', "Couldn't add the deadline", 'Network problem. Try again.') } finally { setBusy(false) }
  }
  return (
    <section className="window" aria-label="Add a deadline">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">add-deadline</span><button type="button" className="btn-ghost-sm" onClick={onClose}>Close</button></div>
      <form className="window-body request-form" onSubmit={save}>
        <div className="field-row">
          <div className="field"><label htmlFor="a-course">Class</label><select id="a-course" value={f.courseId} onChange={e => setF({ ...f, courseId: e.target.value })}>{courses.map(c => <option key={c.id} value={c.id}>{c.code}</option>)}</select></div>
          <div className="field"><label htmlFor="a-type">Type</label><select id="a-type" value={f.type} onChange={e => setF({ ...f, type: e.target.value })}>{['exam', 'quiz', 'homework', 'project', 'paper', 'reading', 'study', 'other'].map(t => <option key={t}>{t}</option>)}</select></div>
        </div>
        <div className="field"><label htmlFor="a-title">Title</label><input id="a-title" required minLength={1} maxLength={160} value={f.title} onChange={e => setF({ ...f, title: e.target.value })} placeholder="Problem set 4" /></div>
        <div className="field-row">
          <div className="field"><label htmlFor="a-date">Due date</label><input id="a-date" type="date" value={f.dueDate} onChange={e => setF({ ...f, dueDate: e.target.value })} /></div>
          <div className="field"><label htmlFor="a-time">Time (optional)</label><input id="a-time" type="time" value={f.dueTime} disabled={!f.dueDate} onChange={e => setF({ ...f, dueTime: e.target.value })} /></div>
        </div>
        <button type="submit" className="btn-primary" disabled={busy || !f.title.trim() || !f.courseId} aria-busy={busy}>Add deadline</button>
      </form>
    </section>
  )
}

/** Outbound iCal feed. The token is a secret: masked until shown, never logged. */
export function SubscribePanel() {
  const { profile, setProfile, tenant, authFetch } = useAuth()
  const { push } = useToast()
  const [show, setShow] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const api = (window as any).__config?.apiUrl as string | undefined
  const path = profile?.calendarPath ?? (profile?.calToken ? `/cal/${profile.calToken}.ics` : null)
  const url = api && path ? `${api}${path}` : null

  async function copy() {
    if (!url) return
    try { await navigator.clipboard.writeText(url); push('success', 'Link copied', 'Paste it into your calendar app.') }
    catch { setShow(true); push('info', 'Copy it manually', 'Your browser blocked copying. The link is shown so you can select it.') }
  }
  async function rotate() {
    try {
      const r = await authFetch('/me/calendar-token/rotate', { method: 'POST', body: '{}' })
      if (!r.ok) { push('error', "Couldn't make a new link", await errorMessage(r)); return }
      const j = await r.json()
      setProfile({ ...profile, calToken: j.calToken, calendarPath: j.calendarPath }, tenant)
      setConfirm(false); setShow(false)
      push('success', 'New link created', 'The old link no longer works. Re-subscribe in your calendar app.')
    } catch { push('error', "Couldn't make a new link", 'Network problem. Try again.') }
  }

  return (
    <section className="window subscribe-panel" aria-label="Subscribe to your calendar">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">subscribe</span></div>
      <div className="window-body subscribe-panel">
        <p>See your deadlines in Google Calendar, Apple Calendar or Outlook. Subscribe once and it stays up to date.</p>
        {url ? (
          <>
            <div className="copy-field">
              <input readOnly aria-label="Calendar link" value={show ? url : '•'.repeat(32)} className={show ? '' : 'secret-mask'} onFocus={e => show && e.currentTarget.select()} />
              <button type="button" className="btn-ghost btn-sm" onClick={() => setShow(s => !s)}>{show ? 'Hide' : 'Show'}</button>
              <button type="button" className="btn-primary btn-sm" onClick={copy}>Copy</button>
            </div>
            <div className="secret-note" role="note">Anyone with this link can see your deadlines. Don't share it.</div>
            <details><summary>How to subscribe</summary>
              <ul className="stack" style={{ gap: 'var(--s-2)', marginTop: 'var(--s-2)' }}>
                <li><strong>Google Calendar:</strong> Other calendars, From URL, paste the link. Google refreshes on its own schedule, often many hours.</li>
                <li><strong>Apple Calendar:</strong> File, New Calendar Subscription, paste the link.</li>
                <li><strong>Outlook:</strong> Add calendar, Subscribe from web, paste the link.</li>
              </ul>
              <p className="muted" style={{ marginTop: 'var(--s-2)' }}>This page is always live; subscribed calendars refresh about hourly or slower.</p>
            </details>
            {confirm ? (
              <div className="row"><span>Make a new link? The old one stops working.</span><button type="button" className="btn-danger btn-sm" onClick={rotate}>Yes, replace it</button><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm(false)}>Keep</button></div>
            ) : <button type="button" className="btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setConfirm(true)}>Make a new link</button>}
          </>
        ) : <p className="muted">Your calendar link isn't ready yet. Try again in a moment.</p>}
      </div>
    </section>
  )
}
