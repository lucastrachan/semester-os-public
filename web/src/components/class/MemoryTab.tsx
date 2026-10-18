import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { errorMessage, timeAgo } from '../../lib/api'
import { useEndpoint } from '../../lib/useEndpoint'
import { useToast } from '../Toast'
import Robot from '../Robot'

interface Note { id: string; text: string; createdAt?: string; source?: 'agent' | 'student' | 'summary' }
interface MemoryResponse { notes: Note[]; limit?: number; count?: number }

const SOURCE_LABEL: Record<string, string> = { agent: 'Agent noted', student: 'You added', summary: 'Summary' }

/** What the class agent remembers about the student (MEMORY_API.md). Always visible, editable and deletable. */
export default function MemoryTab({ courseId, courseCode }: { courseId: string; courseCode: string }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const { data, state, reload } = useEndpoint<MemoryResponse>(`/courses/${courseId}/memory`)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [adding, setAdding] = useState('')
  const [err, setErr] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)

  async function add(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    try {
      const r = await authFetch(`/courses/${courseId}/memory`, { method: 'POST', body: JSON.stringify({ text: adding.trim() }) })
      if (!r.ok) { setErr(await errorMessage(r, "Couldn't save that note.")); return }
      setAdding(''); reload()
    } catch { setErr('Network problem. Try again.') }
  }
  async function save(n: Note) {
    try {
      const r = await authFetch(`/courses/${courseId}/memory/${n.id}`, { method: 'PATCH', body: JSON.stringify({ text: draft.trim() }) })
      if (!r.ok) { push('error', "Couldn't save the note", await errorMessage(r)); return }
      setEditing(null); reload()
    } catch { push('error', "Couldn't save the note", 'Network problem. Try again.') }
  }
  async function remove(n: Note) {
    try {
      const r = await authFetch(`/courses/${courseId}/memory/${n.id}`, { method: 'DELETE' })
      if (!r.ok) { push('error', "Couldn't delete the note", await errorMessage(r)); return }
      reload()
    } catch { push('error', "Couldn't delete the note", 'Network problem. Try again.') }
  }
  async function clearAll() {
    try {
      const r = await authFetch(`/courses/${courseId}/memory`, { method: 'DELETE' })
      if (!r.ok) { push('error', "Couldn't clear memory", await errorMessage(r)); return }
      push('success', 'Memory cleared'); setConfirmClear(false); reload()
    } catch { push('error', "Couldn't clear memory", 'Network problem. Try again.') }
  }

  if (state === 'loading') return <div className="skeleton-block" aria-busy="true" aria-label="Loading memory" />
  if (state === 'unavailable') return (
    <div className="empty"><Robot name="base" size={72} /><div className="empty-title">Memory is not available yet</div>
      <p className="empty-body">{courseCode || 'This class'}'s agent will keep short notes about what you've covered and how you like to study. You'll be able to read, edit and delete every note.</p></div>
  )
  if (state === 'error') return <div className="warning" role="alert"><span>We couldn't load memory.</span><button type="button" className="btn-ghost-sm" onClick={reload}>Try again</button></div>

  const notes = data?.notes ?? []
  const limit = data?.limit ?? 40
  return (
    <div className="stack">
      <p className="muted">These are the notes this agent keeps about you for this class. It only saves short facts about your progress and preferences, never links, contact details or passwords. You're in control: edit or delete anything.</p>
      <span className="eyebrow" role="status">{notes.length} of {limit} notes</span>

      {notes.length === 0 ? <div className="empty"><div className="empty-title">Nothing remembered yet</div><p className="empty-body">As you study, the agent adds short notes here, like which topics you've mastered. You can add your own too.</p></div> : (
        <ul className="stack" style={{ gap: 'var(--s-2)' }}>
          {notes.map(n => (
            <li key={n.id} className="listing" style={{ gridTemplateColumns: '1fr auto' }}>
              {editing === n.id ? (
                <div className="field" style={{ gridColumn: '1 / -1' }}>
                  <label htmlFor={`n-${n.id}`} className="sr-only">Edit note</label>
                  <textarea id={`n-${n.id}`} rows={2} maxLength={280} value={draft} onChange={e => setDraft(e.target.value)} />
                  <div className="row"><button type="button" className="btn-primary btn-sm" disabled={!draft.trim()} onClick={() => save(n)}>Save</button><button type="button" className="btn-ghost btn-sm" onClick={() => setEditing(null)}>Cancel</button></div>
                </div>
              ) : (
                <>
                  <div>
                    <span>{n.text}</span>
                    <div className="agenda-note">{[n.source ? SOURCE_LABEL[n.source] : '', n.createdAt ? timeAgo(n.createdAt) : ''].filter(Boolean).join(' · ')}</div>
                  </div>
                  <div className="row"><button type="button" className="btn-ghost btn-sm" onClick={() => { setEditing(n.id); setDraft(n.text) }}>Edit</button><button type="button" className="btn-ghost btn-sm" onClick={() => remove(n)} aria-label={`Delete note: ${n.text.slice(0, 40)}`}>Delete</button></div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      <form className="stack" style={{ gap: 'var(--s-2)' }} onSubmit={add}>
        <div className="field">
          <label htmlFor="add-note">Add a note yourself</label>
          <input id="add-note" value={adding} maxLength={280} disabled={notes.length >= limit} onChange={e => setAdding(e.target.value)} placeholder="Exam 2 is open-notes" />
          <span className="hint">{notes.length >= limit ? 'Memory is full. Delete a note to add another.' : 'One short fact, up to 280 characters.'}</span>
        </div>
        {err && <p className="field-error" role="alert">{err}</p>}
        <button type="submit" className="btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} disabled={!adding.trim() || notes.length >= limit}>Add note</button>
      </form>

      {notes.length > 0 && (confirmClear
        ? <div className="row"><span>Clear everything this agent remembers?</span><button type="button" className="btn-danger btn-sm" onClick={clearAll}>Yes, clear it</button><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirmClear(false)}>Keep</button></div>
        : <button type="button" className="btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setConfirmClear(true)}>Clear all memory</button>)}
    </div>
  )
}
