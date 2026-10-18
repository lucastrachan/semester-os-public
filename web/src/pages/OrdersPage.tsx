import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { safeImgSrc } from '../lib/market'
import { cents, DEMO_PAY_NOTICE, getOrder, listOrders, orderAction, STATUS_LABEL, type Order, type OrderStatus } from '../lib/orders'
import Avatar from '../components/Avatar'
import Robot from '../components/Robot'
import { shortName } from '../components/market/Checkout'
import { useToast } from '../components/Toast'

const when = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) }
const imgOf = (o: Order) => { const im = o.listing.image; const url = typeof im === 'string' ? im : im?.url; return safeImgSrc(url ?? undefined) }
const ACTIVE: OrderStatus[] = ['paid', 'handed_over']

function Thumb({ o }: { o: Order }) {
  const src = imgOf(o)
  const [bad, setBad] = useState(false)
  return src && !bad ? <img className="checkout-thumb" src={src} alt="" width={96} height={72} loading="lazy" onError={() => setBad(true)} /> : <span className="checkout-thumb" aria-hidden="true" />
}
const Chip = ({ s }: { s: OrderStatus }) => <span className="chip order-chip" data-status={s}>{STATUS_LABEL[s]}</span>

export default function OrdersPage() {
  const { id } = useParams()
  return id ? <OrderDetail id={id} /> : <OrderList />
}

