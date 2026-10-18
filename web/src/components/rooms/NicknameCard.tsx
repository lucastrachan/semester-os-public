import { useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../lib/api'
import { useEndpoint } from '../../lib/useEndpoint'
import { useToast } from '../Toast'

/** The name classmates see in class chats. Never your real name or email. */
export default function NicknameCard() {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const { data, state, reload } = useEndpoint<{ nickname: string; isDefault: boolean }>('/me/nickname')
  const [value, setValue] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (data) setValue(data.nickname) }, [data])

  async function save(nickname: string | null) {
    setBusy(true); setErr('')
    try {
      const r = await authFetch('/me/nickname', { method: 'PATCH', body: JSON.stringify({ nickname }) })
      if (!r.ok) { setErr(await errorMessage(r, 'Use 2 to 24 letters, digits or spaces, with no links or @.')); return }
      push('success', nickname ? 'Nickname saved' : 'Back to your default nickname'); reload()
    } catch { setErr('Network problem. Try again.') } finally { setBusy(false) }
  }

  if (state === 'unavailable') return null // class chats not deployed yet: no card
  return (
    <section className="window" aria-label="Class chat nickname">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">class-chat-nickname</span></div>
      <div className="window-body stack">
        <p className="muted">Classmates in your class chats see only this nickname, never your name or email.</p>
        {state === 'loading' ? <div className="skeleton-line" aria-busy="true" /> : state === 'error' ? <p className="field-error" role="alert">We couldn't load your nickname.</p> : (
          <form className="stack" onSubmit={e => { e.preventDefault(); save(value.trim()) }}>
            <div className="field"><label htmlFor="nick">Nickname</label><input id="nick" value={value} minLength={2} maxLength={24} onChange={e => setValue(e.target.value)} /><span className="hint">2 to 24 characters: letters, digits, spaces, . _ - ' only.</span></div>
            {err && <p className="field-error" role="alert">{err}</p>}
            <div className="row"><button type="submit" className="btn-primary btn-sm" disabled={busy || value.trim().length < 2 || value.trim() === data?.nickname} aria-busy={busy}>Save</button>
              {data && !data.isDefault && <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={() => save(null)}>Use the default again</button>}</div>
          </form>
        )}
      </div>
    </section>
  )
}
