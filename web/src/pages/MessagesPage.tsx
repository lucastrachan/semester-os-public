import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Conversations from '../components/Conversations'
import { RoomList, RoomView } from '../components/rooms/Rooms'
import { normCode, type Room } from '../lib/rooms'

type Seg = 'rooms' | 'market'

/** One Messages area: class chats (classmates who added a class) and marketplace chats (per listing). */
export default function MessagesPage() {
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [params] = useSearchParams()
  const [seg, setSeg] = useState<Seg>(params.get('seg') === 'market' || params.get('convo') ? 'market' : 'rooms')
  const [room, setRoom] = useState<Room | null>(null)
  const [convo, setConvo] = useState<string | null>(params.get('convo'))
  const [roomUnread, setRoomUnread] = useState(0)
  const [marketUnread, setMarketUnread] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const wantCode = params.get('code') ? normCode(params.get('code') as string) : ''

  useEffect(() => {
    if (!user) return
    let alive = true
    const poll = async () => {
      if (document.visibilityState !== 'visible') return
      try { const r = await fetchRef.current('/conversations/unread'); if (r.ok && alive) setMarketUnread((await r.json()).unread ?? 0) } catch { /* ignore */ }
    }
    poll()
    const t = window.setInterval(poll, 60000)
    return () => { alive = false; window.clearInterval(t) }
  }, [user])

  const onLoaded = useCallback((rooms: Room[]) => {
    if (wantCode && !room) { const m = rooms.find(r => r.code === wantCode); if (m) setRoom(m) }
  }, [wantCode, room])

  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">Messages</span>
        <h1>Class chats and marketplace chats</h1>
        <div className="segmented" role="tablist" aria-label="Messages" style={{ alignSelf: 'flex-start' }}>
          <button role="tab" type="button" aria-selected={seg === 'rooms'} aria-pressed={seg === 'rooms'} onClick={() => setSeg('rooms')}>Class chats{roomUnread > 0 ? ` (${roomUnread})` : ''}</button>
          <button role="tab" type="button" aria-selected={seg === 'market'} aria-pressed={seg === 'market'} onClick={() => { setSeg('market'); setConvo(null) }}>Marketplace{marketUnread > 0 ? ` (${marketUnread})` : ''}</button>
        </div>
      </div>

      {seg === 'rooms' && (room
        ? <RoomView key={room.id} room={room} onBack={() => { setRoom(null); setRefresh(n => n + 1) }} onChanged={() => setRefresh(n => n + 1)} />
        : <RoomList key={refresh} onOpen={setRoom} onUnread={setRoomUnread} onLoaded={onLoaded} />)}
      {seg === 'market' && <Conversations openId={convo} onOpen={setConvo} />}
    </div>
  )
}
