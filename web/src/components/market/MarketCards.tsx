import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../lib/api'
import { eventWhen, firstImage, kindOf, money, safeHttps, TRANSFER_LABEL, type ListingV2 } from '../../lib/market'
import { useToast } from '../Toast'
import Avatar from '../Avatar'
import { buyLabel } from './Checkout'

export type ChatStarter = (l: ListingV2, message: string) => Promise<string | null>

const KIND_BADGE: Record<string, string> = { sell: 'For sale', trade: 'Trade', free: 'Free', wanted: 'Wanted', service: 'Tutor' }

/** One short badge per card. Demo data must always say so. */
function badgeOf(l: ListingV2): string {
  if (l.demo) return 'Demo listing'
  if (l.category === 'tickets' || l.ticket) return 'Ticket'
  return KIND_BADGE[kindOf(l)] ?? 'For sale'
}
function priceOf(l: ListingV2): string {
  const k = kindOf(l)
  if (k === 'wanted') return l.price > 0 ? `Up to ${money(l.price)}` : 'Wanted'
  if (k === 'trade') return l.acceptCash && l.price > 0 ? money(l.price) : 'Trade'
  if (k === 'service') return l.price === 0 ? 'Free' : `${money(l.price)}/hr`
  return money(l.price)
}
function metaOf(l: ListingV2): string {
  const k = kindOf(l)
  if (l.ticket?.eventAt || (l.category === 'tickets' && l.ticket?.event)) return [eventWhen(l.ticket?.eventAt), l.campus.shortName].filter(Boolean).join(' · ')
  if (k === 'service') return [l.tutoring?.courseCodes?.[0] ?? l.tutoring?.subjects?.[0] ?? l.courseCode, l.campus.shortName].filter(Boolean).join(' · ')
  if (k === 'trade') return [l.tradeFor ? `Wants ${l.tradeFor}` : '', l.campus.shortName].filter(Boolean).join(' · ')
  return [l.campus.shortName, l.condition].filter(Boolean).join(' · ')
}

const CAT_ICON: Record<string, string> = {
  books: 'M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4zM5 17a3 3 0 0 1 3-3h10', textbooks: 'M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4zM5 17a3 3 0 0 1 3-3h10',
  electronics: 'M4 6h16v10H4zM2 20h20', furniture: 'M5 11V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v4M3 11h18v6H3zM6 17v3M18 17v3', dorm: 'M5 11V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v4M3 11h18v6H3zM6 17v3M18 17v3',
  tickets: 'M3 8a2 2 0 0 0 0 4v0a2 2 0 0 1 0 4v2h18v-2a2 2 0 0 1 0-4v0a2 2 0 0 0 0-4V6H3zM14 6v12', tutoring: 'M2 9l10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5',
  clothing: 'M8 3l-5 4 3 3 2-1v12h8V9l2 1 3-3-5-4a4 4 0 0 1-8 0z', clothes: 'M8 3l-5 4 3 3 2-1v12h8V9l2 1 3-3-5-4a4 4 0 0 1-8 0z',
}
const FALLBACK_CATS = ['books', 'supplies', 'electronics', 'dorm', 'tickets', 'tutoring', 'clothing', 'rides', 'other']
const CAT_TILE = ['books', 'textbooks', 'electronics', 'furniture', 'dorm', 'tickets', 'tutoring', 'clothing', 'clothes']

/** Category-coloured tile with an icon: what a listing with no picture shows instead of an empty box. */
function CategoryTile({ category }: { category: string }) {
  const c = CAT_TILE.includes(category) ? category : ''
  return (
    <span className="mk-thumb mk-thumb--tile" data-cat={c || 'other'} aria-hidden="true">
      <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={CAT_ICON[c] ?? 'M4 8l8-4 8 4v8l-8 4-8-4zM4 8l8 4 8-4M12 12v8'} /></svg>
    </span>
  )
}

