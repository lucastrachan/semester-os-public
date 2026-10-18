import { useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { canonCategory, CATEGORIES, CONDITIONS, GOODS, STANDINGS, TRANSFER_LABEL, type CategoryId, type Kind, type ListingV2, type TransferMethod } from '../lib/market'
import { useToast } from './Toast'

const pad = (n: number) => String(n).padStart(2, '0')
const toLocalInput = (iso?: string) => { const d = iso ? new Date(iso) : null; return d && !Number.isNaN(d.getTime()) ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}` : '' }

type Choice = { id: string; title: string; blurb: string; kind: Kind; cat?: CategoryId }
const CHOICES: Choice[] = [
  { id: 'sell', title: 'Sell something', blurb: 'Books, supplies, dorm gear, electronics', kind: 'sell' },
  { id: 'tickets', title: 'Sell tickets', blurb: 'At face value, through the official app', kind: 'sell', cat: 'tickets' },
  { id: 'tutor', title: 'Offer tutoring', blurb: 'Help classmates, set your own rate', kind: 'service', cat: 'tutoring' },
  { id: 'trade', title: 'Trade', blurb: 'Swap for something you need', kind: 'trade' },
  { id: 'free', title: 'Give away', blurb: 'Free to a classmate', kind: 'free' },
  { id: 'wanted', title: "I'm looking for something", blurb: 'Post what you need and get matches', kind: 'wanted' },
]

/**
 * A short 3-step wizard (what are you posting? > details > review). The contract's rules are applied before sending:
 * tutoring needs kind service or wanted, tickets need a future event and (when the campus caps prices) a price at or
 * below face value, condition only for goods. Kind cannot change on edit, so editing goes straight to the details.
 */
export default function ListingForm({ categories, pickupSpots, ticketPriceCap = true, edit, preset, onClose, onSaved }: {
  categories: string[]; pickupSpots: string[]; ticketPriceCap?: boolean; edit?: ListingV2 | null; preset?: 'sell' | 'tickets' | 'tutor'; onClose: () => void; onSaved: () => void
}) {
  const presetChoice = !edit && preset ? CHOICES.find(c => c.id === preset) : undefined
  const { authFetch } = useAuth()
  const { push } = useToast()
  const enabled = useMemo(() => new Set((categories.length ? categories : CATEGORIES.map(c => c.id)).map(canonCategory)), [categories])

  const [step, setStep] = useState<1 | 2 | 3>(edit || presetChoice ? 2 : 1)
  const [choice, setChoice] = useState<string>(edit ? 'edit' : presetChoice?.id ?? '')
  const [kind, setKind] = useState<Kind>(edit?.kind ?? presetChoice?.kind ?? 'sell')
  const [cat, setCat] = useState<CategoryId>((edit ? canonCategory(edit.category) : presetChoice?.cat ?? 'books') as CategoryId)
  const tk = edit?.ticket ?? {}, tu = edit?.tutoring ?? {}
  const [f, setF] = useState({
    title: edit?.title ?? '', author: edit?.author ?? '', isbn: edit?.isbn ?? '', edition: edit?.edition ?? '',
    price: edit && edit.price != null ? String(edit.price) : '', condition: edit?.condition || 'Good', courseCode: edit?.courseCode ?? '',
    description: edit?.description ?? '', pickupSpot: edit?.pickupSpot ?? '',
    tradeFor: edit?.tradeFor ?? '', acceptCash: !!edit?.acceptCash,
    event: tk.event ?? '', eventAt: toLocalInput(tk.eventAt), venue: tk.venue ?? '', section: tk.section ?? '', quantity: String(tk.quantity ?? 1),
    faceValue: tk.faceValue != null ? String(tk.faceValue) : '', transferMethod: (tk.transferMethod ?? 'official_app') as TransferMethod, externalLink: tk.externalLink ?? '',
    subjects: (tu.subjects ?? []).join(', '), courseCodes: (tu.courseCodes ?? []).join(', '), mode: tu.mode ?? 'in_person', availability: tu.availability ?? '', standing: tu.standing ?? '',
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value })

  function pick(c: Choice) {
    setChoice(c.id); setKind(c.kind)
    setCat(c.cat ?? (CATEGORIES.find(x => x.id === cat && !['tickets', 'tutoring'].includes(x.id) && enabled.has(x.id))?.id ?? (CATEGORIES.find(x => !['tickets', 'tutoring'].includes(x.id) && enabled.has(x.id))?.id ?? 'other')))
    setStep(2)
  }

  const isTicket = cat === 'tickets', isWanted = kind === 'wanted', isFree = kind === 'free', isService = kind === 'service', isTrade = kind === 'trade'
  const isTutor = isService || (cat === 'tutoring' && isWanted)
  const needsCondition = !isWanted && GOODS.includes(cat) && !isService
  // categories you can pick inside "sell / trade / give away / wanted" (tickets and tutoring have their own paths, except when wanted)
  const catChoices = CATEGORIES.filter(c => enabled.has(c.id) && (isWanted || (c.id !== 'tickets' && c.id !== 'tutoring')))

  const eventDate = f.eventAt ? new Date(f.eventAt) : null
  const eventOk = !isTicket || isWanted || (!!eventDate && eventDate.getTime() > Date.now() && eventDate.getTime() < Date.now() + 400 * 86400000)
  const subjects = f.subjects.split(',').map(s => s.trim()).filter(Boolean)
  const codes = f.courseCodes.split(',').map(s => s.trim()).filter(Boolean)
  const price = Number(f.price)

  let problem = ''
  if (f.title.trim().length < 3) problem = 'Add a title of at least 3 characters.'
  else if (!enabled.has(cat)) problem = 'Your campus has not turned this category on.'
  else if (isTrade && (f.tradeFor.trim().length < 3 || f.tradeFor.trim().length > 120)) problem = 'Say what you want in return (3 to 120 characters).'
  else if (isTrade && f.acceptCash && !(price > 0)) problem = 'Add the cash price, or turn off "also accept cash".'
  else if (isTicket && !isWanted && (f.event.trim().length < 3 || f.venue.trim().length < 2)) problem = 'Add the event and the venue.'
  else if (isTicket && !isWanted && !eventOk) problem = 'The event must be in the future (within about a year).'
  else if (isTicket && !isWanted && f.faceValue === '') problem = 'Add the face value of one ticket.'
  else if (isTicket && !isWanted && !isFree && ticketPriceCap && price > Number(f.faceValue)) problem = `Tickets can't be listed above face value ($${f.faceValue}).`
  else if (isTutor && !isWanted && (subjects.length < 1 || subjects.length > 5)) problem = 'Add 1 to 5 subjects or classes you tutor.'
  else if (!isFree && !isWanted && !isTrade && !(f.price !== '' && price >= 0 && price <= (isService ? 200 : 1000))) problem = isService ? 'Add an hourly rate between $0 and $200.' : 'Add a price between $0 and $1000.'

  async function save() {
    if (problem) return
    setBusy(true); setErr('')
    const body: Record<string, unknown> = { title: f.title.trim(), category: cat }
    if (!edit) body.kind = kind
    if (needsCondition) body.condition = f.condition
    for (const k of ['description', 'pickupSpot', 'courseCode'] as const) if (f[k].trim()) body[k] = f[k].trim()
    if (cat === 'books') for (const k of ['author', 'isbn', 'edition'] as const) if (f[k].trim()) body[k] = f[k].trim()
    if (!isFree && f.price !== '') body.price = price
    if (isTicket && f.price === '' && !isWanted) body.price = 0
    if (isTrade) { body.tradeFor = f.tradeFor.trim(); body.acceptCash = f.acceptCash }
    if (isTicket) {
      body.ticket = {
        event: f.event.trim(), eventAt: eventDate ? eventDate.toISOString() : undefined, venue: f.venue.trim(), section: f.section.trim(),
        quantity: Math.max(1, Math.min(10, Number(f.quantity) || 1)), faceValue: f.faceValue === '' ? undefined : Number(f.faceValue),
        transferMethod: f.transferMethod, externalLink: f.externalLink.trim(),
      }
    }
    if (isTutor) body.tutoring = { subjects, courseCodes: codes, mode: f.mode, availability: f.availability.trim(), standing: f.standing }
    try {
      const r = edit
        ? await authFetch(`/listings/${edit.id}`, { method: 'PATCH', body: JSON.stringify(body) })
        : await authFetch('/listings', { method: 'POST', body: JSON.stringify(body) })
      if (!r.ok) {
        let code = ''; try { code = (await r.clone().json()).error } catch { /* none */ }
        setErr(code === 'limit' ? await errorMessage(r, "You've reached the limit for this kind of listing. Remove one first.") : await errorMessage(r)); return
      }
      push('success', edit ? 'Saved' : isWanted ? 'Posted' : 'Listed', edit ? undefined : 'Students at your campus can see it now.')
      onSaved()
    } catch { setErr('Network problem. Try again.') } finally { setBusy(false) }
  }

  const summaryPrice = isFree ? 'Free' : isWanted ? (f.price ? `Up to $${f.price}` : 'No budget set') : isTrade ? (f.acceptCash && f.price ? `Trade or $${f.price}` : 'Trade') : isService ? `$${f.price || 0}/hr` : isTicket ? `$${f.price || 0} each` : `$${f.price || 0}`
  const stepLabel = ['What are you posting?', 'The details', 'Review'][step - 1]

  return (
    <section className="window" aria-label={edit ? 'Edit listing' : 'Create a listing'}>
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">{edit ? 'edit-listing' : `new-listing · step ${step} of 3`}</span><button type="button" className="btn-ghost-sm" onClick={onClose}>Close</button></div>
      <div className="window-body stack">
        {!edit && <ol className="wizard-steps" aria-label="Progress">{['Type', 'Details', 'Review'].map((s, i) => <li key={s} className="wizard-dot" data-on={step >= i + 1} aria-current={step === i + 1 ? 'step' : undefined}>{i + 1}. {s}</li>)}</ol>}
        <h2 style={{ fontSize: 'var(--text-lg)' }}>{edit ? 'Edit your listing' : stepLabel}</h2>

        {step === 1 && (
          <div className="config-grid" role="group" aria-label="What are you posting?">
            {CHOICES.map(c => {
              const off = c.cat ? !enabled.has(c.cat) : false
              return (
                <button key={c.id} type="button" className="config-item" disabled={off} style={{ textAlign: 'left', cursor: off ? 'not-allowed' : 'pointer', opacity: off ? 0.55 : 1 }} onClick={() => pick(c)}>
                  <h3>{c.title}</h3><p className="config-value">{off ? 'Not turned on at your campus' : c.blurb}</p>
                </button>
              )
            })}
          </div>
        )}

        {step === 2 && (
          <div className="request-form">
            {!edit && catChoices.length > 1 && !isTicket && !isService && (
              <div className="field"><span className="field-label" id="cat-l">Category</span>
                <div className="chip-row" role="group" aria-labelledby="cat-l">
                  {catChoices.map(c => <button key={c.id} type="button" className={cat === c.id ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'} aria-pressed={cat === c.id} onClick={() => { setCat(c.id) }}>{c.label}</button>)}
                </div></div>
            )}

            <div className="field"><label htmlFor="l-title">{isTicket ? 'Listing title' : isService ? 'What do you tutor?' : isWanted ? 'What are you looking for?' : isTrade ? 'What are you offering?' : 'Title'} <span className="req">*</span></label>
              <input id="l-title" required minLength={3} maxLength={160} value={f.title} onChange={set('title')} placeholder={isService ? 'Calculus and statistics tutor' : isTicket ? 'Two tickets: Saturday home game' : 'Calculus: Early Transcendentals, 8th ed'} /></div>

            {cat === 'books' && (
              <div className="field-row">
                <div className="field"><label htmlFor="l-author">Author</label><input id="l-author" value={f.author} onChange={set('author')} /></div>
                <div className="field"><label htmlFor="l-isbn">ISBN</label><input id="l-isbn" inputMode="numeric" value={f.isbn} onChange={set('isbn')} placeholder="Matches it to classes" /></div>
              </div>
            )}

            {isTrade && (
              <div className="field"><label htmlFor="l-trade">What do you want in return? <span className="req">*</span></label><input id="l-trade" value={f.tradeFor} maxLength={120} onChange={set('tradeFor')} />
                <label className="check"><input type="checkbox" checked={f.acceptCash} onChange={set('acceptCash')} /> Also accept cash</label></div>
            )}

            {isTicket && !isWanted && (
              <>
                <div className="field-row">
                  <div className="field"><label htmlFor="t-event">Event <span className="req">*</span></label><input id="t-event" maxLength={120} value={f.event} onChange={set('event')} /></div>
                  <div className="field"><label htmlFor="t-at">Date and time <span className="req">*</span></label><input id="t-at" type="datetime-local" value={f.eventAt} onChange={set('eventAt')} aria-invalid={!!f.eventAt && !eventOk} /></div>
                </div>
                <div className="field-row">
                  <div className="field"><label htmlFor="t-venue">Venue <span className="req">*</span></label><input id="t-venue" maxLength={120} value={f.venue} onChange={set('venue')} /></div>
                  <div className="field"><label htmlFor="t-section">Section / row</label><input id="t-section" maxLength={40} value={f.section} onChange={set('section')} placeholder="Section 12, row F" /></div>
                </div>
                <div className="field-row">
                  <div className="field"><label htmlFor="t-qty">How many tickets</label><input id="t-qty" type="number" min={1} max={10} value={f.quantity} onChange={set('quantity')} /></div>
                  <div className="field"><label htmlFor="t-face">Face value of one ticket (USD) <span className="req">*</span></label><input id="t-face" type="number" min={0} max={1000} step="0.01" value={f.faceValue} onChange={set('faceValue')} /><span className="hint">{ticketPriceCap ? 'Your campus caps prices at face value.' : 'Be fair: sell at or near face value.'}</span></div>
                </div>
                <div className="field-row">
                  <div className="field"><label htmlFor="t-xfer">How will you transfer them?</label><select id="t-xfer" value={f.transferMethod} onChange={set('transferMethod')}>{(Object.keys(TRANSFER_LABEL) as TransferMethod[]).map(m => <option key={m} value={m}>{TRANSFER_LABEL[m]}</option>)}</select></div>
                  <div className="field"><label htmlFor="t-url">Official ticket app link (optional, https)</label><input id="t-url" type="url" maxLength={300} value={f.externalLink} onChange={set('externalLink')} placeholder="https://" /></div>
                </div>
              </>
            )}
            {isTicket && isWanted && <div className="field"><label htmlFor="t-event">Which event?</label><input id="t-event" maxLength={120} value={f.event} onChange={set('event')} /></div>}

            {isTutor && (
              <>
                <div className="field"><label htmlFor="u-subj">{isWanted ? 'Subjects you need help with' : 'Subjects you tutor'} (comma separated, up to 5)</label><input id="u-subj" value={f.subjects} onChange={set('subjects')} placeholder="Calculus I, Statistics" /></div>
                <div className="field-row">
                  <div className="field"><label htmlFor="u-codes">Class codes (optional)</label><input id="u-codes" value={f.courseCodes} onChange={set('courseCodes')} placeholder="MATH 125, STAT 200" /></div>
                  <div className="field"><label htmlFor="u-mode">Where</label><select id="u-mode" value={f.mode} onChange={set('mode')}><option value="in_person">In person at a campus spot</option><option value="online">Online</option><option value="both">Either</option></select></div>
                </div>
                {!isWanted && (
                  <div className="field-row">
                    <div className="field"><label htmlFor="u-avail">When are you free?</label><input id="u-avail" maxLength={200} value={f.availability} onChange={set('availability')} placeholder="Weeknights after 6" /></div>
                    <div className="field"><label htmlFor="u-stand">Your standing (optional)</label><select id="u-stand" value={f.standing} onChange={set('standing')}><option value="">Prefer not to say</option>{STANDINGS.map(s => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}</select></div>
                  </div>
                )}
              </>
            )}

            {!isFree && (
              <div className="field-row">
                <div className="field"><label htmlFor="l-price">{isService ? 'Rate per hour (USD, 0 = free)' : isWanted ? 'Most you would pay (USD, optional)' : isTrade ? 'Cash price (USD)' : isTicket ? 'Your price per ticket (USD)' : 'Price (USD)'}</label>
                  <input id="l-price" type="number" min={0} max={isService ? 200 : 1000} step="0.01" value={f.price} onChange={set('price')} /></div>
                {needsCondition && <div className="field"><label htmlFor="l-cond">Condition</label><select id="l-cond" value={f.condition} onChange={set('condition')}>{CONDITIONS.map(c => <option key={c}>{c}</option>)}</select></div>}
              </div>
            )}
            {isFree && needsCondition && <div className="field"><label htmlFor="l-cond">Condition</label><select id="l-cond" value={f.condition} onChange={set('condition')}>{CONDITIONS.map(c => <option key={c}>{c}</option>)}</select></div>}

            <details className="mk-safety">
              <summary>More details (optional)</summary>
              <div className="stack" style={{ marginTop: 'var(--s-3)' }}>
                {cat !== 'tutoring' && <div className="field"><label htmlFor="l-course">Class</label><input id="l-course" value={f.courseCode} onChange={set('courseCode')} placeholder="MIS 430" /></div>}
                <div className="field"><label htmlFor="l-spot">Meet-up spot</label><input id="l-spot" list="spots" maxLength={80} value={f.pickupSpot} onChange={set('pickupSpot')} placeholder={pickupSpots.length ? 'Choose or type a public place' : 'A public, well-lit place on campus'} /><datalist id="spots">{pickupSpots.map(s => <option key={s} value={s} />)}</datalist></div>
                <div className="field"><label htmlFor="l-desc">Description</label><textarea id="l-desc" rows={3} maxLength={500} value={f.description} onChange={set('description')} /><span className="hint">Plain text. Links aren't allowed.</span></div>
              </div>
            </details>
            {problem && f.title.trim().length >= 3 && <p className="field-error" role="status">{problem}</p>}
          </div>
        )}

        {step === 3 && (
          <div className="stack">
            <div className="mk-card mk-card--preview" aria-label="Preview">
              <span className="mk-badge">{isTicket ? 'Ticket' : isWanted ? 'Wanted' : isService ? 'Tutor' : isTrade ? 'Trade' : isFree ? 'Free' : 'For sale'}</span>
              <span className="mk-title">{isTicket && f.event ? f.event : f.title}</span>
              <span className="mk-price">{summaryPrice}</span>
              <span className="mk-meta">{[CATEGORIES.find(c => c.id === cat)?.label, needsCondition ? f.condition : '', f.pickupSpot].filter(Boolean).join(' · ')}</span>
            </div>
            <p className="muted">It will show to students at your campus{kind === 'service' ? '' : ' (and other open campuses)'}. Payment happens in person, never in the app. You can edit or remove it any time.</p>
            {isTicket && !isWanted && <p className="secret-note" role="note">Buyers pay in the app (demo checkout) at face value or less. Transfer tickets only through the official ticket app.</p>}
            {err && <p className="field-error" role="alert">{err}</p>}
          </div>
        )}

        <div className="row" style={{ justifyContent: 'space-between' }}>
          {step > 1 && !edit ? <button type="button" className="btn-ghost" onClick={() => setStep((step - 1) as 1 | 2)}>Back</button> : <span />}
          {step === 2 && !edit && <button type="button" className="btn-primary" disabled={!!problem} onClick={() => setStep(3)}>Review</button>}
          {step === 2 && edit && <button type="button" className="btn-primary" disabled={!!problem || busy} aria-busy={busy} onClick={save}>Save changes</button>}
          {step === 3 && <button type="button" className="btn-primary btn-lg" style={{ width: 'auto' }} disabled={busy} aria-busy={busy} onClick={save}>{isWanted ? 'Post it' : 'List it'}</button>}
        </div>
        {edit && err && <p className="field-error" role="alert">{err}</p>}
      </div>
    </section>
  )
}
