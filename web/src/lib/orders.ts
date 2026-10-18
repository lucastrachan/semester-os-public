// Mock checkout + orders (a SIMULATION: no card fields, no real payment data anywhere). Built defensively to the expected API.
import { errorMessage } from './api'

export type OrderStatus = 'paid' | 'handed_over' | 'completed' | 'refunded' | 'cancelled'
export type Method = 'pickup' | 'ship'
export interface Order {
  id: string
  status: OrderStatus
  timeline: { status: OrderStatus; at: string }[]
  listing: { id: string; title: string; price?: number; category?: string; image?: { url: string; alt?: string } | string | null; campus?: { name?: string; shortName?: string } | string }
  counterpart: { name: string; avatar?: string; id?: string }
  amountCents: number
  method: Method
  demo?: boolean
  createdAt: string
  role?: 'buying' | 'selling'
}

export const DEMO_PAY_NOTICE = 'Semester OS Pay (demo): no real money moves in this prototype. Never enter real card or bank details.'
export const STATUS_LABEL: Record<OrderStatus, string> = { paid: 'Paid', handed_over: 'Handed over', completed: 'Completed', refunded: 'Refunded', cancelled: 'Cancelled' }
export const cents = (c: number) => `$${(Math.max(0, Number.isFinite(c) ? c : 0) / 100).toFixed(2)}`
export const toCents = (dollars: number) => Math.round((Number.isFinite(dollars) ? dollars : 0) * 100)
const STATUSES: OrderStatus[] = ['paid', 'handed_over', 'completed', 'refunded', 'cancelled']
export const asStatus = (s: unknown): OrderStatus => (STATUSES.includes(s as OrderStatus) ? (s as OrderStatus) : 'paid')

type Fetch = (p: string, i?: RequestInit) => Promise<Response>

/** Accepts {order}, {orders:[...]} or a bare order, and fills safe defaults. */
export function normalizeOrder(raw: unknown): Order | null {
  const o = (raw && typeof raw === 'object' ? ((raw as { order?: unknown }).order ?? raw) : null) as Partial<Order> | null
  if (!o || typeof o.id !== 'string') return null
  const status = asStatus(o.status)
  return {
    id: o.id, status,
    timeline: Array.isArray(o.timeline) ? o.timeline.filter(t => t && typeof t.at === 'string').map(t => ({ status: asStatus(t.status), at: t.at })) : [{ status: 'paid', at: o.createdAt ?? '' }],
    listing: { ...(o.listing ?? {}), id: String(o.listing?.id ?? ''), title: String(o.listing?.title ?? 'Listing') },
    counterpart: { name: String(o.counterpart?.name ?? 'A student'), avatar: o.counterpart?.avatar, id: o.counterpart?.id },
    amountCents: typeof o.amountCents === 'number' ? o.amountCents : 0,
    method: o.method === 'ship' ? 'ship' : 'pickup', demo: o.demo !== false, createdAt: String(o.createdAt ?? ''), role: o.role,
  }
}

export async function placeOrder(f: Fetch, listingId: string, method: Method, note?: string): Promise<{ order?: Order; error?: string }> {
  try {
    const r = await f(`/listings/${listingId}/orders`, { method: 'POST', body: JSON.stringify({ method, ...(note ? { note } : {}) }) })
    if (!r.ok) return { error: await errorMessage(r, "We couldn't place the order. Try again.") }
    const order = normalizeOrder(await r.json().catch(() => null))
    return order ? { order } : { error: 'The order was placed but we could not read it. Check Orders.' }
  } catch { return { error: 'Network problem. Try again.' } }
}

export async function listOrders(f: Fetch, role: 'buying' | 'selling'): Promise<{ orders?: Order[]; unavailable?: boolean; error?: boolean }> {
  try {
    const r = await f(`/orders?role=${role}`)
    if ([403, 404, 405, 501].includes(r.status)) return { unavailable: true }
    if (!r.ok) return { error: true }
    const j = await r.json()
    const arr: unknown[] = Array.isArray(j) ? j : Array.isArray(j.orders) ? j.orders : []
    return { orders: arr.map(normalizeOrder).filter((x): x is Order => !!x) }
  } catch { return { error: true } }
}

export async function getOrder(f: Fetch, id: string): Promise<{ order?: Order; missing?: boolean; error?: boolean }> {
  try {
    const r = await f(`/orders/${encodeURIComponent(id)}`)
    if (r.status === 404) return { missing: true }
    if (!r.ok) return { error: true }
    const order = normalizeOrder(await r.json())
    return order ? { order } : { error: true }
  } catch { return { error: true } }
}

export async function orderAction(f: Fetch, id: string, action: 'handed_over' | 'received' | 'cancel' | 'decline'): Promise<{ order?: Order; error?: string }> {
  try {
    const r = await f(`/orders/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ action }) })
    if (!r.ok) return { error: await errorMessage(r, "We couldn't update the order. Try again.") }
    return { order: normalizeOrder(await r.json().catch(() => null)) ?? undefined }
  } catch { return { error: 'Network problem. Try again.' } }
}