/** 4:3 picture with a soft skeleton until it loads. Own-origin or https only (see safeImgSrc). */
export function ListingThumb({ l, large }: { l: ListingV2; large?: boolean }) {
  const img = firstImage(l)
  const [state, setState] = useState<'loading' | 'ok' | 'broken'>('loading')
  const [fb, setFb] = useState(true)
  if (!img || state === 'broken') {
    if (large) return null
    const cat = FALLBACK_CATS.includes(l.category === 'textbooks' ? 'books' : l.category) ? (l.category === 'textbooks' ? 'books' : l.category) : 'other'
    return fb
      ? <span className="mk-thumb mk-thumb--fallback" data-state="ok" aria-hidden="true"><img src={`/demo/market/fallback-${cat}.svg`} alt="" loading="lazy" decoding="async" width={640} height={480} onError={() => setFb(false)} /></span>
      : <CategoryTile category={l.category} />
  }
  return (
    <span className={`mk-thumb${large ? ' mk-thumb--large' : ''}`} data-state={state}>
      <img src={img.src} alt={img.alt || l.title} loading={large ? 'eager' : 'lazy'} decoding="async" width={640} height={480}
        referrerPolicy="no-referrer" onLoad={() => setState('ok')} onError={() => setState('broken')} />
    </span>
  )
}

/** The ONE card shell for every kind: badge, title, big price, one line of meta. Tap opens the detail sheet. */
export function MarketCard({ l, onOpen }: { l: ListingV2; onOpen: (l: ListingV2) => void }) {
  const title = l.ticket?.event || l.title
  return (
    <button type="button" className="mk-card" data-here={l.onYourCampus} onClick={() => onOpen(l)} aria-label={`${title}, ${priceOf(l)}. Open details`}>
      <ListingThumb l={l} />
      <span className={`mk-badge${l.demo ? ' mk-badge--demo' : ''}`}>{badgeOf(l)}</span>
      <span className="mk-title">{title}</span>
      <span className="mk-price">{priceOf(l)}</span>
      <span className="mk-meta">{metaOf(l)}</span>
    </button>
  )
}

/** Tickets: a date block, the event, venue, price and the face value. Tap opens the details. */
export function TicketCard({ l, onOpen }: { l: ListingV2; onOpen: (l: ListingV2) => void }) {
  const t = l.ticket
  const d = t?.eventAt ? new Date(t.eventAt) : null
  const ok = !!d && !Number.isNaN(d.getTime())
  const title = t?.event || l.title
  return (
    <button type="button" className="mk-card mk-ticket" data-here={l.onYourCampus} onClick={() => onOpen(l)} aria-label={`${title}, ${money(l.price)} each. Open details`}>
      <span className="mk-datebox" aria-hidden="true"><b>{ok ? d!.toLocaleDateString(undefined, { day: 'numeric' }) : '?'}</b><span>{ok ? d!.toLocaleDateString(undefined, { month: 'short' }) : 'TBA'}</span></span>
      <span className="mk-ticket-main">
        <span className={`mk-badge${l.demo ? ' mk-badge--demo' : ''}`}>{l.demo ? 'Demo listing' : 'Ticket'}</span>
        <span className="mk-title">{title}</span>
        <span className="mk-meta">{[ok ? eventWhen(t?.eventAt) : '', t?.venue, t?.section].filter(Boolean).join(' · ')}</span>
        <span className="mk-ticket-price"><span className="mk-price">{money(l.price)}</span><span className="mk-meta">each{t?.faceValue != null ? ` · face value ${money(t.faceValue)}` : ''}{t?.quantity && t.quantity > 1 ? ` · ${t.quantity} tickets` : ''}</span></span>
      </span>
    </button>
  )
}

