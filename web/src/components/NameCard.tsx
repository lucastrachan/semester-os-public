import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { cleanName, greetName, validatePart } from '../lib/name'
import { useToast } from './Toast'

/** Saves first and last name via PATCH /me and updates the profile in context. Shared by the one-time prompt and Settings. */
function useSaveName() {
  const { authFetch, profile, tenant, setProfile } = useAuth()
  const { push } = useToast()
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  async function save(first: string, last: string): Promise<boolean> {
    const bad = validatePart(first, 'first') ?? validatePart(last, 'last')
    if (bad) { setErr(bad); return false }
    setBusy(true); setErr('')
    try {
      const firstName = cleanName(first), lastName = cleanName(last)
      const r = await authFetch('/me', { method: 'PATCH', body: JSON.stringify({ firstName, lastName }) })
      if (!r.ok) { setErr(await errorMessage(r, 'We could not save your name. Try again.')); return false }
      const j = await r.json().catch(() => ({}))
      const next = j?.profile ?? j
      setProfile({ ...profile, firstName, lastName, displayName: `${firstName} ${lastName}`, ...(next && typeof next === 'object' ? next : {}), needsName: false }, j?.tenant ?? tenant)
      push('success', 'Name saved')
      return true
    } catch { setErr('Network problem. Try again.'); return false } finally { setBusy(false) }
  }
  return { save, err, busy, setErr }
}

function Fields({ idp, first, last, setFirst, setLast, err }: { idp: string; first: string; last: string; setFirst: (v: string) => void; setLast: (v: string) => void; err: string }) {
  const d = err ? `${idp}-err` : undefined
  return (
    <>
      <div className="field"><label htmlFor={`${idp}-first`}>First name</label>
        <input id={`${idp}-first`} value={first} onChange={e => setFirst(e.target.value)} autoComplete="given-name" maxLength={40} aria-invalid={err ? true : undefined} aria-describedby={d} /></div>
      <div className="field"><label htmlFor={`${idp}-last`}>Last name</label>
        <input id={`${idp}-last`} value={last} onChange={e => setLast(e.target.value)} autoComplete="family-name" maxLength={40} aria-invalid={err ? true : undefined} aria-describedby={d} />
        {err && <span id={d} className="field-error" role="alert">{err}</span>}</div>
    </>
  )
}

/** One-time inline prompt for accounts that have no name yet. Renders nothing once a name exists. */
export function NamePrompt() {
  const { profile } = useAuth()
  const { save, err, busy, setErr } = useSaveName()
  const [first, setFirst] = useState('')
  const [last, setLast] = useState('')
  if (!profile || profile.needsName !== true) return null
  return (
    <section className="window" aria-label="Your name">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">what-should-we-call-you</span></div>
      <form className="window-body stack" onSubmit={e => { e.preventDefault(); save(first, last) }} noValidate>
        <p><strong>What should we call you?</strong></p>
        <Fields idp="np" first={first} last={last} setFirst={v => { setFirst(v); setErr('') }} setLast={v => { setLast(v); setErr('') }} err={err} />
        <span className="hint">We use your first name to say hello. Classmates never see your name.</span>
        <div className="row"><button type="submit" className="btn-primary btn-sm" disabled={busy || !first.trim() || !last.trim()} aria-busy={busy}>Save</button></div>
      </form>
    </section>
  )
}

/** Editable "Your name" fields for Settings. */
export function NameField() {
  const { profile } = useAuth()
  const { save, err, busy, setErr } = useSaveName()
  const curFirst: string = profile?.firstName && !String(profile.firstName).includes('@') ? profile.firstName : ''
  const curLast: string = profile?.lastName && !String(profile.lastName).includes('@') ? profile.lastName : ''
  const [first, setFirst] = useState<string | null>(null)
  const [last, setLast] = useState<string | null>(null)
  const f = first ?? curFirst, l = last ?? curLast
  const changed = f.trim() !== curFirst || l.trim() !== curLast
  return (
    <form className="stack" onSubmit={async e => { e.preventDefault(); if (await save(f, l)) { setFirst(null); setLast(null) } }} noValidate>
      <Fields idp="set" first={f} last={l} setFirst={v => { setFirst(v); setErr('') }} setLast={v => { setLast(v); setErr('') }} err={err} />
      <div className="row"><button type="submit" className="btn-primary btn-sm" disabled={busy || !f.trim() || !l.trim() || !changed} aria-busy={busy}>Save name</button>
        {!err && greetName(profile) && <span className="hint">We greet you as {greetName(profile)}.</span>}</div>
    </form>
  )
}
