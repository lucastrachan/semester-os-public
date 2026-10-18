import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage, timeAgo } from '../lib/api'
import { useEndpoint } from '../lib/useEndpoint'
import { useToast } from './Toast'

interface FeedStatus {
  connected: boolean; urlMasked?: string; lastCheckedAt?: string | null; lastStatus?: string
  lastError?: { code: string; message: string } | null
  counts?: { events: number; matched: number; unassigned: number; newSinceSeen: number }
  syncCooldownSeconds?: number
}

/** Blackboard "Share Calendar" link. The URL is a secret: typed into a password field, never shown again (only the masked form), never logged. */
export default function FeedCard({ onChanged }: { onChanged?: () => void }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const navigate = useNavigate()
  const { data, state, reload } = useEndpoint<FeedStatus>('/me/feed')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [confirmOff, setConfirmOff] = useState(false)

  async function connect(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const r = await authFetch('/me/feed', { method: 'PUT', body: JSON.stringify({ url: url.trim() }) })
      if (!r.ok) { setErr(await errorMessage(r, "That link didn't work. Check it and try again.")); return }
      let n: number | undefined
      try { const pj = await r.json(); if (typeof pj.upcomingCount === 'number') n = pj.upcomingCount } catch { /* no body */ }
      setUrl('')
      await authFetch('/me/feed/sync', { method: 'POST', body: '{}' }).catch(() => {})
      reload(); onChanged?.()
      push('success', n !== undefined ? `Imported ${n} deadline${n === 1 ? '' : 's'}` : 'Blackboard connected', 'Here is your calendar.')
      navigate('/calendar', { state: { allSet: true } })
    } catch { setErr('Network problem. Try again.') } finally { setBusy(false) }
  }
  async function syncNow() {
    setBusy(true)
    try {
      const r = await authFetch('/me/feed/sync', { method: 'POST', body: '{}' })
      if (!r.ok) { push('error', "Couldn't check Blackboard", await errorMessage(r)); return }
      push('success', 'Checked Blackboard'); reload(); onChanged?.()
    } catch { push('error', "Couldn't check Blackboard", 'Network problem. Try again.') } finally { setBusy(false) }
  }
  async function disconnect() {
    try {
      const r = await authFetch('/me/feed', { method: 'DELETE' })
      if (!r.ok) { push('error', "Couldn't disconnect", await errorMessage(r)); return }
      setConfirmOff(false); push('success', 'Blackboard disconnected', 'Deadlines already added stay.'); reload(); onChanged?.()
    } catch { push('error', "Couldn't disconnect", 'Network problem. Try again.') }
  }

  return (
    <section className="window" aria-label="Blackboard calendar">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">blackboard</span></div>
      <div className="window-body stack">
        {state === 'loading' ? <div className="skeleton-line" aria-busy="true" /> : state === 'unavailable' ? (
          <p className="muted">Blackboard sync is coming soon. When it's ready you'll paste your calendar link here once and every class agent will watch it for new deadlines.</p>
        ) : state === 'error' ? (
          <div className="warning" role="alert"><span>We couldn't load your Blackboard status.</span><button type="button" className="btn-ghost-sm" onClick={reload}>Try again</button></div>
        ) : data?.connected ? (
          <>
            <div className="row">
              <span className={`badge ${data.lastStatus === 'error' ? 'badge-danger' : 'badge-ok'}`}>{data.lastStatus === 'error' ? 'Problem' : 'Connected'}</span>
              <span className="mono muted">{data.urlMasked}</span>
            </div>
            <p className="muted">{data.lastCheckedAt ? `Last checked ${timeAgo(data.lastCheckedAt)}.` : 'Not checked yet.'}{data.lastError ? ` ${data.lastError.message}` : ''}{data.counts ? ` ${data.counts.events} events, ${data.counts.unassigned} waiting for a class.` : ''}</p>
            <div className="row">
              <button type="button" className="btn-primary btn-sm" disabled={busy || (data.syncCooldownSeconds ?? 0) > 0} aria-busy={busy} onClick={syncNow}>{(data.syncCooldownSeconds ?? 0) > 0 ? `Check again in ${data.syncCooldownSeconds}s` : 'Check now'}</button>
              {confirmOff
                ? <><span>Disconnect? Deadlines already added stay.</span><button type="button" className="btn-danger btn-sm" onClick={disconnect}>Yes, disconnect</button><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirmOff(false)}>Keep</button></>
                : <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirmOff(true)}>Disconnect</button>}
            </div>
          </>
        ) : (
          <form className="stack" onSubmit={connect}>
            <p>Paste your Blackboard calendar link to pull in every deadline. You'll then sort them into your classes in a tap. It's read-only: we never ask for your Blackboard password.</p>
            <div className="field">
              <label htmlFor="feed-url">Calendar link</label>
              <input id="feed-url" type="password" autoComplete="off" spellCheck={false} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…" />
              <span className="hint">In Blackboard: open Calendar, click the gear icon (Calendar Settings, top right of the Calendar page), then the three dots (More options) in the panel that opens, then Share calendar. Menu names can differ a little at your school. Treat this link like a password.</span>
            </div>
            {err && <p className="field-error" role="alert">{err}</p>}
            <button type="submit" className="btn-primary" style={{ alignSelf: 'flex-start' }} disabled={busy || !url.trim()} aria-busy={busy}>Connect Blackboard</button>
            <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>The feed carries dates and events only, not files, announcements or grades, and it mixes all your classes. Some instructors don't use the Blackboard calendar.</p>
          </form>
        )}
      </div>
    </section>
  )
}