/** Tutoring: who, what they teach, the rate and when. Tap opens the details where "Request a session" lives. */
export function TutorCard({ l, onOpen }: { l: ListingV2; onOpen: (l: ListingV2) => void }) {
  const tu = l.tutoring
  const codes = tu?.courseCodes?.length ? tu.courseCodes : l.courseCode ? [l.courseCode] : []
  const subjects = (tu?.subjects ?? []).slice(0, 3)
  return (
    <button type="button" className="mk-card mk-tutor" data-here={l.onYourCampus} onClick={() => onOpen(l)} aria-label={`${l.title}, ${l.price === 0 ? 'free' : `${money(l.price)} per hour`}. Open details`}>
      <span className="row" style={{ flexWrap: 'nowrap', gap: 'var(--s-3)', alignItems: 'center', width: '100%' }}>
        <Avatar avatar={l.sellerAvatar} id={l.sellerId ?? l.sellerName} size={44} />
        <span style={{ minWidth: 0, flex: 1 }}><span className="mk-title">{l.title}</span><span className="mk-meta" style={{ display: 'block' }}>{l.sellerName || 'A student'} · {l.campus.shortName}</span></span>
        <span className="mk-price" style={{ fontSize: 'var(--text-lg)' }}>{l.price === 0 ? 'Free' : `${money(l.price)}/hr`}</span>
      </span>
      {(codes.length > 0 || subjects.length > 0) && <span className="chip-row">{codes.slice(0, 3).map(c => <span key={c} className="chip">{c}</span>)}{subjects.map(c => <span key={c} className="chip chip-outline">{c}</span>)}</span>}
      <span className="mk-meta">{[tu?.mode === 'online' ? 'Online' : tu?.mode === 'both' ? 'In person or online' : 'In person', tu?.availability].filter(Boolean).join(' · ')}</span>
      <span className="mk-cta" aria-hidden="true">Request a session</span>
    </button>
  )
}

