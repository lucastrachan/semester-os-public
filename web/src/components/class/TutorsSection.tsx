import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../lib/api'
import { useEndpoint } from '../../lib/useEndpoint'
import type { ListingV2 } from '../../lib/market'
import Drawer from '../market/Drawer'
import { ListingDetail, MarketCard, type ChatStarter } from '../market/MarketCards'

/** "Tutors for MIS 430": peer tutors tagged with this class (GET /courses/{id}/tutors). "Request a session" opens the listing chat. */
export default function TutorsSection({ courseId, courseCode }: { courseId: string; courseCode: string }) {
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const { data, state } = useEndpoint<{ tutors: ListingV2[] }>(`/courses/${courseId}/tutors`)
  const [selected, setSelected] = useState<ListingV2 | null>(null)

  const chat: ChatStarter = useCallback(async (l, message) => {
    try {
      const r = await authFetch(`/listings/${l.id}/conversations`, { method: 'POST', body: JSON.stringify({ message }) })
      if (!r.ok) return await errorMessage(r)
      const j = await r.json()
      navigate(`/marketplace?convo=${encodeURIComponent(j.conversation.id)}`)
      return null
    } catch { return 'Network problem. Try again.' }
  }, [authFetch, navigate])

  if (state !== 'ok') return null // not deployed or failed: stay quiet, this is a bonus section
  const tutors = data?.tutors ?? []
  return (
    <section aria-labelledby="tutors-h" className="stack" style={{ gap: 'var(--s-2)', marginTop: 'var(--s-4)' }}>
      <div className="section-head"><h2 id="tutors-h" style={{ fontSize: 'var(--text-md)' }}>Tutors for {courseCode}</h2></div>
      {tutors.length === 0
        ? <p className="muted">No peer tutors for this class yet. Know it well? Offer tutoring in the Marketplace.</p>
        : <div className="mk-grid">{tutors.map(t => <MarketCard key={t.id} l={t} onOpen={setSelected} />)}</div>}
      <Drawer open={!!selected} title="Tutor" onClose={() => setSelected(null)}>{selected && <ListingDetail l={selected} onChat={chat} />}</Drawer>
    </section>
  )
}
