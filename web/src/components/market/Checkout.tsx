import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { firstImage, kindOf, money, type ListingV2 } from '../../lib/market'
import { cents, DEMO_PAY_NOTICE, placeOrder, toCents, type Method, type Order } from '../../lib/orders'
import Avatar from '../Avatar'

const LockIcon = () => <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>

/** "Seller L." from "Seller Lastname". Never an email. */
export const shortName = (n?: string) => {
  const p = (n ?? '').trim().split(/\s+/).filter(Boolean)
  if (!p.length || p[0].includes('@')) return 'A student'
  return p.length > 1 ? `${p[0]} ${p[p.length - 1][0].toUpperCase()}.` : p[0]
}

export const buyLabel = (l: ListingV2) => (l.ticket || l.category === 'tickets' ? 'Buy ticket' : kindOf(l) === 'service' ? 'Book session' : 'Buy now')

/** The checkout sheet: a SIMULATION. No card fields; "Pay (demo)" places an order and no real money moves. */
export default function Checkout({ l, onClose }: { l: ListingV2; onClose: () => void }) {
  const { authFetch } = useAuth()
  const crossCampus = !l.onYourCampus
  const [method, setMethod] = useState<Method>(crossCampus ? 'ship' : 'pickup')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [order, setOrder] = useState<Order | null>(null)
  const img = firstImage(l)
  const isService = kindOf(l) === 'service'
  const isTicket = !!l.ticket || l.category === 'tickets'
  const total = toCents(l.price)

  async function pay() {
    setBusy(true); setErr('')
    const res = await placeOrder(authFetch, l.id, isService || isTicket ? 'pickup' : method, note.trim() || undefined)
    setBusy(false)
    if (res.error) { setErr(res.error); return }
    setOrder(res.order ?? null)
  }

  if (order) {
    return (
      <div className="stack" role="status">
        <div className="row"><span className="scan-ok" aria-hidden="true">✓</span><h3 style={{ margin: 0 }}>Order placed</h3></div>
        <p className="muted">Your order for <strong>{l.ticket?.event || l.title}</strong> ({cents(order.amountCents)}) is in. This was a demo checkout: no real money moved.</p>
        <div className="row"><Link to={`/orders/${order.id}`} className="btn-primary" onClick={onClose}>View order</Link><button type="button" className="btn-ghost" onClick={onClose}>Keep browsing</button></div>
      </div>
    )
  }

  return (
    <form className="stack" onSubmit={e => { e.preventDefault(); pay() }}>
      <div className="row" style={{ flexWrap: 'nowrap', gap: 'var(--s-3)', alignItems: 'center' }}>
        {img ? <img className="checkout-thumb" src={img.src} alt={img.alt || l.title} width={96} height={72} /> : <span className="checkout-thumb" aria-hidden="true" />}
        <div style={{ minWidth: 0 }}>
          <strong>{l.ticket?.event || l.title}</strong>
          <div className="muted" style={{ fontSize: 'var(--text-sm)' }}>{l.campus.name}</div>
          <div className="row" style={{ gap: 'var(--s-2)', flexWrap: 'nowrap', alignItems: 'center' }}><Avatar avatar={l.sellerAvatar} id={l.sellerId ?? l.sellerName} size={22} /><span className="muted" style={{ fontSize: 'var(--text-sm)' }}>Sold by {shortName(l.sellerName)}</span></div>
        </div>
      </div>

      {isTicket && <p className="secret-note" role="note">Face-value tickets only. Transfer only through the official ticket app after you order; no scalping.</p>}

      {!isService && !isTicket && (
        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          <legend className="field-label">Delivery</legend>
          <div className="segmented" role="radiogroup" aria-label="Delivery method">
            <button type="button" role="radio" aria-checked={method === 'pickup'} aria-pressed={method === 'pickup'} onClick={() => setMethod('pickup')}>Campus pickup</button>
            <button type="button" role="radio" aria-checked={method === 'ship'} aria-pressed={method === 'ship'} onClick={() => setMethod('ship')}>Ship{crossCampus ? ' (recommended)' : ''}</button>
          </div>
          <span className="hint">{method === 'ship' ? 'Shipping is arranged with the seller in chat. No address is collected here.' : 'Meet in a public, well-lit campus spot arranged in chat.'}</span>
        </fieldset>
      )}
      <div className="field"><label htmlFor="co-note">Note to the seller (optional)</label><input id="co-note" value={note} maxLength={200} onChange={e => setNote(e.target.value)} placeholder="No addresses or phone numbers" /></div>

      <dl className="mk-facts" aria-label="Price breakdown">
        <div><dt>{isService ? 'Session (1 hour)' : 'Price'}</dt><dd>{cents(total)}</dd></div>
        <div><dt>Fees</dt><dd>{cents(0)} · no fees</dd></div>
        <div><dt><strong>Total</strong></dt><dd><strong>{cents(total)}</strong></dd></div>
      </dl>

      <p className="campus-note row" role="note" style={{ gap: 'var(--s-2)', flexWrap: 'nowrap', alignItems: 'flex-start' }}><LockIcon /><span>{DEMO_PAY_NOTICE}</span></p>
      {err && <p className="field-error" role="alert">{err}</p>}
      <div className="row"><button type="submit" className="btn-primary btn-lg" disabled={busy || l.mine} aria-busy={busy}>{busy ? 'Placing order…' : `Pay (demo) ${money(l.price)}`}</button><button type="button" className="btn-ghost" onClick={onClose}>Cancel</button></div>
      {l.mine && <p className="muted">This is your own listing.</p>}
    </form>
  )
}
