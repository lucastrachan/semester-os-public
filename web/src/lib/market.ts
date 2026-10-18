// Marketplace types (MARKETPLACE_API.md, MESSAGES_API.md). Listing and message text is plain text: never HTML, never links.
export interface Listing {
  id: string; title: string; author: string; isbn: string | null; edition: string
  price: number; condition: string; category: string; courseCode: string
  description: string; pickupSpot: string; status: 'available' | 'sold' | 'removed'
  flagged: boolean; demo: boolean; sellerName: string; sellerAvatar?: string; sellerId?: string
  campus: { id: string; name: string; shortName: string }
  onYourCampus: boolean; mine: boolean; createdAt: string
}
export interface BookMatch { matchType: 'isbn' | 'title'; score: number; listing: Listing }
export interface BookNeed {
  title: string; author: string; edition: string; isbn: string; required: boolean; notes: string
  matches: BookMatch[]; bestPrice: number | null; bestOnYourCampus: number | null
}
export interface CourseBooks { courseId: string; courseCode: string; title: string; color: string; books: BookNeed[] }

export interface Conversation {
  id: string; role: 'buyer' | 'seller'
  listing: { id: string; title: string; price?: number; status?: string }
  other: { name: string; avatar?: string; id?: string; campus: { id: string; name: string; shortName: string } }
  status: 'open' | 'closed'; closedReason: string | null; canSend: boolean
  lastMessage: { from: 'me' | 'them' | 'system'; text: string; at: string } | null
  unread: number; createdAt: string; lastMessageAt: string
}
export interface ChatMessage { id: string; from: 'me' | 'them' | 'system'; text: string; at: string }

export const money = (n: number) => (n === 0 ? 'Free' : `$${Number.isInteger(n) ? n : n.toFixed(2)}`)

export const CONDITIONS = ['New', 'Like new', 'Good', 'Acceptable'] as const

export const CLOSED_TEXT: Record<string, string> = {
  listing_removed: 'This listing was removed.',
  listing_flagged: 'This listing is under review.',
  campus_unavailable: 'This campus is unavailable right now.',
}
/** Never say who blocked, and never reveal admin or ban details. */
export const closedText = (reason: string | null) => (reason && CLOSED_TEXT[reason]) || 'This conversation is closed.'

/* ---------------- Marketplace v2 (MARKETPLACE_V2_API.md) ---------------- */
export type Kind = 'sell' | 'trade' | 'free' | 'wanted' | 'service'
export const KINDS: { id: Kind; label: string }[] = [
  { id: 'sell', label: 'For sale' }, { id: 'trade', label: 'Trade' }, { id: 'free', label: 'Free' }, { id: 'wanted', label: 'Wanted' }, { id: 'service', label: 'Services' },
]
export type CategoryId = 'books' | 'supplies' | 'electronics' | 'dorm' | 'clothing' | 'tickets' | 'tutoring' | 'rides' | 'other'
export const CATEGORIES: { id: CategoryId; label: string; hint: string }[] = [
  { id: 'books', label: 'Books', hint: 'Textbooks and readings' },
  { id: 'supplies', label: 'Supplies', hint: 'Lab, art, calculators' },
  { id: 'electronics', label: 'Electronics', hint: 'Laptops, tablets, headphones' },
  { id: 'dorm', label: 'Dorm', hint: 'Furniture and appliances' },
  { id: 'clothing', label: 'Clothing', hint: 'Game day, formal, gear' },
  { id: 'tickets', label: 'Tickets', hint: 'Games, shows, events' },
  { id: 'tutoring', label: 'Tutoring', hint: 'Peer tutors' },
  { id: 'rides', label: 'Rides', hint: 'Carpools and trips' },
  { id: 'other', label: 'Other', hint: 'Anything school-related' },
]
/** Categories where a condition is required for sell/trade/free listings (the goods). */
export const GOODS: CategoryId[] = ['books', 'supplies', 'electronics', 'dorm', 'clothing', 'other']

/** Kinds, tickets, tutoring and trades on the existing /listings routes are deployed. */
export const MARKET_V2_LIVE = true
/** GET /listings/for-you and GET /courses/{id}/tutors are written but not routed yet: flip each when Builder confirms its deploy. */
export const FOR_YOU_LIVE = true
export const TUTORS_FOR_CLASS_LIVE = true

export type TransferMethod = 'official_app' | 'mobile_wallet' | 'will_call' | 'other'
export const TRANSFER_LABEL: Record<TransferMethod, string> = { official_app: 'Official ticket app', mobile_wallet: 'Mobile wallet', will_call: 'Will call', other: 'Other' }
export type Standing = '' | 'freshman' | 'sophomore' | 'junior' | 'senior' | 'graduate'
export const STANDINGS: Standing[] = ['freshman', 'sophomore', 'junior', 'senior', 'graduate']

export interface TicketInfo { event?: string; eventAt?: string; venue?: string; section?: string; quantity?: number; faceValue?: number; transferMethod?: TransferMethod; externalLink?: string }
export interface TutoringInfo { subjects?: string[]; courseCodes?: string[]; mode?: 'in_person' | 'online' | 'both'; availability?: string; standing?: Standing }
export interface ListingV2 extends Listing { kind?: Kind; tradeFor?: string; acceptCash?: boolean; ticket?: TicketInfo | null; tutoring?: TutoringInfo | null; expired?: boolean; images?: (ListingImage | string)[] }
export interface ListingImage { url: string; alt?: string }

/** Image src allowed in <img>: our own /demo/ illustrations or https URLs. Anything else is dropped. */
export const safeImgSrc = (u?: string): string | null => {
  if (!u) return null
  if (u.startsWith('/demo/') && !u.includes('..') && !u.startsWith('//') && !u.includes('\\') && !u.includes('?')) return u
  return safeHttps(u)
}
/** First usable image of a listing, or null (the card then shows its category tile). */
export function firstImage(l: ListingV2): { src: string; alt: string } | null {
  for (const im of l.images ?? []) {
    const o: ListingImage = typeof im === 'string' ? { url: im } : im
    const src = safeImgSrc(o?.url)
    if (src) return { src, alt: typeof o.alt === 'string' ? o.alt.slice(0, 160) : '' }
  }
  return null
}

/** https only: a link from listing data is never trusted to be safe. */
export const safeHttps = (u?: string): string | null => { try { const x = new URL(u ?? ''); return x.protocol === 'https:' ? x.href : null } catch { return null } }
export const kindOf = (l: ListingV2): Kind => l.kind ?? (l.category === 'tutoring' ? 'service' : l.price === 0 ? 'free' : 'sell')
export const eventWhen = (iso?: string) => { const d = iso ? new Date(iso) : null; return d && !Number.isNaN(d.getTime()) ? d.toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '' }
/** The "done" button is labelled by what the listing was. */
export const DONE_LABEL: Record<Kind, string> = { sell: 'Mark sold', trade: 'Mark traded', free: 'Mark given away', wanted: 'Found one', service: 'Not offering any more' }
/** The server returns the legacy "textbooks" as "books"; campus category lists may still contain either. */
export const canonCategory = (c: string): string => (c.toLowerCase().startsWith('textbook') ? 'books' : c.toLowerCase())
