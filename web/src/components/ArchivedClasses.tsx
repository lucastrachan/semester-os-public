import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import type { Course } from '../lib/api'
import { setArchived } from '../lib/archive'
import { useToast } from './Toast'

/** Settings: classes the student hid. Restore puts one back in Study, Today and Calendar. Defensive about the server shape. */
export default function ArchivedClasses({ onRestored }: { onRestored: () => void }) {
  const { authFetch, user } = useAuth()
  const { push } = useToast()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [list, setList] = useState<Course[] | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading')
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await fetchRef.current('/courses?archived=true')
      if (!r.ok) throw new Error(String(r.status))
      const j = await r.json()
      setList((Array.isArray(j.courses) ? (j.courses as Course[]) : []).filter(c => c.archived === true))
      setState('ok')
    } catch { setState('error') }
  }, [])
  useEffect(() => { if (user) load() }, [user, load])

  async function restore(c: Course) {
    setBusy(c.id)
    const problem = await setArchived(fetchRef.current, c.id, false)
    setBusy(null)
    if (problem) { push('error', "Couldn't restore the class", problem); return }
    push('success', 'Class restored', `${c.courseCode || 'The class'} is back in Study.`)
    await load(); onRestored()
  }

  const when = (iso?: string) => { const d = iso ? new Date(iso) : null; return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '' }

  return (
    <section className="window" aria-label="Archived classes">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">archived-classes</span></div>
      <div className="window-body stack">
        <p className="muted">Archived classes are hidden from Study, Today and Calendar. Restore one to bring it back with everything it knows.</p>
        {state === 'loading' ? <div className="skeleton-line" aria-busy="true" />
          : state === 'error' ? <p className="muted">Archived classes aren't available right now.</p>
          : !list || list.length === 0 ? <p className="muted">No archived classes.</p>
          : (
            <ul className="stack" style={{ gap: 'var(--s-2)' }}>
              {list.map(c => (
                <li key={c.id} className="listing" style={{ gridTemplateColumns: '1fr auto' }}>
                  <span><strong>{c.courseCode || 'Class'}</strong> <span className="muted">{c.title}</span>{when(c.archivedAt) && <span className="muted" style={{ display: 'block', fontSize: 'var(--text-sm)' }}>Archived {when(c.archivedAt)}</span>}</span>
                  <button type="button" className="btn-ghost btn-sm" onClick={() => restore(c)} disabled={busy === c.id} aria-busy={busy === c.id} aria-label={`Restore ${c.courseCode || 'class'}`}>Restore</button>
                </li>
              ))}
            </ul>
          )}
      </div>
    </section>
  )
}
