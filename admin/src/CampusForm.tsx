import { useState } from 'react'
import { timezones } from './api'

export interface TutoringRow { name: string; description: string; url: string }
export interface CampusInput {
  name: string; shortName: string; domains: string[]; themeColor: string; timezone: string
  lmsType: string; tutoringResources: TutoringRow[]; pickupSpots: string[]; openToNetwork: boolean
}

const HEX = /^#[0-9a-fA-F]{6}$/

export function CampusForm(props: {
  initialName?: string; initialDomains?: string[]; initial?: Partial<CampusInput>; lockDomains?: boolean; submitLabel: string; busy: boolean
  onSubmit: (c: CampusInput) => void; onCancel?: () => void
}) {
  const [name, setName] = useState(props.initial?.name ?? props.initialName ?? '')
  const [shortName, setShortName] = useState(props.initial?.shortName ?? '')
  const [domains, setDomains] = useState((props.initial?.domains ?? props.initialDomains ?? []).join(', '))
  const [color, setColor] = useState(props.initial?.themeColor ?? '#1a56db')
  const [tz, setTz] = useState(props.initial?.timezone ?? 'America/Chicago')
  const [lms, setLms] = useState(props.initial?.lmsType ?? 'blackboard_ultra')
  const [tutoring, setTutoring] = useState<TutoringRow[]>(props.initial?.tutoringResources ?? [])
  const [spots, setSpots] = useState((props.initial?.pickupSpots ?? []).join('\n'))
  const [open, setOpen] = useState(props.initial?.openToNetwork ?? true)
  const [err, setErr] = useState('')

  const setRow = (i: number, patch: Partial<TutoringRow>) =>
    setTutoring(rows => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  function submit(ev: React.FormEvent) {
    ev.preventDefault()
    if (!HEX.test(color)) { setErr('Theme colour must look like #RRGGBB.'); return }
    setErr('')
    props.onSubmit({
      name: name.trim(), shortName: shortName.trim(),
      domains: domains.split(/[\s,;]+/).filter(Boolean),
      themeColor: color, timezone: tz, lmsType: lms,
      tutoringResources: tutoring.filter(t => t.name.trim()),
      pickupSpots: spots.split('\n').map(s => s.trim()).filter(Boolean),
      openToNetwork: open,
    })
  }

  return (
    <form className="ops-form" onSubmit={submit}>
      <div className="field-row">
        <div className="field"><label>Campus name</label>
          <input required minLength={2} maxLength={120} value={name} onChange={e => setName(e.target.value)} /></div>
        <div className="field"><label>Short name</label>
          <input maxLength={8} value={shortName} onChange={e => setShortName(e.target.value)} placeholder="auto" />
          <span className="hint">Up to 8 characters. Blank derives it.</span></div>
      </div>
      <div className="field"><label>Email domains</label>
        <input required readOnly={props.lockDomains} value={domains} onChange={e => setDomains(e.target.value)} placeholder="ua.edu, crimson.ua.edu" />
        <span className="hint">{props.lockDomains ? 'Domains cannot be changed here.' : 'Comma separated. Public mail providers are rejected. Existing domains are never overwritten.'}</span></div>
      <div className="field-row">
        <div className="field"><label>Theme colour</label>
          <div className="color-row">
            <input type="color" aria-label="Pick colour" value={HEX.test(color) ? color : '#1a56db'} onChange={e => setColor(e.target.value)} />
            <input type="text" aria-label="Hex colour" value={color} maxLength={7} onChange={e => setColor(e.target.value)} className="mono" />
          </div></div>
        <div className="field"><label>Timezone</label>
          <select value={tz} onChange={e => setTz(e.target.value)}>
            {!timezones.includes(tz) && <option>{tz}</option>}
            {timezones.map(z => <option key={z}>{z}</option>)}
          </select></div>
      </div>
      <div className="field-row">
        <div className="field"><label>LMS</label>
          <select value={lms} onChange={e => setLms(e.target.value)}>
            <option value="blackboard_ultra">Blackboard Ultra (iCal feed)</option>
            <option value="canvas">Canvas (pending approval)</option>
            <option value="other">Other / none</option>
          </select></div>
        <label className="check"><input type="checkbox" checked={open} onChange={e => setOpen(e.target.checked)} /> Open to network (listings visible to other campuses)</label>
      </div>

      <div className="ops-sub">
        <b>Tutoring resources</b>
        {tutoring.map((t, i) => (
          <div className="ops-sub" key={i}>
            <div className="field-row">
              <div className="field"><label>Name</label><input value={t.name} onChange={e => setRow(i, { name: e.target.value })} maxLength={120} /></div>
              <div className="field"><label>Link (https)</label><input type="url" value={t.url} onChange={e => setRow(i, { url: e.target.value })} /></div>
            </div>
            <div className="field"><label>Description</label><input value={t.description} onChange={e => setRow(i, { description: e.target.value })} maxLength={400} /></div>
            <button type="button" className="btn-ghost-sm" onClick={() => setTutoring(rows => rows.filter((_, j) => j !== i))}>Remove</button>
          </div>
        ))}
        {tutoring.length < 10 && (
          <button type="button" className="btn-ghost-sm" onClick={() => setTutoring(r => [...r, { name: '', description: '', url: '' }])}>Add resource</button>
        )}
      </div>

      <div className="field"><label>Pickup spots</label>
        <textarea rows={3} value={spots} onChange={e => setSpots(e.target.value)} placeholder="One per line, public and well lit" />
        <span className="hint">Only list places you have confirmed exist.</span></div>

      {err && <p className="ops-msg-err" role="alert">{err}</p>}
      <div className="ops-actions">
        <button className="btn-primary" disabled={props.busy} aria-busy={props.busy}>{props.submitLabel}</button>
        {props.onCancel && <button type="button" className="btn-ghost-sm" onClick={props.onCancel}>Cancel</button>}
      </div>
    </form>
  )
}
