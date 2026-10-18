import { useState } from 'react'
import { api } from './api'
import { ago, useLoad } from './useLoad'

interface Account { emailHash: string; email: string; tenantId: string; note: string; createdAt: string }

/** Test students for demos: an email you control mapped to a campus. Emails are masked after creation. */
export function DemoAccounts() {
  const accounts = useLoad<{ accounts: Account[]; max: number }>('/admin/demo-accounts')
  const campuses = useLoad<{ campuses: { id: string; name: string; disabled?: boolean }[] }>('/admin/campuses')
  const [email, setEmail] = useState('')
  const [tenantId, setTenantId] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const usable = (campuses.data?.campuses ?? []).filter(c => !c.disabled)

  async function add(ev: React.FormEvent) {
    ev.preventDefault(); setBusy(true); setMsg(null)
    try {
      const r = await api<{ email: string }>('/admin/demo-accounts', { method: 'POST', body: { email, tenantId: tenantId || usable[0]?.id, note } })
      setMsg({ ok: true, text: `Added ${r.email}. It is masked in the list from now on.` })
      setEmail(''); setNote(''); await accounts.reload()
    } catch (e: any) { setMsg({ ok: false, text: e.message }) } finally { setBusy(false) }
  }

  async function remove(a: Account) {
    if (!window.confirm(`Remove demo account ${a.email}? That email can no longer sign in as a student.`)) return
    setMsg(null)
    try { await api(`/admin/demo-accounts/${a.emailHash}`, { method: 'DELETE' }); setMsg({ ok: true, text: 'Removed.' }); await accounts.reload() }
    catch (e: any) { setMsg({ ok: false, text: e.message }) }
  }

  return (
    <div className="stack">
      <div className="window">
        <div className="window-bar"><span className="window-title">Add a demo account</span></div>
        <div className="window-body ops-form">
          <form className="field-row" onSubmit={add}>
            <div className="field"><label htmlFor="da-e">Email</label>
              <input id="da-e" type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@gmail.com" autoComplete="off" /></div>
            <div className="field"><label htmlFor="da-c">Campus</label>
              <select id="da-c" value={tenantId || usable[0]?.id || ''} onChange={e => setTenantId(e.target.value)}>
                {usable.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select></div>
            <div className="field"><label htmlFor="da-n">Note</label>
              <input id="da-n" value={note} maxLength={200} onChange={e => setNote(e.target.value)} /></div>
            <button className="btn-primary" disabled={busy || !email || usable.length === 0} aria-busy={busy}>Add</button>
          </form>
          <p className="muted">Plain addresses only (no + aliases). At most {accounts.data?.max ?? 20} accounts.</p>
        </div>
      </div>
      {msg && <p className={msg.ok ? 'ops-msg-ok' : 'ops-msg-err'} role={msg.ok ? 'status' : 'alert'}>{msg.text}</p>}
      {accounts.error && <p className="ops-msg-err" role="alert">{accounts.error}</p>}
      {accounts.loading && !accounts.data && <div className="skeleton-block" aria-busy="true" />}
      {accounts.data && accounts.data.accounts.length === 0 && <div className="empty"><div className="empty-title">No demo accounts</div></div>}
      <div className="ops-list">
        {accounts.data?.accounts.map(a => (
          <div className="ops-row" key={a.emailHash}>
            <div className="ops-row-head">
              <div className="meta"><strong className="mono">{a.email}</strong><span className="domain">{a.tenantId}</span>
                {a.note && <span className="muted">{a.note}</span>}<span className="muted">{ago(a.createdAt)}</span></div>
              <div className="ops-actions"><button className="btn-reject" onClick={() => void remove(a)}>Remove</button></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
