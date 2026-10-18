import { useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { useCourses } from '../lib/useCourses'
import { useEndpoint } from '../lib/useEndpoint'
import { classIndexFromHex } from '../styles/color'
import { useToast } from './Toast'

interface Item {
  uid: string; title: string; description?: string; categories?: string[]; dueDate?: string | null; dueTime?: string | null
  type?: string; suggestions?: { courseId: string; courseCode: string; confidence: number }[]
}
/** Server-side grouping (when the backend sends it) or null: then the list is grouped here by title pattern. */
interface ServerGroup { key?: string; pattern?: string; title?: string; count?: number; uids?: string[]; items?: Item[]; suggestions?: Item['suggestions'] }
interface Group { key: string; label: string; items: Item[]; suggestions: NonNullable<Item['suggestions']> }

const when = (d?: string | null, t?: string | null) => {
  if (!d) return 'No date'
  const day = new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  return t ? `${day}, ${t}` : day
}

/** "Reading Journal 7", "Reading Journal 8" -> one pattern "reading journal #". Numbers, dates and times are removed. */
export function titlePattern(title: string): string {
  return title.toLowerCase()
    .replace(/\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b/g, ' ')
    .replace(/\b(week|wk|chapter|ch|module|unit|part|lab|hw|homework|quiz|assignment|problem set|pset|exam|journal|reading|discussion)\s*#?\d+\b/g, '$1 #')
    .replace(/\d+/g, '#').replace(/(#\s*)+/g, '#').replace(/\s+/g, ' ').trim()
}
const display = (title: string) => title.replace(/\s*[#(]?\s*\d+\)?\s*$/, '').trim() || title

function groupItems(list: Item[], server: ServerGroup[] | undefined): Group[] {
  if (server && server.length) {
    return server.map((g, i) => {
      const items = g.items ?? (g.uids ?? []).map(uid => list.find(x => x.uid === uid)).filter((x): x is Item => !!x)
      return { key: g.key ?? g.pattern ?? String(i), label: g.title ?? display(items[0]?.title ?? 'Items'), items, suggestions: g.suggestions ?? items[0]?.suggestions ?? [] }
    }).filter(g => g.items.length > 0)
  }
  const map = new Map<string, Item[]>()
  list.forEach(i => { const k = titlePattern(i.title); map.set(k, [...(map.get(k) ?? []), i]) })
  return [...map.entries()].map(([key, items]) => ({ key, label: display(items[0].title), items, suggestions: items[0].suggestions ?? [] }))
}

/**
 * The hero of the Blackboard feed: deadlines that don't say which class they belong to, grouped by title pattern so one tap
 * assigns a whole group ("Reading Journal x12"). Suggestions are only hints. All text is plain text.
 */
export default function UnassignedInbox({ onChanged, hero = false }: { onChanged: () => void; hero?: boolean }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const { courses } = useCourses()
  const { data, state, reload } = useEndpoint<{ unassigned: Item[]; groups?: ServerGroup[] }>('/feed/unassigned')
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const ready = courses.filter(c => c.status === 'READY')

  const groups = useMemo(() => (data ? groupItems(data.unassigned, data.groups) : []), [data])
  const total = data?.unassigned.length ?? 0

  async function assignGroup(g: Group, courseId: string) {
    setBusyKey(g.key); let done = 0, also = 0
    try {
      for (const i of g.items) {
        const r = await authFetch(`/feed/unassigned/${i.uid}/assign`, { method: 'POST', body: JSON.stringify({ courseId, remember: true }) })
        if (r.status === 404) continue // already placed by the rule learned from an earlier tap
        if (!r.ok) { push('error', "Couldn't add them", await errorMessage(r)); break }
        const j = await r.json(); done++; also += j.alsoAssigned ?? 0
      }
      if (done + also > 0) push('success', `Added ${done + also} deadline${done + also === 1 ? '' : 's'} to the class`, 'We will remember this for similar ones.')
      reload(); onChanged()
    } catch { push('error', "Couldn't add them", 'Network problem. Try again.') } finally { setBusyKey(null) }
  }
  async function dismissGroup(g: Group) {
    setBusyKey(g.key)
    try {
      for (const i of g.items) {
        const r = await authFetch(`/feed/unassigned/${i.uid}/dismiss`, { method: 'POST', body: '{}' })
        if (!r.ok && r.status !== 404) { push('error', "Couldn't dismiss them", await errorMessage(r)); break }
      }
      reload()
    } catch { push('error', "Couldn't dismiss them", 'Network problem. Try again.') } finally { setBusyKey(null) }
  }

  if (state !== 'ok' || !data || total === 0) return null
  const sorted = [...groups].sort((a, b) => b.items.length - a.items.length)
  return (
    <section className={`undated stack${hero ? ' unassigned-hero' : ''}`} aria-label="Sort your Blackboard deadlines" style={{ gap: 'var(--s-3)' }}>
      <div>
        <span className="eyebrow">From Blackboard · {total} to sort</span>
        {hero && <h2 style={{ fontSize: 'var(--text-lg)', margin: 'var(--s-1) 0' }}>Sort your deadlines into classes</h2>}
        <p className="muted">Blackboard doesn't say which class each deadline is for. Tap a class and the whole group goes there; we'll remember for next time.</p>
      </div>
      {sorted.map(g => {
        const top = g.suggestions[0]?.courseId
        const order = [...ready].sort((a, b) => (a.id === top ? -1 : b.id === top ? 1 : 0))
        const next = g.items.map(i => i.dueDate).filter(Boolean).sort()[0] as string | undefined
        const busy = busyKey === g.key
        return (
          <div key={g.key} className="card stack" style={{ gap: 'var(--s-2)' }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>{g.label}{g.items.length > 1 ? <span className="mono muted"> ×{g.items.length}</span> : null}</strong>
              <span className="chip chip-outline">{g.items.length > 1 ? `next due ${when(next)}` : when(g.items[0].dueDate, g.items[0].dueTime)}</span>
            </div>
            {g.items.length === 1 && g.items[0].description && <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>{g.items[0].description}</p>}
            {g.items.length > 1 && <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>{g.items.slice(0, 3).map(i => i.title).join(' · ')}{g.items.length > 3 ? ' …' : ''}</p>}
            {ready.length === 0
              ? <p className="muted">Add a class first (with its syllabus), then come back and tap it here.</p>
              : <div className="chip-row" role="group" aria-label={`Which class is "${g.label}" for?`}>
                {order.map(c => {
                  const idx = classIndexFromHex(c.color)
                  return <button key={c.id} type="button" disabled={busy} aria-busy={busy} className={c.id === top ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'} data-theme={idx >= 0 ? `c${idx}` : undefined} onClick={() => assignGroup(g, c.id)}>{c.courseCode || 'Class'}{c.id === top ? ' (likely)' : ''}</button>
                })}
                <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={() => dismissGroup(g)}>Not deadlines</button>
              </div>}
          </div>
        )
      })}
    </section>
  )
}
