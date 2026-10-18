import { useState } from 'react'
import { api } from './api'
import { ago, useLoad } from './useLoad'

interface Evidence { from: string; text: string; at: string }
interface Report {
  id: string; kind: 'listing' | 'conversation'; targetId: string; listingId: string; listingTitle: string
  reason: string; note: string; status: string; createdAt: string; reportedSub: string; reportedName: string
  reportedCampus: string; reporterRole?: string; demo: boolean; resolution?: string
  evidence?: Evidence[]
  conversation?: { exists: boolean; status?: string; closedReason?: string }
  listing?: { exists: boolean; title?: string; description?: string; price?: number | null; status?: string; hidden?: boolean }
}

/** Moderation queue. Everything from students is shown as plain text (React escapes it). */
export function Reports() {
  const [filter, setFilter] = useState('open')
  const { data, error, loading, reload } = useLoad<{ reports: Report[]; total: number }>(`/admin/reports?status=${filter}`)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  async function act(key: string, confirmText: string, path: string, body: unknown, okText: string) {
    if (!window.confirm(confirmText)) return
    setBusy(key); setMsg(null)
    try { await api(path, { method: 'POST', body }); setMsg({ ok: true, text: okText }); await reload() }
    catch (e: any) { setMsg({ ok: false, text: e.message }) } finally { setBusy('') }
  }

  return (
    <div className="stack">
      <div className="ops-toolbar">
        <select aria-label="Status" value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="open">Open</option><option value="resolved">Resolved</option><option value="all">All</option>
        </select>
        <button className="btn-ghost-sm" onClick={() => void reload()}>Refresh</button>
        <span className="muted">Opening this list is recorded in the audit log.</span>
      </div>
      {msg && <p className={msg.ok ? 'ops-msg-ok' : 'ops-msg-err'} role={msg.ok ? 'status' : 'alert'}>{msg.text}</p>}
      {error && <p className="ops-msg-err" role="alert">{error}</p>}
      {loading && !data && <div className="skeleton-block" aria-busy="true" />}
      {data && data.reports.length === 0 && <div className="empty"><div className="empty-title">No reports</div><div className="empty-body">Nothing matches this filter.</div></div>}
      <div className="ops-list">
        {data?.reports.map(r => {
          const disabled = busy.startsWith(r.id)
          return (
            <div className="ops-row" key={r.id}>
              <div className="ops-row-head">
                <div className="meta">
                  <strong>{r.kind === 'listing' ? 'Listing' : 'Conversation'}: {r.listingTitle || r.targetId}</strong>
                  <span className="badge badge-warn">{r.reason}</span>
                  <span className={`badge ${r.status === 'open' ? 'badge-danger' : 'badge-ok'}`}>{r.status}{r.resolution ? ` (${r.resolution})` : ''}</span>
                  {r.demo && <span className="tag tag-demo">demo</span>}
                  <span className="muted">{ago(r.createdAt)}</span>
                </div>
              </div>
              <div className="ops-row-body">
                <div className="muted">Reported person: {r.reportedName || 'Student'} {r.reportedCampus && `(${r.reportedCampus})`}{r.reporterRole ? `, reported by the ${r.reporterRole}` : ''}</div>
                {r.note && <div>Note: {r.note}</div>}

                {r.kind === 'listing' && r.listing && (r.listing.exists ? (
                  <div className="ops-req">
                    <div><b>{r.listing.title}</b> {r.listing.price != null && `($${r.listing.price})`} <span className="tag">{r.listing.status}</span>
                      {r.listing.hidden && <span className="badge badge-danger">hidden</span>}</div>
                    {r.listing.description && <div className="muted">{r.listing.description}</div>}
                  </div>
                ) : <div className="muted">The listing no longer exists.</div>)}

                {r.kind === 'conversation' && (
                  <div className="ops-req">
                    <div className="muted">Last messages (oldest first). Conversation: {r.conversation?.exists ? (r.conversation.status ?? 'open') : 'gone'}{r.conversation?.closedReason ? `, ${r.conversation.closedReason}` : ''}</div>
                    {(r.evidence ?? []).map((m, i) => (
                      <div key={i}><b>{m.from}</b>: {m.text}</div>
                    ))}
                  </div>
                )}

                <div className="ops-actions">
                  {r.kind === 'listing' && r.listing?.exists && (r.listing.hidden
                    ? <button className="btn-approve" disabled={disabled} onClick={() => void act(`${r.id}:unhide`, 'Show this listing to students again?', `/admin/listings/${r.targetId}/unhide`, {}, 'Listing is visible again.')}>Unhide listing</button>
                    : <button className="btn-reject" disabled={disabled} onClick={() => void act(`${r.id}:hide`, 'Hide this listing from all students?', `/admin/listings/${r.targetId}/hide`, {}, 'Listing hidden.')}>Hide listing</button>)}
                  {r.kind === 'conversation' && r.conversation?.exists && r.conversation.status !== 'closed' && (
                    <button className="btn-reject" disabled={disabled} onClick={() => void act(`${r.id}:close`, 'Close this conversation for both people?', `/admin/conversations/${r.targetId}/close`, {}, 'Conversation closed.')}>Close conversation</button>)}
                  {r.reportedSub && (
                    <button className="btn-reject" disabled={disabled} onClick={() => {
                      const reason = window.prompt('Ban this student? They lose access to the marketplace and chat, their listings are removed and chats closed.\n\nReason (optional):')
                      if (reason === null) return
                      void act(`${r.id}:ban`, 'Confirm: ban this student?', `/admin/users/${encodeURIComponent(r.reportedSub)}/ban`, { reason }, 'Student banned.')
                    }}>Ban student</button>)}
                  {r.reportedSub && (
                    <button className="btn-ghost-sm" disabled={disabled} onClick={() => void act(`${r.id}:unban`, 'Lift the ban on this student?', `/admin/users/${encodeURIComponent(r.reportedSub)}/unban`, {}, 'Ban lifted.')}>Unban</button>)}
                  {r.status === 'open' && <>
                    <button className="btn-approve" disabled={disabled} onClick={() => void act(`${r.id}:resolve`, 'Mark this report as handled?', `/admin/reports/${r.id}/resolve`, { resolution: 'actioned' }, 'Report resolved.')}>Mark resolved</button>
                    <button className="btn-ghost-sm" disabled={disabled} onClick={() => void act(`${r.id}:dismiss`, 'Dismiss this report (no action needed)?', `/admin/reports/${r.id}/resolve`, { resolution: 'dismissed' }, 'Report dismissed.')}>Dismiss</button>
                  </>}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
