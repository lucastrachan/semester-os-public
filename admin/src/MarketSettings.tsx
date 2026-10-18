import { useState } from 'react'
import { api } from './api'

const ALL = ['books', 'supplies', 'electronics', 'dorm', 'clothing', 'tickets', 'tutoring', 'rides', 'other']

/** Per-campus marketplace switches: which categories students can post in, and the ticket face-value cap. */
export function MarketSettings({ campusId, categories, ticketPriceCap, onSaved }:
  { campusId: string; categories?: string[]; ticketPriceCap?: boolean; onSaved: () => Promise<void> }) {
  const start = (categories && categories.length ? categories : ALL).map(c => (c === 'textbooks' ? 'books' : c))
  const [picked, setPicked] = useState<string[]>(start)
  const [cap, setCap] = useState(ticketPriceCap !== false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const toggle = (c: string) => setPicked(p => (p.includes(c) ? p.filter(x => x !== c) : [...p, c]))

  async function save() {
    if (!window.confirm('Save marketplace settings for this campus?')) return
    setBusy(true); setMsg(null)
    try {
      await api(`/admin/campuses/${campusId}/marketplace`, { method: 'POST', body: { categories: picked, ticketPriceCap: cap } })
      setMsg({ ok: true, text: 'Saved.' }); await onSaved()
    } catch (e: any) { setMsg({ ok: false, text: e.message }) } finally { setBusy(false) }
  }

  return (
    <div className="ops-req">
      <strong>Marketplace</strong>
      <div className="chip-row">
        {ALL.map(c => (
          <label key={c} className="chip chip-outline">
            <input type="checkbox" checked={picked.includes(c)} disabled={c === 'books'} onChange={() => toggle(c)} /> {c}
          </label>
        ))}
      </div>
      <label><input type="checkbox" checked={cap} onChange={e => setCap(e.target.checked)} /> Cap ticket prices at face value (recommended)</label>
      {msg && <p className={msg.ok ? 'ops-msg-ok' : 'ops-msg-err'} role={msg.ok ? 'status' : 'alert'}>{msg.text}</p>}
      <div><button className="btn-primary" disabled={busy || picked.length === 0} aria-busy={busy} onClick={() => void save()}>Save marketplace settings</button></div>
    </div>
  )
}
