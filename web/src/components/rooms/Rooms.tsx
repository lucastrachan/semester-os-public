import Avatar, { MyAvatar } from '../Avatar'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { errorMessage, timeAgo } from '../../lib/api'
import { useCourses } from '../../lib/useCourses'
import { dayLabel, messageProblem, ROOM_NOTICE, timeOf, type Room, type RoomMessage } from '../../lib/rooms'
import { classIndexFromHex } from '../../styles/color'
import Robot from '../Robot'
import { useToast } from '../Toast'

type AuthFetch = (path: string, init?: RequestInit) => Promise<Response>

/* ---------------- list ---------------- */
export function RoomList({ onOpen, onUnread, onLoaded }: { onOpen: (r: Room) => void; onUnread?: (n: number) => void; onLoaded?: (r: Room[]) => void }) {
  const { authFetch, user } = useAuth()
  const { courses } = useCourses()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [rooms, setRooms] = useState<Room[] | null>(null)
  const [state, setState] = useState<'ok' | 'unavailable' | 'error'>('ok')
  const [showLeft, setShowLeft] = useState(false)
  const [banner, setBanner] = useState(() => { try { return localStorage.getItem('rooms-banner') !== '1' } catch { return true } })

  const load = useCallback(async () => {
    try {
      const r = await fetchRef.current(`/rooms${showLeft ? '?includeLeft=true' : ''}`)
      if ([401, 403, 404, 405, 501].includes(r.status)) { setState('unavailable'); setRooms([]); return }
      if (!r.ok) throw new Error(String(r.status))
      const j = await r.json()
      setRooms(j.rooms ?? []); setState('ok'); onUnread?.(j.unreadTotal ?? 0); onLoaded?.(j.rooms ?? [])
    } catch { setState('error') }
  }, [showLeft]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!user) return
    load()
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') load() }, 30000)
    return () => window.clearInterval(t)
  }, [user, load])

  const colorFor = (r: Room) => {
    const c = courses.find(x => (x.courseCode ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '') === r.code)
    const i = c ? classIndexFromHex(c.color) : -1
    return i >= 0 ? `c${i}` : undefined
  }
  const dismiss = () => { setBanner(false); try { localStorage.setItem('rooms-banner', '1') } catch { /* storage unavailable */ } }

  if (state === 'unavailable') return <div className="empty"><Robot name="base" size={72} /><div className="empty-title">Class chats are coming soon</div><p className="empty-body">Soon every class you add gets a chat for classmates who added it too.</p></div>
  if (state === 'error') return <div className="warning" role="alert"><span>We couldn't load your class chats.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div>
  if (!rooms) return <div className="skeleton-block" aria-busy="true" aria-label="Loading class chats" />

  return (
    <div className="stack">
      {banner && (
        <div className="campus-note row" role="note" style={{ justifyContent: 'space-between' }}>
          <span>{ROOM_NOTICE}</span><button type="button" className="btn-ghost-sm" onClick={dismiss}>Got it</button>
        </div>
      )}
      {rooms.length === 0 ? (
        <div className="empty"><Robot name="class-tutor" size={72} /><div className="empty-title">Add a class to join its chat</div><p className="empty-body">Each class you add gets a chat with classmates who added it too.</p><Link className="btn-primary" to="/study">Go to Study</Link></div>
      ) : (
        <ul className="stack" style={{ gap: 'var(--s-2)' }}>
          {rooms.map(r => (
            <li key={r.id}>
              <button type="button" className="listing" data-theme={colorFor(r)} style={{ width: '100%', textAlign: 'left', borderLeft: '4px solid var(--accent)' }} onClick={() => onOpen(r)}>
                <span>
                  <strong>{r.displayCode}</strong> <span className="muted">· {r.memberCount} classmate{r.memberCount === 1 ? '' : 's'}{r.title ? ` · ${r.title}` : ''}</span>
                  <span className="muted" style={{ display: 'block', fontSize: 'var(--text-sm)' }}>{r.left ? 'You left this chat' : r.lastMessage ? `${r.lastMessage.from === 'me' ? 'You' : r.lastMessage.name}: ${r.lastMessage.text}` : 'No messages yet. Say hi.'}</span>
                </span>
                <span className="row" style={{ flexWrap: 'nowrap' }}>
                  {r.muted && <span className="chip chip-outline">Muted</span>}
                  {r.unread > 0 && !r.muted && <span className="badge badge-count" aria-label={`${r.unread} unread`}>{r.unread}</span>}
                  {r.lastMessageAt && <span className="sys-time">{timeAgo(r.lastMessageAt)}</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setShowLeft(s => !s)}>{showLeft ? 'Hide chats I left' : 'Show chats I left'}</button>
    </div>
  )
}

/* ---------------- room ---------------- */
async function roomError(r: Response): Promise<string> {
  let code = ''; try { code = (await r.clone().json()).error } catch { /* none */ }
  if (code === 'room_left') return 'You left this chat. Rejoin it to read and post.'
  if (code === 'room_closed') return 'This chat is closed.'
  if (r.status === 429) return 'Slow down a little: you can send about 12 messages a minute.'
  return errorMessage(r)
}

export function RoomView({ room, onBack, onChanged }: { room: Room; onBack: () => void; onChanged: () => void }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const fetchRef = useRef<AuthFetch>(authFetch)
  fetchRef.current = authFetch
  const [info, setInfo] = useState<Room>(room)
  const [msgs, setMsgs] = useState<RoomMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState('')
  const cursor = useRef<string | null>(null)
  const lastNew = useRef(Date.now())
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [menu, setMenu] = useState(false)
  const [target, setTarget] = useState<RoomMessage | null>(null) // message being reported or blocked
  const [reporting, setReporting] = useState<null | 'room' | 'message'>(null)
  const end = useRef<HTMLDivElement>(null)

  const fetchMsgs = useCallback(async () => {
    try {
      const q = cursor.current ? `?after=${encodeURIComponent(cursor.current)}` : ''
      const r = await fetchRef.current(`/rooms/${room.id}/messages${q}`)
      if (!r.ok) { setFailed(await roomError(r)); setLoading(false); return }
      const j = await r.json()
      setFailed(''); if (j.room) setInfo(j.room)
      if (j.messages?.length) { lastNew.current = Date.now(); setMsgs(m => (cursor.current ? [...m, ...j.messages] : j.messages)) }
      if (j.nextCursor) cursor.current = j.nextCursor
      setLoading(false)
    } catch { setLoading(false) }
  }, [room.id])

  useEffect(() => {
    cursor.current = null; setMsgs([]); setLoading(true); fetchMsgs()
    let timer: number
    const tick = () => { const quiet = Date.now() - lastNew.current > 120000; timer = window.setTimeout(() => { if (document.visibilityState === 'visible') fetchMsgs(); tick() }, quiet ? 15000 : 5000) }
    tick()
    const onVis = () => { if (document.visibilityState === 'visible') fetchMsgs() }
    document.addEventListener('visibilitychange', onVis)
    return () => { window.clearTimeout(timer); document.removeEventListener('visibilitychange', onVis) }
  }, [room.id, fetchMsgs])
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }) }, [msgs])

  const problem = messageProblem(text)
  async function send(e: React.FormEvent) {
    e.preventDefault()
    const t = text.trim()
    if (!t || busy || problem) return
    setBusy(true); setErr('')
    try {
      const r = await authFetch(`/rooms/${room.id}/messages`, { method: 'POST', body: JSON.stringify({ text: t }) })
      if (!r.ok) { setErr(await roomError(r)); return }
      setText(''); lastNew.current = Date.now(); await fetchMsgs()
    } catch { setErr('Network problem. Try again.') } finally { setBusy(false) }
  }

  async function act(path: string, body: Record<string, unknown> | null, done: string, after?: () => void) {
    try {
      const r = await authFetch(`/rooms/${room.id}/${path}`, { method: 'POST', body: JSON.stringify(body ?? {}) })
      if (!r.ok) { push('error', "That didn't work", await roomError(r)); return }
      push('success', done); setMenu(false); after?.(); onChanged()
    } catch { push('error', "That didn't work", 'Network problem. Try again.') }
  }
  const report = (reason: string) => act('report', { reason, ...(reporting === 'message' && target ? { messageId: target.id } : {}) }, 'Report sent. Thank you.', () => { setReporting(null); setTarget(null) })

  let lastDay = '', lastName = ''
  return (
    <section className="window chat" aria-label={`${info.displayCode} class chat`}>
      <div className="window-bar">
        <button type="button" className="btn-ghost-sm" onClick={onBack}>‹ Messages</button>
        <span className="window-title">{info.displayCode} chat · {info.memberCount} classmate{info.memberCount === 1 ? '' : 's'}</span>
        <button type="button" className="btn-ghost-sm" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(m => !m)}>⋯ Options</button>
      </div>
      {menu && (
        <div className="row" role="menu" style={{ padding: 'var(--s-2) var(--s-4)', borderBottom: '1px solid var(--border)' }}>
          {info.left
            ? <button type="button" role="menuitem" className="btn-ghost btn-sm" onClick={() => act('rejoin', null, 'You rejoined the chat')}>Rejoin chat</button>
            : <>
              <button type="button" role="menuitem" className="btn-ghost btn-sm" onClick={() => act(info.muted ? 'unmute' : 'mute', null, info.muted ? 'Unmuted' : 'Muted', () => setInfo(i => ({ ...i, muted: !i.muted })))}>{info.muted ? 'Unmute' : 'Mute'}</button>
              <button type="button" role="menuitem" className="btn-ghost btn-sm" onClick={() => act('leave', null, 'You left the chat', onBack)}>Leave chat</button>
              <button type="button" role="menuitem" className="btn-ghost btn-sm" onClick={() => { setReporting('room'); setTarget(null); setMenu(false) }}>Report this chat</button>
            </>}
        </div>
      )}
      <p className="campus-note" style={{ padding: 'var(--s-3) var(--s-4) 0' }}>Classmates who added this class. Be kind, share no personal info. Enrollment is not verified.</p>

      {reporting && (
        <div className="row" role="group" aria-label="Report" style={{ padding: 'var(--s-3) var(--s-4)' }}>
          <span className="muted">{reporting === 'message' ? `Report ${target?.name}'s message as:` : 'Report this chat as:'}</span>
          {[['harassment', 'Harassment'], ['spam', 'Spam'], ['scam', 'Scam'], ['inappropriate', 'Inappropriate'], ['other', 'Other']].map(([v, t]) => <button key={v} type="button" className="btn-ghost btn-sm" onClick={() => report(v)}>{t}</button>)}
          <button type="button" className="btn-ghost btn-sm" onClick={() => { setReporting(null); setTarget(null) }}>Cancel</button>
        </div>
      )}

      <div className="chat-log" role="log" aria-live="polite" aria-label="Class chat messages">
        {loading && <div className="skeleton-block" aria-busy="true" style={{ height: '5rem' }} />}
        {failed && <div className="warning" role="alert">{failed}</div>}
        {!loading && !failed && msgs.length === 0 && <p className="muted">No messages yet. Say hi to your classmates.</p>}
        {msgs.map(m => {
          const day = dayLabel(m.at); const showDay = day !== lastDay; lastDay = day
          const showName = showDay || m.name !== lastName || m.from === 'me'; lastName = m.name
          return (
            <div key={m.id} className="stack" style={{ gap: 2, alignItems: m.from === 'me' ? 'flex-end' : 'flex-start' }}>
              {showDay && <div className="eyebrow" style={{ alignSelf: 'center', margin: 'var(--s-2) 0' }}>{day}</div>}
              {showName && m.from === 'them' && <span className="msg-meta">{m.name}</span>}
              <div className={`msg-row${m.from === 'me' ? ' msg-row--me' : ''}`}>
                {m.from === 'me' ? <MyAvatar size={28} /> : <Avatar avatar={m.avatar} id={m.userId ?? m.name} size={28} />}
                <div className={`msg ${m.from === 'me' ? 'msg-user' : 'msg-agent'}`}>
                  {m.text /* plain text only, never HTML, never auto-linked */}
                  <span className="msg-meta" style={{ display: 'block', opacity: 0.8, marginTop: 2 }}>{timeOf(m.at)}</span>
                </div>
              </div>
              {m.from === 'them' && (
                <span className="row" style={{ gap: 'var(--s-2)' }}>
                  <button type="button" className="link-btn" style={{ fontSize: 'var(--text-xs)' }} onClick={() => { setTarget(m); setReporting('message') }} aria-label={`Report ${m.name}'s message`}>Report</button>
                  <button type="button" className="link-btn" style={{ fontSize: 'var(--text-xs)' }} onClick={() => act('block', { messageId: m.id }, `${m.name} is hidden for you`, fetchMsgs)} aria-label={`Block ${m.name}`}>Block</button>
                </span>
              )}
            </div>
          )
        })}
        <div ref={end} />
      </div>

      {info.left ? <p className="warning" style={{ margin: 'var(--s-3)' }}>You left this chat. Use Options to rejoin.</p> : info.canSend === false || info.closed ? <p className="warning" style={{ margin: 'var(--s-3)' }}>This chat is closed.</p> : (
        <form className="chat-composer" onSubmit={send} style={{ flexWrap: 'wrap' }}>
          <input aria-label="Message the class" value={text} maxLength={500} onChange={e => setText(e.target.value)} placeholder="Write a message (plain text, no links)" aria-invalid={!!problem} />
          <button type="submit" className="btn-primary" disabled={busy || !text.trim() || !!problem} aria-busy={busy}>Send</button>
          <span className="hint" style={{ flexBasis: '100%', color: problem ? 'var(--danger)' : undefined }} role={problem ? 'alert' : undefined}>{problem || `${text.length}/500 · Plain text only: no links, photos or personal info.`}</span>
        </form>
      )}
      {err && <p className="field-error" role="alert" style={{ padding: '0 var(--s-4) var(--s-3)' }}>{err}</p>}
    </section>
  )
}
