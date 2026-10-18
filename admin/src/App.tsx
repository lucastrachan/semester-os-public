import { useState } from 'react'
import { AuthGate, useAdmin } from './Auth'
import { api } from './api'
import { CampusForm, type CampusInput } from './CampusForm'
import { Reports } from './Reports'
import { DemoAccounts } from './DemoAccounts'
import { useLoad } from './useLoad'
import { MarketSettings } from './MarketSettings'
import { ColorReview, type ColorCampus } from './ColorReview'

export type Tab = 'overview' | 'reports' | 'campuses' | 'demo' | 'audit'
const TABS: [Tab, string][] = [['overview', 'Overview'], ['reports', 'Reports'], ['campuses', 'Campuses'], ['demo', 'Demo accounts'], ['audit', 'Audit log']]

export default function App() {
  return <AuthGate><Console /></AuthGate>
}

function Console() {
  const { admin, signOut } = useAdmin()
  const [tab, setTab] = useState<Tab>('overview')
  return (
    <div className="ops-shell">
      <header className="ops-top">
        <div className="ops-brand">Semester <span>OS ADMIN</span></div>
        <div className="ops-user"><span>{admin.email}</span>
          <button className="btn-ghost-sm" onClick={() => void signOut()}>Sign out</button></div>
      </header>
      <nav className="ops-tabs" aria-label="Sections">
        {TABS.map(([id, label]) => (
          <button key={id} aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>
      <main>
        {tab === 'overview' && <Overview go={setTab} />}
        {tab === 'reports' && <Reports />}
        {tab === 'campuses' && <Campuses />}
        {tab === 'demo' && <DemoAccounts />}
        {tab === 'audit' && <Audit />}
      </main>
    </div>
  )
}

// ── Overview ────────────────────────────────────────────────────────────────

function Overview({ go }: { go: (t: Tab) => void }) {
  const { data, error, loading } = useLoad<{ campuses: number; demoCampuses: number; colorReviews: number; openReports: number; demoAccounts: number }>('/admin/overview')
  if (loading) return <div className="skeleton-block" aria-busy="true" />
  if (error || !data) return <p className="ops-msg-err" role="alert">{error}</p>
  return (
    <div className="stack">
      <div className="ops-grid">
        <div className="ops-stat"><b>{data.campuses}</b><span>Campuses live ({data.demoCampuses} demo)</span></div>
        <div className="ops-stat"><b>{data.openReports}</b><span>Open reports</span></div>
        <div className="ops-stat"><b>{data.colorReviews}</b><span>Campus colours to review</span></div>
        <div className="ops-stat"><b>{data.demoAccounts}</b><span>Demo accounts</span></div>
      </div>
      <div className="ops-actions">
        {data.openReports > 0 && <button className="btn-primary" onClick={() => go('reports')}>Review {data.openReports} open report(s)</button>}
        {data.colorReviews > 0 && <button className="btn-ghost" onClick={() => go('campuses')}>Review colours</button>}
        <button className="btn-ghost" onClick={() => go('campuses')}>Create a campus</button>
      </div>
    </div>
  )
}

function payload(i: CampusInput) {
  return {
    name: i.name, shortName: i.shortName || undefined, domains: i.domains, themeColor: i.themeColor,
    timezone: i.timezone, lmsType: i.lmsType, tutoringResources: i.tutoringResources,
    pickupSpots: i.pickupSpots, openToNetwork: i.openToNetwork,
  }
}

// ── Campuses ────────────────────────────────────────────────────────────────

interface Campus {
  id: string; name: string; shortName: string; domains: string[]; timezone: string
  theme?: { primary: string; ink?: string }; lms?: { type: string }; demo?: boolean; autoCreated?: boolean; disabled?: boolean
  disabledReason?: string; categories?: string[]; ticketPriceCap?: boolean; colorStatus?: string; colorSource?: string; colorConfidence?: number; openToNetwork?: boolean; tutoringResources?: CampusInput['tutoringResources']; pickupSpots?: string[]
}
interface Blocked { domain: string; reason?: string; blockedBy?: string; blockedAt?: string }

function Campuses() {
  const { data, error, loading, reload } = useLoad<{ campuses: Campus[] }>('/admin/campuses')
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  async function act(fn: () => Promise<unknown>, okText: string) {
    setBusy(true); setMsg(null)
    try { await fn(); setMsg({ ok: true, text: okText }); setCreating(false); setEditing(null); await reload() }
    catch (e: any) { setMsg({ ok: false, text: e.message }) } finally { setBusy(false) }
  }

  const create = (i: CampusInput) => act(() => api('/admin/campuses', { method: 'POST', body: payload(i) }),
    `${i.name} is live. Students at ${i.domains.join(', ')} can sign up now.`)
  const save = (c: Campus, i: CampusInput) =>
    act(() => api(`/admin/campuses/${c.id}`, { method: 'PATCH', body: { ...payload(i), domains: undefined } }), `${i.name} saved.`)
  function toggleDisabled(c: Campus) {
    if (c.disabled) return act(() => api(`/admin/campuses/${c.id}/enable`, { method: 'POST' }), `${c.name} re-enabled.`)
    const reason = window.prompt(`Disable ${c.name}? Its students cannot use the app until you re-enable it. Data is kept.\n\nReason (optional):`)
    if (reason === null) return
    return act(() => api(`/admin/campuses/${c.id}/disable`, { method: 'POST', body: { reason: reason || 'none' } }), `${c.name} disabled.`)
  }

  return (
    <div className="stack">
      <div className="ops-toolbar">
        {!creating && <button className="btn-primary" onClick={() => { setCreating(true); setEditing(null) }}>Create campus directly</button>}
        <button className="btn-ghost-sm" onClick={() => void reload()}>Refresh</button>
      </div>
      {msg && <p className={msg.ok ? 'ops-msg-ok' : 'ops-msg-err'} role={msg.ok ? 'status' : 'alert'}>{msg.text}</p>}
      {creating && (
        <div className="window"><div className="window-bar"><span className="window-title">New campus</span></div>
          <div className="window-body"><CampusForm submitLabel="Create campus" busy={busy} onSubmit={i => void create(i)} onCancel={() => setCreating(false)} /></div></div>
      )}
      {error && <p className="ops-msg-err" role="alert">{error}</p>}
      {loading && !data && <div className="skeleton-block" aria-busy="true" />}
      {data && <ColorReview campuses={data.campuses as ColorCampus[]} onChanged={reload} />}
      <div className="ops-list">
        {data?.campuses.map(c => (
          <div className="ops-row" key={c.id}>
            <div className="ops-row-head">
              <div className="meta"><strong>{c.name}</strong><span className="domain">{c.domains.join(', ')}</span>
                {c.autoCreated && <span className="badge badge-info">auto-created</span>}
                {c.demo && <span className="tag tag-demo">demo</span>}
                {c.disabled && <span className="badge badge-danger">disabled</span>}</div>
              <div className="ops-actions">
                <span className="chip-outline chip">{c.timezone}</span>
                <span className="chip-outline chip">{c.lms?.type ?? 'lms ?'}</span>
                <span className="chip-outline chip mono">{c.theme?.primary ?? ''}</span>
                <button className="btn-ghost-sm" onClick={() => { setEditing(editing === c.id ? null : c.id); setCreating(false) }}>{editing === c.id ? 'Close' : 'Edit'}</button>
                <button className={c.disabled ? 'btn-approve' : 'btn-reject'} disabled={busy} onClick={() => void toggleDisabled(c)}>{c.disabled ? 'Enable' : 'Disable'}</button>
              </div>
            </div>
            {c.disabled && c.disabledReason && <div className="ops-row-body muted">Disabled: {c.disabledReason}</div>}
            {editing === c.id && (
              <div className="ops-row-body">
                <CampusForm lockDomains submitLabel="Save changes" busy={busy} onCancel={() => setEditing(null)} onSubmit={i => void save(c, i)}
                  initial={{ name: c.name, shortName: c.shortName, domains: c.domains, themeColor: c.theme?.primary, timezone: c.timezone,
                    lmsType: c.lms?.type, tutoringResources: c.tutoringResources ?? [], pickupSpots: c.pickupSpots ?? [], openToNetwork: c.openToNetwork ?? true }} />
                <MarketSettings campusId={c.id} categories={c.categories} ticketPriceCap={c.ticketPriceCap} onSaved={reload} />
              </div>
            )}
          </div>
        ))}
      </div>
      <BlockedDomains />
    </div>
  )
}

function BlockedDomains() {
  const { data, error, reload } = useLoad<{ domains: Blocked[] }>('/admin/blocked-domains')
  const [domain, setDomain] = useState('')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')
  async function block(ev: React.FormEvent) {
    ev.preventDefault(); setErr('')
    try { await api('/admin/blocked-domains', { method: 'POST', body: { domain, reason } }); setDomain(''); setReason(''); await reload() }
    catch (e: any) { setErr(e.message) }
  }
  async function unblock(d: string) {
    if (!window.confirm(`Unblock ${d}?`)) return
    try { await api(`/admin/blocked-domains/${encodeURIComponent(d)}`, { method: 'DELETE' }); await reload() } catch (e: any) { setErr(e.message) }
  }
  return (
    <div className="window">
      <div className="window-bar"><span className="window-title">Blocked domains (abuse kill switch)</span></div>
      <div className="window-body ops-form">
        <form className="field-row" onSubmit={block}>
          <div className="field"><label>Domain</label><input required value={domain} onChange={e => setDomain(e.target.value)} placeholder="spam.edu" /></div>
          <div className="field"><label>Reason</label><input value={reason} maxLength={200} onChange={e => setReason(e.target.value)} /></div>
          <button className="btn-reject">Block domain</button>
        </form>
        {(err || error) && <p className="ops-msg-err" role="alert">{err || error}</p>}
        {data?.domains.length === 0 && <p className="muted">No blocked domains.</p>}
        {data?.domains.map(b => (
          <div className="ops-req" key={b.domain}>
            <div><b className="mono">{b.domain}</b> <span className="muted">{b.reason}</span></div>
            <div><button className="btn-ghost-sm" onClick={() => void unblock(b.domain)}>Unblock</button></div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Audit ───────────────────────────────────────────────────────────────────

interface Entry { at: string; adminEmail: string; action: string; target: string; detail?: Record<string, unknown> }

function Audit() {
  const { data, error, loading, reload } = useLoad<{ entries: Entry[] }>('/admin/audit')
  return (
    <div className="stack">
      <div className="ops-toolbar"><button className="btn-ghost-sm" onClick={() => void reload()}>Refresh</button>
        <span className="muted">Latest 100 actions. Entries expire after 90 days.</span></div>
      {error && <p className="ops-msg-err" role="alert">{error}</p>}
      {loading && !data && <div className="skeleton-block" aria-busy="true" />}
      {data && data.entries.length === 0 && <div className="empty"><div className="empty-title">No actions yet</div></div>}
      {data && data.entries.length > 0 && (
        <table className="ops-table">
          <thead><tr><th>When (UTC)</th><th>Admin</th><th>Action</th><th>Target</th></tr></thead>
          <tbody>{data.entries.map((e, i) => (
            <tr key={i}><td className="mono">{e.at.replace('T', ' ').slice(0, 19)}</td><td>{e.adminEmail}</td><td>{e.action}</td><td className="mono">{e.target}</td></tr>
          ))}</tbody>
        </table>
      )}
    </div>
  )
}
