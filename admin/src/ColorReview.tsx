import { useState } from 'react'
import { api } from './api'

export interface ColorCampus {
  id: string; name: string; shortName: string
  theme?: { primary: string }
  colorStatus?: string; colorSource?: string; colorConfidence?: number
}

const NEEDS = ['needs_review', 'placeholder']

/** Campuses whose colour was detected automatically (or is a placeholder): approve it or set a new one. */
export function ColorReview({ campuses, onChanged }: { campuses: ColorCampus[]; onChanged: () => Promise<void> }) {
  const todo = campuses.filter(c => c.colorStatus && NEEDS.includes(c.colorStatus))
  const [picks, setPicks] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  if (todo.length === 0 && !msg) return null

  async function act(c: ColorCampus, path: string, body: unknown, okText: string, confirmText: string) {
    if (!window.confirm(confirmText)) return
    setBusy(c.id); setMsg(null)
    try { await api(path, { method: 'POST', body }); setMsg({ ok: true, text: okText }); await onChanged() }
    catch (e: any) { setMsg({ ok: false, text: e.message }) } finally { setBusy('') }
  }

  return (
    <div className="window">
      <div className="window-bar"><span className="window-title">Colour review ({todo.length})</span></div>
      <div className="window-body ops-form">
        <p className="muted">These campuses got their colour automatically. Check it looks right for the school, then approve it or type a different one.</p>
        {msg && <p className={msg.ok ? 'ops-msg-ok' : 'ops-msg-err'} role={msg.ok ? 'status' : 'alert'}>{msg.text}</p>}
        {todo.map(c => {
          const detected = c.theme?.primary ?? ''
          const pick = picks[c.id] ?? ''
          const valid = /^#[0-9a-fA-F]{6}$/.test(pick)
          return (
            <div className="ops-req" key={c.id}>
              <div className="meta">
                <svg width="22" height="22" role="img" aria-label={`Detected colour ${detected}`}><rect width="22" height="22" rx="4" fill={/^#[0-9a-fA-F]{6}$/.test(detected) ? detected : '#cccccc'} /></svg>
                <strong>{c.name}</strong> <span className="chip-outline chip mono">{detected || 'none'}</span>
                <span className="badge badge-warn">{c.colorStatus}</span>
                <span className="muted">source: {c.colorSource ?? 'unknown'}, confidence: {typeof c.colorConfidence === 'number' ? `${Math.round(c.colorConfidence * 100)}%` : 'unknown'}</span>
              </div>
              <div className="ops-actions">
                <button className="btn-approve" disabled={busy === c.id || !detected} onClick={() => void act(c, `/admin/campuses/${c.id}/color/approve`, {}, `${c.name} colour approved.`, `Approve ${detected} for ${c.name}?`)}>Approve detected colour</button>
                <input aria-label={`New colour for ${c.name}`} placeholder="#RRGGBB" maxLength={7} value={pick} onChange={e => setPicks(p => ({ ...p, [c.id]: e.target.value.trim() }))} />
                <button className="btn-ghost-sm" disabled={busy === c.id || !valid} onClick={() => void act(c, `/admin/campuses/${c.id}/color`, { color: pick }, `${c.name} colour set.`, `Set ${pick} for ${c.name}?`)}>Set colour</button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