/* ---------------- detail sheet content ---------------- */
function Detail({ rows }: { rows: [string, string | undefined | null][] }) {
  const shown = rows.filter(([, v]) => v)
  if (!shown.length) return null
  return <dl className="mk-facts">{shown.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
}

export function ListingDetail({ l, onChat, onBuy }: { l: ListingV2; onChat: ChatStarter; onBuy?: (l: ListingV2) => void }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const kind = kindOf(l)
  const [composing, setComposing] = useState(false)
  const [msg, setMsg] = useState(`Hi! Is "${l.ticket?.event || l.title}" still available?`.slice(0, 200))
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [reporting, setReporting] = useState(false)
  const t = l.ticket ?? null, tu = l.tutoring ?? null
  const official = safeHttps(t?.externalLink)
  const cta = kind === 'wanted' ? 'I have this' : kind === 'service' ? 'Request a session' : kind === 'trade' ? 'Propose a trade' : 'Message seller'

  async function send(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr('')
    const problem = await onChat(l, msg.trim())
    if (problem) setErr(problem)
    setBusy(false)
  }
  async function report(reason: string) {
    try {
      const r = await authFetch(`/listings/${l.id}/report`, { method: 'POST', body: JSON.stringify({ reason }) })
      if (!r.ok) { push('error', "Couldn't send the report", await errorMessage(r)); return }
      push('success', 'Report sent', 'Thanks for helping keep the marketplace safe.'); setReporting(false)
    } catch { push('error', "Couldn't send the report", 'Network problem. Try again.') }
  }

  return (
    <div className="stack">
      <ListingThumb l={l} large />
      <div>
        <span className={`mk-badge${l.demo ? ' mk-badge--demo' : ''}`}>{badgeOf(l)}</span>
        <h3 className="mk-detail-title">{t?.event || l.title}</h3>
        <div className="mk-price" style={{ fontSize: 'var(--text-xl)' }}>{priceOf(l)}{t ? <span className="muted" style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}> each</span> : null}</div>
        <p className="muted row" style={{ gap: 'var(--s-2)', flexWrap: 'nowrap', alignItems: 'center' }}><Avatar avatar={l.sellerAvatar} id={l.sellerId ?? l.sellerName} size={24} /><span>{l.campus.name}{l.onYourCampus ? ' (your campus)' : ''} · by {l.sellerName || 'a student'}</span></p>
      </div>

      {l.description && <p>{l.description}</p>}

      <Detail rows={[
        ['Condition', l.condition],
        ['Author', [l.author, l.edition].filter(Boolean).join(' · ')],
        ['Class', l.courseCode || tu?.courseCodes?.join(', ')],
        ['When', t ? eventWhen(t.eventAt) : undefined],
        ['Where', t ? [t.venue, t.section].filter(Boolean).join(' · ') : undefined],
        ['Tickets', t?.quantity ? String(t.quantity) : undefined],
        ['Face value', t?.faceValue != null ? `${money(t.faceValue)} each` : undefined],
        ['Transfer', t?.transferMethod ? TRANSFER_LABEL[t.transferMethod] ?? t.transferMethod : undefined],
        ['Subjects', tu?.subjects?.join(', ')],
        ['Format', tu?.mode === 'online' ? 'Online' : tu?.mode === 'both' ? 'In person or online' : tu ? 'In person' : undefined],
        ['Available', tu?.availability],
        ['Standing', tu?.standing],
        ['Wants in return', l.tradeFor],
        ['Also accepts cash', l.acceptCash ? (l.price > 0 ? money(l.price) : 'Yes') : undefined],
        ['Meet at', l.pickupSpot],
      ]} />

      {t && <p className="secret-note" role="note">Face-value tickets only. After you order, transfer them only through the official ticket app. Never pay or send tickets outside the app.</p>}
      {onBuy && !l.mine && kind !== 'wanted' && <button type="button" className="btn-primary btn-lg" onClick={() => onBuy(l)}>{buyLabel(l)}</button>}
      {official && <a className="btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} href={official} target="_blank" rel="noopener noreferrer">Open in the official ticket app</a>}

      <details className="mk-safety">
        <summary>Safety tips</summary>
        <ul>
          <li>Meet in a public, well-lit campus spot{l.pickupSpot ? ` (like ${l.pickupSpot})` : ''}.</li>
          <li>Pay securely in the app (demo checkout: no real money moves in this prototype). Never send money or card details anywhere else.</li>
          <li>Check the item before you pay. If anything feels off, walk away and report it.</li>
        </ul>
      </details>

      {l.demo && !onBuy ? <p className="muted">This is a demo listing, so there's no seller to message.</p> : l.demo ? <p className="muted">Demo listing: you can try the demo checkout, but there's no real seller to message.</p> : l.mine ? <p className="muted">This is your listing. Manage it in My listings.</p> : (
        <div className="stack" style={{ gap: 'var(--s-2)' }}>
          {composing ? (
            <form className="stack" onSubmit={send}>
              <div className="field"><label htmlFor={`m-${l.id}`}>Message to {l.sellerName || 'the seller'}</label><textarea id={`m-${l.id}`} rows={3} maxLength={1000} value={msg} onChange={e => setMsg(e.target.value)} /><span className="hint">No links or contact details.</span></div>
              {err && <p className="field-error" role="alert">{err}</p>}
              <div className="row"><button type="submit" className="btn-primary" disabled={busy || !msg.trim()} aria-busy={busy}>Send</button><button type="button" className="btn-ghost" onClick={() => setComposing(false)}>Cancel</button></div>
            </form>
          ) : <button type="button" className="btn-primary btn-lg" onClick={() => setComposing(true)}>{cta}</button>}
          {reporting ? (
            <div className="row" role="group" aria-label="Report this listing"><span className="muted">Report as:</span>
              {[['spam', 'Spam'], ['scam', 'Scam'], ['prohibited', 'Not allowed'], ['wrong_info', 'Wrong info'], ['other', 'Other']].map(([v, tx]) => <button key={v} type="button" className="btn-ghost btn-sm" onClick={() => report(v)}>{tx}</button>)}
            </div>
          ) : <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setReporting(true)}>Report this listing</button>}
        </div>
      )}
    </div>
  )
}
