import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorMessage, timeAgo } from '../lib/api'
import { closedText, money, type ChatMessage, type Conversation } from '../lib/market'
import { useToast } from './Toast'
import Avatar, { MyAvatar } from './Avatar'

/** Inbox (polled every 30s) and a thread (polled every 5s, 15s after 2 quiet minutes, paused when the tab is hidden). Plain text only. */
export default function Conversations({ openId, onOpen }: { openId: string | null; onOpen: (id: string | null) => void }) {
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [list, setList] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await fetchRef.current('/conversations')
      if (!r.ok) throw new Error(String(r.status))
      setList((await r.json()).conversations ?? []); setError(false)
    } catch { setError(true) } finally { setLoading(false) }
  }, [])
  useEffect(() => {
    if (!user || openId) return
    load()
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') load() }, 30000)
    return () => window.clearInterval(t)
  }, [user, openId, load])

  if (openId) return <Thread id={openId} onBack={() => { onOpen(null); load() }} />

  if (loading) return <div className="skeleton-block" style={{ height: '8rem' }} aria-busy="true" aria-label="Loading messages" />
  if (error) return <div className="warning" role="alert"><span>We couldn't load your messages.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div>
  if (list.length === 0) return <div className="empty"><div className="empty-title">No messages yet</div><p className="empty-body">When you message a seller, or someone messages you about a listing, it shows up here.</p></div>
  return (
    <ul className="stack" style={{ gap: 'var(--s-2)' }}>
      {list.map(c => (
        <li key={c.id}>
          <button type="button" className="listing" style={{ width: '100%', textAlign: 'left' }} onClick={() => onOpen(c.id)}>
            <span className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start', gap: 'var(--s-3)' }}>
              <Avatar avatar={c.other.avatar} id={c.other.id ?? c.other.name} size={40} />
              <span>
              <strong>{c.listing.title}</strong>
              <span className="agenda-note" style={{ display: 'block' }}>{c.other.name} · {c.other.campus.shortName} · {c.role === 'buyer' ? 'You are buying' : 'You are selling'}</span>
              <span className="muted" style={{ display: 'block', fontSize: 'var(--text-sm)' }}>{c.status === 'closed' ? closedText(c.closedReason) : c.lastMessage ? `${c.lastMessage.from === 'me' ? 'You: ' : ''}${c.lastMessage.text}` : ''}</span>
              </span>
            </span>
            <span className="row" style={{ flexWrap: 'nowrap' }}>
              {c.unread > 0 && <span className="badge badge-count" aria-label={`${c.unread} unread`}>{c.unread}</span>}
              <span className="sys-time">{timeAgo(c.lastMessageAt)}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function Thread({ id, onBack }: { id: string; onBack: () => void }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [convo, setConvo] = useState<Conversation | null>(null)
  const [msgs, setMsgs] = useState<ChatMessage[]>([])
  const [missing, setMissing] = useState(false)
  const cursor = useRef<string | null>(null)
  const lastNew = useRef(Date.now())
  const [text, setText] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmBlock, setConfirmBlock] = useState(false)
  const end = useRef<HTMLDivElement>(null)

  const fetchMsgs = useCallback(async () => {
    try {
      const q = cursor.current ? `?after=${encodeURIComponent(cursor.current)}` : ''
      const r = await fetchRef.current(`/conversations/${id}${q}`)
      if (r.status === 404) { setMissing(true); return }
      if (!r.ok) return
      const j = await r.json()
      setConvo(j.conversation)
      if (j.messages?.length) {
        lastNew.current = Date.now()
        setMsgs(m => (cursor.current ? [...m, ...j.messages] : j.messages))
      }
      if (j.nextCursor) cursor.current = j.nextCursor
    } catch { /* keep polling */ }
  }, [id])

  useEffect(() => {
    cursor.current = null; setMsgs([]); setConvo(null); setMissing(false)
    fetchMsgs()
    let timer: number
    const tick = () => {
      const quiet = Date.now() - lastNew.current > 120000
      timer = window.setTimeout(() => { if (document.visibilityState === 'visible') fetchMsgs(); tick() }, quiet ? 15000 : 5000)
    }
    tick()
    const onVis = () => { if (document.visibilityState === 'visible') fetchMsgs() }
    document.addEventListener('visibilitychange', onVis)
    return () => { window.clearTimeout(timer); document.removeEventListener('visibilitychange', onVis) }
  }, [id, fetchMsgs])
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }) }, [msgs])

  async function send(e: React.FormEvent) {
    e.preventDefault()
    const t = text.trim()
    if (!t || busy) return
    setBusy(true); setErr('')
    try {
      const r = await authFetch(`/conversations/${id}/messages`, { method: 'POST', body: JSON.stringify({ text: t }) })
      if (!r.ok) { setErr(await errorMessage(r)); return }
      setText(''); lastNew.current = Date.now(); await fetchMsgs()
    } catch { setErr('Network problem. Try again.') } finally { setBusy(false) }
  }
  async function block() {
    try {
      const r = await authFetch(`/conversations/${id}/block`, { method: 'POST', body: '{}' })
      if (!r.ok) { push('error', "Couldn't block", await errorMessage(r)); return }
      push('success', 'Conversation closed'); setConfirmBlock(false); fetchMsgs()
    } catch { push('error', "Couldn't block", 'Network problem. Try again.') }
  }
  async function report() {
    try {
      const r = await authFetch(`/conversations/${id}/report`, { method: 'POST', body: JSON.stringify({ reason: 'other' }) })
      if (!r.ok) { push('error', "Couldn't send the report", await errorMessage(r)); return }
      push('success', 'Report sent', 'Thanks. Our team will take a look.')
    } catch { push('error', "Couldn't send the report", 'Network problem. Try again.') }
  }

  if (missing) return <div className="empty"><div className="empty-title">Conversation not found</div><button type="button" className="btn-primary" onClick={onBack}>Back to messages</button></div>

  return (
    <section className="window chat" aria-label="Conversation">
      <div className="window-bar">
        <button type="button" className="btn-ghost-sm" onClick={onBack}>‹ Messages</button>
        <span className="window-title">{convo ? `${convo.listing.title}${convo.listing.price !== undefined ? ` · ${money(convo.listing.price)}` : ''}` : 'Loading…'}</span>
        {convo && <span className="chip chip-outline" style={{ gap: 6 }}><Avatar avatar={convo.other.avatar} id={convo.other.id ?? convo.other.name} size={20} />{convo.other.name} · {convo.other.campus.shortName}</span>}
      </div>
      <p className="campus-note" style={{ padding: 'var(--s-3) var(--s-4) 0' }}>Meet in a public, well-lit campus spot. Use Buy now to pay securely in the app (demo checkout, no real money moves in this prototype). Don't share personal details.</p>
      <div className="chat-log" role="log" aria-live="polite" aria-label="Messages">
        {msgs.map(m => m.from === 'system'
          ? <div key={m.id} className="eyebrow" style={{ textAlign: 'center' }}>{m.text}</div>
          : <div key={m.id} className={`msg-row${m.from === 'me' ? ' msg-row--me' : ''}`}>{m.from === 'me' ? <MyAvatar size={28} /> : <Avatar avatar={convo?.other.avatar} id={convo?.other.id ?? convo?.other.name} size={28} />}<div className={`msg ${m.from === 'me' ? 'msg-user' : 'msg-agent'}`}>{m.text /* plain text only */}</div></div>)}
        <div ref={end} />
      </div>
      {convo && !convo.canSend ? (
        <div className="warning" style={{ margin: 'var(--s-3)' }} role="status">{closedText(convo.closedReason)}</div>
      ) : (
        <form className="chat-composer" onSubmit={send}>
          <input aria-label="Message" value={text} maxLength={1000} onChange={e => setText(e.target.value)} placeholder="Write a message (no links)" />
          <button type="submit" className="btn-primary" disabled={busy || !text.trim()} aria-busy={busy}>Send</button>
        </form>
      )}
      {err && <p className="field-error" role="alert" style={{ padding: '0 var(--s-4) var(--s-2)' }}>{err}</p>}
      <div className="window-foot">
        {confirmBlock
          ? <><span>Block this person? The conversation closes for both of you.</span><button type="button" className="btn-danger btn-sm" onClick={block}>Yes, block</button><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirmBlock(false)}>Cancel</button></>
          : <><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirmBlock(true)}>Block</button><button type="button" className="btn-ghost btn-sm" onClick={report}>Report</button></>}
      </div>
    </section>
  )
}
