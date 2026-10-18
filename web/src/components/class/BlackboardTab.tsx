import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { errorMessage, timeAgo } from '../../lib/api'
import { useEndpoint } from '../../lib/useEndpoint'
import { useToast } from '../Toast'
import Robot from '../Robot'

interface FeedItem { uid: string; assignmentId?: string; title: string; type?: string; dueDate?: string | null; dueTime?: string | null; isNew?: boolean; removedFromFeed?: boolean }
interface Feed {
  connected: boolean
  stats: { lastCheckedAt: string | null; lastStatus: string; lastError: { code: string; message: string } | null; newItemsCount: number; unassignedCount: number; itemCount: number; syncCooldownSeconds: number } | null
  items: FeedItem[]
  unassigned: FeedItem[]
}

const when = (d?: string | null, t?: string | null) => {
  if (!d) return 'No date'
  const day = new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  return t ? `${day}, ${t}` : day
}

/** This class's Blackboard view (FEED_API.md). Plain text only: event titles come from the student's feed. */
export default function BlackboardTab({ courseId, courseCode, onChanged }: { courseId: string; courseCode: string; onChanged: () => void }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const { data, state, reload } = useEndpoint<Feed>(`/courses/${courseId}/feed`)
  const [busy, setBusy] = useState(false)
  const [cool, setCool] = useState(0)

  // Opening the tab clears the "new from Blackboard" badge.
  useEffect(() => {
    if (state === 'ok' && data?.connected) fetchRef.current('/feed/seen', { method: 'POST', body: JSON.stringify({ courseId }) }).catch(() => {})
  }, [state, data?.connected, courseId])
  useEffect(() => { if (data?.stats?.syncCooldownSeconds) setCool(data.stats.syncCooldownSeconds) }, [data])
  useEffect(() => {
    if (cool <= 0) return
    const t = window.setTimeout(() => setCool(c => c - 1), 1000)
    return () => window.clearTimeout(t)
  }, [cool])

  async function checkNow() {
    setBusy(true)
    try {
      const r = await authFetch(`/courses/${courseId}/feed/sync`, { method: 'POST', body: '{}' })
      if (!r.ok) {
        if (r.status === 429) setCool(Number(r.headers.get('Retry-After')) || 120)
        push('error', "Couldn't check Blackboard", await errorMessage(r)); return
      }
      const j = await r.json()
      push('success', j.status === 'changed' ? `Found ${j.added ?? 0} new, ${j.updated ?? 0} updated` : 'Checked: nothing new')
      setCool(120); reload(); onChanged()
    } catch { push('error', "Couldn't check Blackboard", 'Network problem. Try again.') } finally { setBusy(false) }
  }

  async function assign(uid: string) {
    try {
      const r = await authFetch(`/feed/unassigned/${uid}/assign`, { method: 'POST', body: JSON.stringify({ courseId, remember: true }) })
      if (!r.ok) { push('error', "Couldn't add it", await errorMessage(r)); return }
      const j = await r.json()
      push('success', 'Added to this class', j.alsoAssigned ? `and ${j.alsoAssigned} similar item${j.alsoAssigned === 1 ? '' : 's'}` : undefined)
      reload(); onChanged()
    } catch { push('error', "Couldn't add it", 'Network problem. Try again.') }
  }

  if (state === 'loading') return <div className="skeleton-block" aria-busy="true" aria-label="Loading Blackboard status" />
  if (state === 'unavailable') return (
    <div className="empty"><Robot name="base" size={72} /><div className="empty-title">Blackboard checks are coming soon</div>
      <p className="empty-body">Connect your Blackboard calendar link and {courseCode || 'this class'}'s agent will watch it for new deadlines.</p></div>
  )
  if (state === 'error') return <div className="warning" role="alert"><span>We couldn't load Blackboard status.</span><button type="button" className="btn-ghost-sm" onClick={reload}>Try again</button></div>

  const feed = data
  if (!feed?.connected) return (
    <div className="config-item" data-state="empty">
      <h3>Blackboard not connected <span className="badge badge-warn">Not set up yet</span></h3>
      <p className="config-value">Connect Blackboard once to pull in your deadlines and classes.</p>
      <Link to="/settings" className="btn-primary btn-sm" style={{ alignSelf: 'flex-start' }}>Connect in Settings</Link>
      <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>The feed carries dates and events only, not files, announcements or grades.</p>
    </div>
  )

  const s = feed.stats
  return (
    <div className="stack">
      <div className="config-item" data-state="set">
        <h3>Blackboard calendar <span className={`badge ${s?.lastStatus === 'error' ? 'badge-danger' : 'badge-ok'}`}>{s?.lastStatus === 'error' ? 'Problem' : 'Connected'}</span></h3>
        <p className="config-value">{s?.lastCheckedAt ? `Last checked ${timeAgo(s.lastCheckedAt)}.` : 'Not checked yet.'}{s?.lastError ? ` ${s.lastError.message}` : ''}</p>
        <div className="row">
          <button type="button" className="btn-primary btn-sm" disabled={busy || cool > 0} aria-busy={busy} onClick={checkNow}>{cool > 0 ? `Check again in ${cool}s` : 'Check now'}</button>
          <span className="muted" style={{ fontSize: 'var(--text-sm)' }}>We also check about hourly. Dates and events only: not files, announcements or grades.</span>
        </div>
      </div>

      {feed.unassigned.length > 0 && (
        <section className="undated stack" style={{ gap: 'var(--s-2)' }} aria-label="Might be for this class">
          <h3 className="eyebrow">Is this {courseCode || 'class'}?</h3>
          {feed.unassigned.map(i => (
            <div key={i.uid} className="agenda-item">
              <span className="agenda-time">{when(i.dueDate, i.dueTime)}</span>
              <span className="agenda-title">{i.title}</span>
              <button type="button" className="btn-primary btn-sm" onClick={() => assign(i.uid)}>Yes, add it</button>
            </div>
          ))}
        </section>
      )}

      <section className="stack" style={{ gap: 'var(--s-2)' }} aria-label="From Blackboard">
        <h3 className="eyebrow">From Blackboard ({feed.items.length})</h3>
        {feed.items.length === 0 ? <p className="muted">Nothing from Blackboard for this class yet.</p> : feed.items.map(i => (
          <div key={i.uid} className="agenda-item" data-done={!!i.removedFromFeed}>
            <span className="agenda-time">{when(i.dueDate, i.dueTime)}</span>
            <span className="grow"><span className="agenda-title">{i.title}</span>{i.removedFromFeed && <span className="agenda-note" style={{ display: 'block' }}>Removed from Blackboard</span>}</span>
            {i.isNew && <span className="badge">New</span>}
          </div>
        ))}
      </section>
    </div>
  )
}
