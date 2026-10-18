import { FILE_ACCEPT, FILE_HELP, fileProblem, mimeFor } from '../../lib/files'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { errorMessage, timeAgo } from '../../lib/api'
import { useEndpoint } from '../../lib/useEndpoint'
import { useToast } from '../Toast'
import Robot from '../Robot'

interface Material {
  id: string; title?: string; filename: string; kind?: 'pdf' | 'text' | 'paste'
  status: 'processing' | 'ready' | 'error'; summary?: string; pages?: number | null; truncated?: boolean; error?: string; addedAt?: string
}
interface MaterialsResponse { materials: Material[]; limit?: number; notice?: string }

const PDF_MAX = 10 * 1024 * 1024
const TEXT_MAX = 500 * 1024
const DEFAULT_NOTICE = "Upload only your own course materials: your notes, and slides or readings your instructor gave you for this class. Files stay private to you and this class, and are deleted when you delete the class or the file."

/** Slides, readings and notes the class agent answers from (MATERIALS_API.md). Plain text only; "coming soon" until the route exists. */
export default function MaterialsTab({ courseId, courseCode }: { courseId: string; courseCode: string }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const { data, state, reload } = useEndpoint<MaterialsResponse>(`/courses/${courseId}/materials`)
  const [busy, setBusy] = useState(false)
  const [over, setOver] = useState(false)
  const [mode, setMode] = useState<'files' | 'paste'>('files')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const input = useRef<HTMLInputElement>(null)

  // Poll while anything is still being read.
  const processing = (data?.materials ?? []).some(m => m.status === 'processing')
  useEffect(() => {
    if (!processing) return
    const t = window.setTimeout(reload, 3000)
    return () => window.clearTimeout(t)
  }, [processing, data, reload])

  async function upload(files: FileList | File[]) {
    setBusy(true)
    for (const f of Array.from(files)) {
      const problem = fileProblem(f)
      if (problem) { push('error', `Can't add ${f.name}`, problem); continue }
      try {
        const r = await authFetch(`/courses/${courseId}/materials`, { method: 'POST', body: JSON.stringify({ filename: f.name, contentType: mimeFor(f.name) }) })
        if (!r.ok) { push('error', `Couldn't add ${f.name}`, await errorMessage(r)); continue }
        const { upload: u } = await r.json()
        const form = new FormData()
        Object.entries((u?.fields ?? {}) as Record<string, string>).forEach(([k, v]) => form.append(k, v))
        form.append('file', f)
        const s3 = await fetch(u.url, { method: 'POST', body: form })
        if (!s3.ok) { push('error', `Couldn't upload ${f.name}`, 'The upload did not go through. Try again.'); continue }
        push('success', `${f.name} added`, 'Your agent is reading it now.')
      } catch { push('error', `Couldn't add ${f.name}`, 'Network problem. Try again.') }
    }
    setBusy(false); reload()
  }

  async function paste(e: React.FormEvent) {
    e.preventDefault(); setBusy(true)
    try {
      const r = await authFetch(`/courses/${courseId}/materials/text`, { method: 'POST', body: JSON.stringify({ title: title.trim(), text }) })
      if (!r.ok) { push('error', "Couldn't add your notes", await errorMessage(r)); return }
      push('success', 'Notes added', 'Your agent is reading them now.')
      setTitle(''); setText(''); reload()
    } catch { push('error', "Couldn't add your notes", 'Network problem. Try again.') } finally { setBusy(false) }
  }

  async function remove(m: Material) {
    try {
      const r = await authFetch(`/courses/${courseId}/materials/${m.id}`, { method: 'DELETE' })
      if (!r.ok) { push('error', "Couldn't remove it", await errorMessage(r)); return }
      push('success', 'Removed', m.title || m.filename); reload()
    } catch { push('error', "Couldn't remove it", 'Network problem. Try again.') }
  }

  if (state === 'loading') return <div className="skeleton-block" aria-busy="true" aria-label="Loading materials" />
  if (state === 'unavailable') return (
    <div className="empty"><Robot name="base" size={72} /><div className="empty-title">Materials are not available yet</div>
      <p className="empty-body">Soon you'll add slides, readings and notes here, and {courseCode || 'this class'}'s agent will answer from them and say which file it used.</p></div>
  )
  if (state === 'error') return <div className="warning" role="alert"><span>We couldn't load your materials.</span><button type="button" className="btn-ghost-sm" onClick={reload}>Try again</button></div>

  const list = data?.materials ?? []
  const textOk = title.trim().length >= 1 && text.trim().length >= 20 && text.length <= 100000
  return (
    <div className="stack">
      <p className="campus-note" role="note">{data?.notice || DEFAULT_NOTICE}</p>
      <div className="segmented" role="group" aria-label="How to add" style={{ alignSelf: 'flex-start' }}>
        <button type="button" aria-pressed={mode === 'files'} onClick={() => setMode('files')}>Upload files</button>
        <button type="button" aria-pressed={mode === 'paste'} onClick={() => setMode('paste')}>Paste notes</button>
      </div>

      {mode === 'files' ? (
        <div className={`dropzone${over ? ' is-over' : ''}`} onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files) }}>
          <strong>Drop slides, readings or notes</strong>
          <span>{FILE_HELP}. Up to 10 MB each (text files up to 500 KB).</span>
          <button type="button" className="btn-ghost" disabled={busy} onClick={() => input.current?.click()} aria-busy={busy}>Choose files</button>
          <input ref={input} type="file" accept={FILE_ACCEPT} multiple hidden onChange={e => { if (e.target.files) upload(e.target.files); e.target.value = '' }} />
        </div>
      ) : (
        <form className="card stack" onSubmit={paste}>
          <div className="field"><label htmlFor="mat-title">Title</label><input id="mat-title" maxLength={100} value={title} onChange={e => setTitle(e.target.value)} placeholder="My notes, week 4" /></div>
          <div className="field"><label htmlFor="mat-text">Notes</label><textarea id="mat-text" rows={8} value={text} onChange={e => setText(e.target.value)} placeholder="Paste your notes or reading here." /><span className="hint">{text.length.toLocaleString()} / 100,000 characters (at least 20)</span></div>
          <button type="submit" className="btn-primary" style={{ alignSelf: 'flex-start' }} disabled={!textOk || busy} aria-busy={busy}>Add notes</button>
        </form>
      )}

      {list.length === 0 ? <p className="muted">No materials yet. Add your lecture slides and the agent can quiz you from them and cite which file it used.</p> : (
        <ul className="stack" style={{ gap: 'var(--s-2)' }}>
          {list.map(m => (
            <li key={m.id} className="listing" style={{ gridTemplateColumns: '1fr auto' }}>
              <div>
                <strong>{m.title || m.filename}</strong>
                <div className="chip-row" style={{ marginTop: 'var(--s-1)' }}>
                  <span className={`badge ${m.status === 'ready' ? 'badge-ok' : m.status === 'error' ? 'badge-danger' : 'badge-info'}`} data-status={m.status === 'processing' ? 'building' : undefined}>{m.status === 'ready' ? 'Ready' : m.status === 'error' ? 'Failed' : 'Reading…'}</span>
                  {m.kind && <span className="chip chip-outline">{m.kind === 'paste' ? 'Pasted notes' : m.kind === 'pdf' ? 'PDF' : 'Text'}</span>}
                  {m.pages ? <span className="chip chip-outline">{m.pages} pages</span> : null}
                  {m.truncated ? <span className="chip chip-outline">Trimmed to the first part</span> : null}
                  {m.addedAt ? <span className="chip chip-outline">{timeAgo(m.addedAt)}</span> : null}
                </div>
                {m.status === 'error' && m.error && <p className="field-error" role="alert" style={{ marginTop: 'var(--s-1)' }}>{m.error}</p>}
                {m.summary && <p className="muted" style={{ fontSize: 'var(--text-sm)', marginTop: 'var(--s-1)' }}>{m.summary}</p>}
              </div>
              <button type="button" className="btn-ghost btn-sm" onClick={() => remove(m)} aria-label={`Remove ${m.title || m.filename}`}>Remove</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
