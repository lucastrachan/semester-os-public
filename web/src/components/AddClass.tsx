import { FILE_ACCEPT, FILE_HELP, fileProblem, mimeFor } from '../lib/files'
import { useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { useToast } from './Toast'
import { sampleSyllabus } from '../lib/sampleSyllabus'

const MAX_BYTES = 10 * 1024 * 1024
type Row = { name: string; state: 'uploading' | 'done' | 'error'; message?: string }

export default function AddClass({ onAdded, onClose, startTab = 'pdf', embedded = false }: { onAdded: () => void; onClose: () => void; startTab?: 'pdf' | 'text'; embedded?: boolean }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const [tab, setTab] = useState<'pdf' | 'text'>(startTab)
  const [over, setOver] = useState(false)
  const [rows, setRows] = useState<Row[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const setRow = (i: number, patch: Partial<Row>) => setRows(rs => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)))

  async function uploadOne(file: File, index: number) {
    const problem = fileProblem(file)
    if (problem) return setRow(index, { state: 'error', message: problem })
    try {
      const r = await authFetch('/courses', { method: 'POST', body: JSON.stringify({ filename: file.name, contentType: mimeFor(file.name) }) })
      if (!r.ok) return setRow(index, { state: 'error', message: await errorMessage(r) })
      const { upload } = await r.json()
      // Presigned POST: every field first, the file last, named "file". No auth header goes to S3.
      const form = new FormData()
      Object.entries(upload.fields as Record<string, string>).forEach(([k, v]) => form.append(k, v))
      form.append('file', file)
      const s3 = await fetch(upload.url, { method: 'POST', body: form })
      if (!s3.ok) return setRow(index, { state: 'error', message: "The upload didn't go through. Try again." })
      setRow(index, { state: 'done' })
    } catch {
      setRow(index, { state: 'error', message: 'Network problem. Try again.' })
    }
  }

  async function addFiles(files: FileList | File[]) {
    const list = Array.from(files)
    if (!list.length) return
    const start = rows.length
    setRows(rs => [...rs, ...list.map(f => ({ name: f.name, state: 'uploading' as const }))])
    setBusy(true)
    for (let i = 0; i < list.length; i++) await uploadOne(list[i], start + i) // one at a time: friendly to the daily cap
    setBusy(false)
    onAdded()
  }

  async function submitText(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await authFetch('/courses', { method: 'POST', body: JSON.stringify({ text }) })
      if (!r.ok) { push('error', "Couldn't add the class", await errorMessage(r)); return }
      push('success', 'Class added', 'Your agent is building now.')
      setText('')
      onAdded()
      onClose()
    } catch {
      push('error', "Couldn't add the class", 'Network problem. Try again.')
    } finally { setBusy(false) }
  }

  const textOk = text.trim().length >= 50 && text.length <= 60000
  // Demo helper: a clearly fictional syllabus with dates relative to today.
  const useSample = () => { setText(sampleSyllabus()); setTab('text') }

  return (
    <section className="window" aria-label="Add a class">
      <div className="window-bar">
        <span className="window-dots" aria-hidden="true"><i /><i /><i /></span>
        <span className="window-title">add-class</span>
        {!embedded && <button type="button" className="btn-ghost-sm" onClick={onClose}>Close</button>}
      </div>
      <div className="window-body stack">
        <div className="tabs" role="tablist" aria-label="How to add a class">
          <button role="tab" type="button" className="tab" aria-selected={tab === 'pdf'} onClick={() => setTab('pdf')}>Syllabus PDFs</button>
          <button role="tab" type="button" className="tab" aria-selected={tab === 'text'} onClick={() => setTab('text')}>Paste text</button>
        </div>

        {tab === 'pdf' ? (
          <>
            <div
              className={`dropzone${over ? ' is-over' : ''}`}
              onDragOver={e => { e.preventDefault(); setOver(true) }}
              onDragLeave={() => setOver(false)}
              onDrop={e => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files) }}
            >
              <strong>Drop syllabus files here</strong>
              <span>{FILE_HELP}. One class per file, up to 10 MB each. You can add several at once.</span>
              <button type="button" className="btn-ghost" disabled={busy} onClick={() => input.current?.click()}>Choose files</button>
              <button type="button" className="link-btn" onClick={useSample}>No syllabus handy? Try a sample</button>
              <input ref={input} type="file" accept={FILE_ACCEPT} multiple hidden onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = '' }} />
            </div>
            {rows.length > 0 && (
              <ul className="stack" style={{ gap: 'var(--s-2)' }} aria-live="polite">
                {rows.map((r, i) => (
                  <li key={i} className="row">
                    <span className="grow truncate">{r.name}</span>
                    <span className={`badge ${r.state === 'error' ? 'badge-danger' : r.state === 'done' ? 'badge-ok' : 'badge-info'}`}>
                      {r.state === 'uploading' ? 'Uploading' : r.state === 'done' ? 'Building' : 'Failed'}
                    </span>
                    {r.message && <span className="field-error" style={{ flexBasis: '100%' }}>{r.message}</span>}
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <form className="stack" onSubmit={submitText}>
            <div className="field">
              <div className="row" style={{ justifyContent: 'space-between' }}><label htmlFor="syllabus-text">Syllabus text</label><button type="button" className="link-btn" onClick={useSample}>Try with a sample syllabus</button></div>
              <textarea id="syllabus-text" rows={10} value={text} onChange={e => setText(e.target.value)} placeholder="Paste the whole syllabus: schedule, grading, policies, books." />
              <span className="hint">{text.length.toLocaleString()} / 60,000 characters (at least 50)</span>
            </div>
            <button type="submit" className="btn-primary" disabled={!textOk || busy} aria-busy={busy}>Build my class agent</button>
          </form>
        )}
      </div>
    </section>
  )
}