function OrderList() {
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [params, setParams] = useSearchParams()
  const role = params.get('role') === 'selling' ? 'selling' : 'buying'
  const [orders, setOrders] = useState<Order[] | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'unavailable' | 'error'>('loading')

  const load = useCallback(async () => {
    const r = await listOrders(fetchRef.current, role)
    if (r.unavailable) { setState('unavailable'); return }
    if (r.error || !r.orders) { setState('error'); return }
    setOrders(r.orders); setState('ok')
  }, [role])
  useEffect(() => { if (user) { setState('loading'); setOrders(null); load() } }, [user, load])

  return (
    <div className="page">
      <div className="page-head"><span className="eyebrow">Orders</span><h1>Your orders</h1>
        <div className="segmented" role="tablist" aria-label="Buying or selling" style={{ alignSelf: 'flex-start' }}>
          {(['buying', 'selling'] as const).map(r => <button key={r} role="tab" type="button" aria-selected={role === r} aria-pressed={role === r} onClick={() => setParams(r === 'buying' ? {} : { role: r })}>{r === 'buying' ? 'Buying' : 'Selling'}</button>)}
        </div>
      </div>
      <p className="campus-note" role="note">{DEMO_PAY_NOTICE}</p>
      {state === 'loading' ? <div className="stack" aria-busy="true" aria-label="Loading orders"><div className="skeleton-block" style={{ height: '5rem' }} /><div className="skeleton-block" style={{ height: '5rem' }} /></div>
        : state === 'unavailable' ? <div className="empty"><Robot name="base" size={72} /><div className="empty-title">Orders are coming soon</div><p className="empty-body">Checkout and orders will show up here as soon as they are switched on.</p></div>
        : state === 'error' ? <div className="warning" role="alert"><span>We couldn't load your orders.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div>
        : !orders || orders.length === 0 ? (
          <div className="empty"><Robot name="books" size={72} /><div className="empty-title">{role === 'buying' ? 'No purchases yet' : 'No sales yet'}</div>
            <p className="empty-body">{role === 'buying' ? 'When you buy something with Buy now, it shows up here.' : 'When someone buys one of your listings, it shows up here.'}</p>
            <Link to="/marketplace" className="btn-primary">{role === 'buying' ? 'Browse the marketplace' : 'See your listings'}</Link></div>
        ) : (
          <ul className="stack" style={{ gap: 'var(--s-2)' }}>
            {orders.map(o => (
              <li key={o.id}>
                <Link to={`/orders/${o.id}`} className="listing order-row" style={{ gridTemplateColumns: 'auto 1fr auto' }} aria-label={`${o.listing.title}, ${STATUS_LABEL[o.status]}, ${cents(o.amountCents)}`}>
                  <Thumb o={o} />
                  <span style={{ minWidth: 0 }}><strong>{o.listing.title}</strong><span className="muted" style={{ display: 'block', fontSize: 'var(--text-sm)' }}>{role === 'buying' ? 'from' : 'to'} {shortName(o.counterpart.name)} · {when(o.createdAt)}</span><Chip s={o.status} /></span>
                  <span className="mk-price">{cents(o.amountCents)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
    </div>
  )
}

function OrderDetail({ id }: { id: string }) {
  const { authFetch, user } = useAuth()
  const { push } = useToast()
  const navigate = useNavigate()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [order, setOrder] = useState<Order | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'missing' | 'error'>('loading')
  const [busy, setBusy] = useState('')
  const [confirm, setConfirm] = useState<'cancel' | 'decline' | null>(null)

  const load = useCallback(async () => {
    const r = await getOrder(fetchRef.current, id)
    if (r.missing) { setState('missing'); return }
    if (!r.order) { setState('error'); return }
    setOrder(r.order); setState('ok')
  }, [id])
  useEffect(() => { if (user) load() }, [user, load])

  async function act(action: 'handed_over' | 'received' | 'cancel' | 'decline', done: string) {
    setBusy(action)
    const r = await orderAction(fetchRef.current, id, action)
    setBusy(''); setConfirm(null)
    if (r.error) { push('error', "Couldn't update the order", r.error); return }
    push('success', done)
    if (r.order) setOrder(r.order); else load()
  }
  async function message() {
    if (!order) return
    setBusy('message')
    try {
      const r = await fetchRef.current(`/listings/${order.listing.id}/conversations`, { method: 'POST', body: JSON.stringify({ message: `Hi! About my order for "${order.listing.title}".`.slice(0, 200) }) })
      if (!r.ok) { push('error', "Couldn't open the chat", await errorMessage(r)); return }
      const j = await r.json()
      navigate(`/messages?convo=${encodeURIComponent(j.conversation?.id ?? '')}`)
    } catch { push('error', "Couldn't open the chat", 'Network problem. Try again.') } finally { setBusy('') }
  }

  if (state === 'loading') return <div className="page"><div className="skeleton-block" style={{ height: '10rem' }} aria-busy="true" aria-label="Loading order" /></div>
  if (state === 'missing') return <div className="page"><div className="empty"><Robot name="state-error" size={72} /><div className="empty-title">Order not found</div><Link to="/orders" className="btn-primary">Back to orders</Link></div></div>
  if (state === 'error' || !order) return <div className="page"><div className="warning" role="alert"><span>We couldn't load this order.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div></div>

  const buyer = order.role !== 'selling'
  const s = order.status
  const steps: OrderStatus[] = s === 'refunded' || s === 'cancelled' ? ['paid', s] : ['paid', 'handed_over', 'completed']
  const at = (st: OrderStatus) => order.timeline.find(t => t.status === st)?.at
  const reached = (st: OrderStatus) => (s === 'refunded' || s === 'cancelled') ? !!at(st) || st === 'paid' || st === s : steps.indexOf(st) <= steps.indexOf(s)

  return (
    <div className="page">
      <Link to={buyer ? '/orders' : '/orders?role=selling'} className="btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }}>← Orders</Link>
      <div className="page-head"><span className="eyebrow">Order · {order.method === 'ship' ? 'Shipping' : 'Campus pickup'}</span><h1>{order.listing.title}</h1></div>
      <section className="window" aria-label="Order">
        <div className="window-body stack">
          <div className="row" style={{ flexWrap: 'nowrap', gap: 'var(--s-3)', alignItems: 'center' }}>
            <Thumb o={order} />
            <div style={{ minWidth: 0, flex: 1 }}><Chip s={s} /><div className="mk-price">{cents(order.amountCents)}</div>
              <div className="row" style={{ gap: 'var(--s-2)', flexWrap: 'nowrap', alignItems: 'center' }}><Avatar avatar={order.counterpart.avatar} id={order.counterpart.id ?? order.counterpart.name} size={22} /><span className="muted">{buyer ? 'Seller' : 'Buyer'}: {shortName(order.counterpart.name)}</span></div></div>
          </div>
          <ol className="order-timeline" aria-label="Order status">
            {steps.map(st => <li key={st} data-on={reached(st)} data-bad={st === 'refunded' || st === 'cancelled'}><span className="order-dot" aria-hidden="true" /><span><strong>{STATUS_LABEL[st]}</strong>{at(st) && <span className="muted" style={{ display: 'block', fontSize: 'var(--text-sm)' }}>{when(at(st)!)}</span>}</span></li>)}
          </ol>
          <p className="campus-note" role="note">{DEMO_PAY_NOTICE}</p>
          <div className="row">
            {buyer && s === 'handed_over' && <button type="button" className="btn-primary" onClick={() => act('received', 'Marked as received')} disabled={!!busy} aria-busy={busy === 'received'}>I got it</button>}
            {buyer && s === 'paid' && (confirm === 'cancel'
              ? <><span className="muted">Cancel this order and refund the demo payment?</span><button type="button" className="btn-danger btn-sm" onClick={() => act('cancel', 'Order cancelled')} disabled={!!busy}>Yes, cancel</button><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm(null)}>Keep</button></>
              : <button type="button" className="btn-ghost" onClick={() => setConfirm('cancel')}>Cancel order</button>)}
            {!buyer && s === 'paid' && <button type="button" className="btn-primary" onClick={() => act('handed_over', 'Marked as handed over')} disabled={!!busy} aria-busy={busy === 'handed_over'}>Mark handed over</button>}
            {!buyer && s === 'paid' && (confirm === 'decline'
              ? <><span className="muted">Decline and refund the buyer?</span><button type="button" className="btn-danger btn-sm" onClick={() => act('decline', 'Order declined')} disabled={!!busy}>Yes, decline</button><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm(null)}>Keep</button></>
              : <button type="button" className="btn-ghost" onClick={() => setConfirm('decline')}>Decline</button>)}
            <button type="button" className="btn-ghost" onClick={message} disabled={busy === 'message'} aria-busy={busy === 'message'}>{buyer ? 'Message seller' : 'Message buyer'}</button>
          </div>
          {!ACTIVE.includes(s) && <p className="muted">This order is {STATUS_LABEL[s].toLowerCase()}.</p>}
        </div>
      </section>
    </div>
  )
}
