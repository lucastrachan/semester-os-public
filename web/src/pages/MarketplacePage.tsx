import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { canonCategory, CATEGORIES, CONDITIONS, DONE_LABEL, FOR_YOU_LIVE, KINDS, kindOf, money, type CategoryId, type CourseBooks, type Kind, type ListingV2 } from '../lib/market'
import Conversations from '../components/Conversations'
import ListingForm from '../components/ListingForm'
import Drawer from '../components/market/Drawer'
import Recommended from '../components/market/Recommended'
import { ListingDetail, MarketCard, TicketCard, TutorCard, type ChatStarter } from '../components/market/MarketCards'
import Checkout, { buyLabel } from '../components/market/Checkout'
import Robot from '../components/Robot'
import { useToast } from '../components/Toast'

type Tab = 'browse' | 'mine' | 'messages'
type Scope = 'campus' | 'network'
type Meta = { safety?: string; spots?: string[]; categories?: string[]; ticketPriceCap?: boolean }


/** The school marketplace, kept calm: search, a few chips, minimal cards, and everything else one tap away (filters, details, create). */
export default function MarketplacePage() {
  const { authFetch, tenant, user } = useAuth()
  const { push } = useToast()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [params] = useSearchParams()
  const nav = useNavigate()
  const { section: secParam } = useParams()
  const section: Section = secParam === 'tickets' || secParam === 'tutoring' ? secParam : 'items'
  const [tab, setTab] = useState<Tab>('browse')
  const [openConvo, setOpenConvo] = useState<string | null>(null)
  const [unread, setUnread] = useState(0)
  const [selected, setSelected] = useState<ListingV2 | null>(null)
  const [checkout, setCheckout] = useState<ListingV2 | null>(null)
  const [wizard, setWizard] = useState<{ edit: ListingV2 | null; preset?: 'sell' | 'tickets' | 'tutor' } | null>(null)
  const PRESET = { items: 'sell', tickets: 'tickets', tutoring: 'tutor' } as const
  const POST_LABEL = { items: 'Sell something', tickets: 'Sell a ticket', tutoring: 'Offer tutoring' } as const
  const openPost = () => setWizard({ edit: null, preset: PRESET[section] })
  const [refresh, setRefresh] = useState(0)
  const [spots, setSpots] = useState<string[]>(tenant?.pickupSpots ?? [])
  const [enabled, setEnabled] = useState<string[]>((tenant?.categories ?? []).map((c: string) => canonCategory(c)))
  const [ticketCap, setTicketCap] = useState(true)

  useEffect(() => { const c = params.get('convo'); if (c && /^[a-z0-9]{8}$/.test(c)) { setOpenConvo(c); setTab('messages') } }, [params])
  useEffect(() => {
    if (!user) return
    let alive = true
    const poll = async () => {
      if (document.visibilityState !== 'visible') return
      try { const r = await fetchRef.current('/conversations/unread'); if (r.ok && alive) setUnread((await r.json()).unread ?? 0) } catch { /* ignore */ }
    }
    poll()
    const t = window.setInterval(poll, 60000)
    return () => { alive = false; window.clearInterval(t) }
  }, [user])

  const startChat: ChatStarter = useCallback(async (l, message) => {
    try {
      const r = await fetchRef.current(`/listings/${l.id}/conversations`, { method: 'POST', body: JSON.stringify({ message }) })
      if (!r.ok) {
        let code = ''; try { code = (await r.clone().json()).error } catch { /* none */ }
        return code === 'cannot_message' ? "You can't message this seller." : code === 'conversation_closed' ? 'That conversation was closed.' : await errorMessage(r)
      }
      const j = await r.json()
      setSelected(null); setOpenConvo(j.conversation.id); setTab('messages')
      return null
    } catch { return 'Network problem. Try again.' }
  }, [])

  const onMeta = useCallback((m: Meta) => {
    if (m.spots?.length) setSpots(m.spots)
    if (m.categories?.length) setEnabled(m.categories.map(canonCategory))
    if (typeof m.ticketPriceCap === 'boolean') setTicketCap(m.ticketPriceCap)
  }, [])

  return (
    <div className="page">
      <div className="page-head">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end' }}>
          <div><span className="eyebrow">Marketplace · {tenant?.shortName ?? 'campus'}</span><h1>Find it. Sell it. Share it.</h1></div>
          <button type="button" className="btn-primary" onClick={openPost}>{POST_LABEL[section]}</button>
        </div>
        <div className="segmented mk-sections" role="tablist" aria-label="Marketplace sections">
          {([['items', 'For sale'], ['tickets', 'Tickets'], ['tutoring', 'Tutoring']] as [Section, string][]).map(([id, label]) => (
            <button key={id} role="tab" type="button" aria-selected={tab === 'browse' && section === id} aria-pressed={tab === 'browse' && section === id} onClick={() => { setTab('browse'); setOpenConvo(null); nav(`/marketplace/${id}`) }}>{label}</button>
          ))}
        </div>
        <div className="row mk-subnav">
          <button type="button" className={`link-btn${tab === 'mine' ? ' is-on' : ''}`} aria-pressed={tab === 'mine'} onClick={() => { setTab('mine'); setOpenConvo(null) }}>My listings</button>
          <button type="button" className={`link-btn${tab === 'messages' ? ' is-on' : ''}`} aria-pressed={tab === 'messages'} onClick={() => setTab('messages')}>{unread > 0 ? `Messages (${unread})` : 'Messages'}</button>
        </div>
      </div>

      {tab === 'browse' && <Browse key={`${section}-${refresh}`} section={section} enabled={enabled} onMeta={onMeta} onOpen={setSelected} onCreate={openPost} ticketCap={ticketCap} />}
      {tab === 'mine' && <Mine key={refresh} onEdit={l => setWizard({ edit: l })} onCreate={openPost} push={push} />}
      {tab === 'messages' && <Conversations openId={openConvo} onOpen={setOpenConvo} />}

      <Drawer open={!!selected} title="Details" onClose={() => setSelected(null)}>
        {selected && <ListingDetail l={selected} onChat={startChat} onBuy={l => { setSelected(null); setCheckout(l) }} />}
      </Drawer>
      <Drawer open={!!checkout} title={checkout ? buyLabel(checkout) : 'Checkout'} onClose={() => setCheckout(null)}>
        {checkout && <Checkout l={checkout} onClose={() => setCheckout(null)} />}
      </Drawer>
      <Drawer open={!!wizard} title={wizard?.edit ? 'Edit listing' : POST_LABEL[section]} onClose={() => setWizard(null)} wide>
        {wizard && <ListingForm categories={enabled} ticketPriceCap={ticketCap} pickupSpots={spots} edit={wizard.edit} preset={wizard.preset} onClose={() => setWizard(null)} onSaved={() => { setWizard(null); setRefresh(n => n + 1); if (!wizard.edit) setTab('mine') }} />}
      </Drawer>
    </div>
  )
}

/* ---------- "For you": one small strip, only when something matches ---------- */
function ForYou({ onChat }: { onChat: ChatStarter }) {
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [books, setBooks] = useState<CourseBooks[]>([])
  const [wanted, setWanted] = useState<{ wantedTitle?: string; listing: ListingV2 }[]>([])
  useEffect(() => {
    if (!user) return
    let alive = true
    fetchRef.current('/books/matches').then(async r => { if (r.ok && alive) setBooks((await r.json()).courses ?? []) }).catch(() => {})
    // Matches for your own "wanted" posts (GET /listings/for-you is deployed later: FOR_YOU_LIVE)
    if (FOR_YOU_LIVE) fetchRef.current('/listings/for-you').then(async r => {
      if (!r.ok || !alive) return
      setWanted((((await r.json()).items ?? []) as { reason: string; wantedTitle?: string; listing: ListingV2 }[]).filter(i => i.reason === 'wanted'))
    }).catch(() => {})
    return () => { alive = false }
  }, [user])
  const picks = useMemo(() => books.flatMap(c => c.books.filter(b => b.required && b.matches.length > 0).map(b => ({ c, b }))).slice(0, 6), [books])
  if (picks.length === 0 && wanted.length === 0) return null
  return (
    <section aria-label="For you" className="stack" style={{ gap: 'var(--s-2)' }}>
      <span className="eyebrow">For you</span>
      <div className="foryou-strip">
        {wanted.slice(0, 4).map(w => (
          <button key={`w-${w.listing.id}`} type="button" className="foryou-chip" onClick={() => onChat(w.listing, `Hi! Is "${w.listing.title}" still available?`)}>
            <strong>{w.listing.title}</strong><span>{money(w.listing.price)} · matches your post</span>
          </button>
        ))}
        {picks.map(({ c, b }) => {
          const m = b.matches[0]
          return (
            <button key={`${c.courseId}-${b.title}`} type="button" className="foryou-chip" onClick={() => onChat(m.listing, `Hi! Is "${m.listing.title}" still available?`)} disabled={m.listing.demo || m.listing.mine}>
              <strong>{b.title}</strong><span>{c.courseCode} · {money(m.listing.price)} · {m.listing.campus.shortName}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

/* ---------- Browse: three distinct sections ---------- */
type Section = 'items' | 'tickets' | 'tutoring'
const isTicketL = (l: ListingV2) => l.category === 'tickets' || !!l.ticket
const isTutorL = (l: ListingV2) => l.category === 'tutoring' || kindOf(l) === 'service'
const ITEM_CATS: { id: CategoryId; label: string }[] = [{ id: 'books', label: 'Books' }, { id: 'supplies', label: 'Supplies' }, { id: 'electronics', label: 'Electronics' }, { id: 'dorm', label: 'Dorm' }, { id: 'clothing', label: 'Clothing' }]
const EVENT_TYPES = [{ id: 'all', label: 'All events' }, { id: 'football', label: 'Football' }, { id: 'basketball', label: 'Basketball' }, { id: 'concert', label: 'Concerts' }, { id: 'other', label: 'Other' }]
const normCode = (c: string) => c.toUpperCase().replace(/[^A-Z0-9]/g, '')
const EMPTY: Record<Section, { title: string; body: string; cta: string }> = {
  items: { title: 'Nothing for sale here yet', body: 'Be the first to post a book, supplies or dorm gear for your campus.', cta: 'Sell something' },
  tickets: { title: 'No tickets listed yet', body: 'Going to a game or a show you cannot use? List your tickets at face value.', cta: 'Sell a ticket' },
  tutoring: { title: 'No tutors yet', body: 'Know a class well? Offer a few hours and set your own rate.', cta: 'Offer tutoring' },
}

function Browse({ section, enabled, onMeta, onOpen, onCreate, ticketCap }: { section: Section; enabled: string[]; onMeta: (m: Meta) => void; onOpen: (l: ListingV2) => void; onCreate: () => void; ticketCap: boolean }) {
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [q, setQ] = useState('')
  const [applied, setApplied] = useState('')
  const [cat, setCat] = useState<CategoryId | 'all'>('all')
  const [filters, setFilters] = useState(false)
  const [scope, setScope] = useState<Scope>('campus')
  const [kind, setKind] = useState<Kind | 'all'>('all')
  const [maxPrice, setMaxPrice] = useState('')
  const [cond, setCond] = useState('')
  const [evType, setEvType] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [code, setCode] = useState('')
  const [mode, setMode] = useState('any')
  const [sort, setSort] = useState<'best' | 'rate'>('best')
  const [items, setItems] = useState<ListingV2[] | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    try {
      const qs = new URLSearchParams({ scope })
      if (applied) qs.set('q', applied)
      if (section === 'tickets') qs.set('category', 'tickets')
      else if (section === 'tutoring') qs.set('category', 'tutoring')
      else if (cat !== 'all') qs.set('category', cat)
      if (section === 'items' && kind !== 'all') qs.set('kind', kind)
      if (maxPrice !== '' && Number(maxPrice) >= 0) qs.set('priceMax', String(Number(maxPrice)))
      if (section === 'items' && cond) qs.set('condition', cond)
      const r = await fetchRef.current(`/listings?${qs}`)
      if (!r.ok) throw new Error(String(r.status))
      const j = await r.json()
      setItems(j.listings ?? []); setError(false)
      onMeta({ safety: j.safety, spots: j.campus?.pickupSpots, categories: j.campus?.categories, ticketPriceCap: j.campus?.ticketPriceCap })
    } catch { setError(true) }
  }, [section, scope, applied, cat, kind, maxPrice, cond]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (user) { setItems(null); load() } }, [user, load])

  const on = (id: CategoryId) => enabled.length === 0 || enabled.includes(id)
  const itemCats = ITEM_CATS.filter(c => on(c.id))
  const restCats = CATEGORIES.filter(c => on(c.id) && c.id !== 'tickets' && c.id !== 'tutoring' && !ITEM_CATS.some(p => p.id === c.id))
  const activeFilters = (scope !== 'campus' ? 1 : 0) + (maxPrice !== '' ? 1 : 0)
    + (section === 'items' ? (cond ? 1 : 0) + (cat !== 'all' ? 1 : 0) + (kind !== 'all' ? 1 : 0) : 0)
    + (section === 'tickets' ? (from ? 1 : 0) + (to ? 1 : 0) + (evType !== 'all' ? 1 : 0) : 0)
    + (section === 'tutoring' ? (mode !== 'any' ? 1 : 0) + (code.trim() ? 1 : 0) + (sort !== 'best' ? 1 : 0) : 0)
  const anyFilter = !!applied || activeFilters > 0

  const shown = useMemo(() => {
    const all = items ?? []
    if (section === 'items') return all.filter(l => !isTicketL(l) && !isTutorL(l) && (kind === 'all' ? kindOf(l) !== 'wanted' : kindOf(l) === kind))
    if (section === 'tickets') {
      const lo = from ? new Date(`${from}T00:00:00`).getTime() : null
      const hi = to ? new Date(`${to}T23:59:59`).getTime() : null
      return all.filter(l => {
        if (!isTicketL(l) || kindOf(l) === 'wanted') return false
        const text = `${l.ticket?.event ?? ''} ${l.title}`.toLowerCase()
        if (evType === 'football' && !/football|gridiron/.test(text)) return false
        if (evType === 'basketball' && !/basketball/.test(text)) return false
        if (evType === 'concert' && !/concert|music|band|tour|festival/.test(text)) return false
        if (evType === 'other' && /football|gridiron|basketball|concert|music|band|tour|festival/.test(text)) return false
        const at = l.ticket?.eventAt ? new Date(l.ticket.eventAt).getTime() : null
        if (lo !== null && (at === null || at < lo)) return false
        if (hi !== null && (at === null || at > hi)) return false
        return true
      }).sort((a, b) => (a.ticket?.eventAt ? new Date(a.ticket.eventAt).getTime() : Infinity) - (b.ticket?.eventAt ? new Date(b.ticket.eventAt).getTime() : Infinity))
    }
    const want = normCode(code)
    const has = (l: ListingV2) => !!want && [...(l.tutoring?.courseCodes ?? []), l.courseCode].some(c => c && normCode(c).includes(want))
    return all.filter(l => isTutorL(l) && kindOf(l) === 'service' && (!want || has(l)) && (mode === 'any' || l.tutoring?.mode === mode || l.tutoring?.mode === 'both'))
      .sort((a, b) => sort === 'rate' || !want ? a.price - b.price : Number(has(b)) - Number(has(a)) || a.price - b.price)
  }, [items, section, kind, evType, from, to, code, mode, sort])

  const reset = () => { setQ(''); setApplied(''); setCat('all'); setScope('campus'); setKind('all'); setMaxPrice(''); setCond(''); setEvType('all'); setFrom(''); setTo(''); setCode(''); setMode('any') }
  const accept = section === 'items' ? (l: ListingV2) => !isTicketL(l) && !isTutorL(l) : section === 'tickets' ? isTicketL : (l: ListingV2) => isTutorL(l)
  const placeholder = section === 'tickets' ? 'Search games, concerts, venues…' : section === 'tutoring' ? 'Search tutors, subjects, classes…' : 'Search books, supplies, dorm gear…'
  const emp = EMPTY[section]
  const Card = section === 'tickets' ? TicketCard : section === 'tutoring' ? TutorCard : MarketCard

  return (
    <div className="stack">
      <form className="mk-search" role="search" onSubmit={e => { e.preventDefault(); setApplied(q.trim()) }}>
        <input className="input" aria-label={`Search ${section === 'items' ? 'items for sale' : section}`} value={q} maxLength={80} onChange={e => setQ(e.target.value)} placeholder={placeholder} />
        <button type="submit" className="btn-primary">Search</button>
        <button type="button" className="btn-ghost" onClick={() => setFilters(true)}>Filters{activeFilters > 0 ? ` (${activeFilters})` : ''}</button>
      </form>

      {section === 'tickets' && <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>{ticketCap ? 'Face value or less. ' : ''}Pay in the app (demo checkout, no real money moves) and transfer only through the official ticket app. No scalping.</p>}

      {!anyFilter && <Recommended onOpen={onOpen} accept={accept} fallback={shown} />}

      {error ? <div className="warning" role="alert"><span>We couldn't load listings.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div>
        : !items ? <div className="mk-grid" aria-busy="true" aria-label="Loading listings">{[0, 1, 2, 3].map(i => <div key={i} className="skeleton-block" style={{ height: section === 'items' ? '15rem' : '8rem' }} />)}</div>
        : shown.length === 0 ? (
          <div className="empty">
            <Robot name="base" size={72} />
            <div className="empty-title">{applied ? `Nothing matches "${applied.slice(0, 40)}"` : anyFilter ? 'Nothing matches' : emp.title}</div>
            <p className="empty-body">{scope === 'campus' && anyFilter ? 'Nothing on your campus fits. Other open campuses might have it.' : anyFilter ? 'Try a different search, or clear your filters.' : emp.body}</p>
            <div className="row" style={{ justifyContent: 'center' }}>
              {scope === 'campus' && anyFilter && <button type="button" className="btn-primary" onClick={() => setScope('network')}>Search all open campuses</button>}
              {!anyFilter && <button type="button" className="btn-primary" onClick={onCreate}>{emp.cta}</button>}
              {anyFilter && <button type="button" className="btn-ghost" onClick={reset}>Clear filters</button>}
            </div>
          </div>
        ) : <div className={section === 'items' ? 'mk-grid' : 'mk-grid mk-grid--wide'}>{shown.map(l => <Card key={l.id} l={l} onOpen={onOpen} />)}</div>}

      <Drawer open={filters} title="Filters" onClose={() => setFilters(false)}
        footer={<><button type="button" className="btn-ghost" onClick={reset}>Reset</button><button type="button" className="btn-primary" onClick={() => setFilters(false)}>Show results</button></>}>
        <div className="stack">
          {section === 'items' && <>
            <div className="field"><label htmlFor="f-cat">Category</label><select id="f-cat" value={cat} onChange={e => setCat(e.target.value as CategoryId | 'all')}><option value="all">All categories</option>{[...itemCats, ...restCats].map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></div>
            <div className="field"><label htmlFor="f-kind">Type of post</label><select id="f-kind" value={kind} onChange={e => setKind(e.target.value as Kind | 'all')}><option value="all">Everything</option>{KINDS.filter(k => k.id !== 'service').map(k => <option key={k.id} value={k.id}>{k.label}</option>)}</select></div>
          </>}
          {section === 'tickets' && <div className="field"><label htmlFor="f-ev">Event type</label><select id="f-ev" value={evType} onChange={e => setEvType(e.target.value)}>{EVENT_TYPES.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}</select></div>}
          {section === 'tutoring' && <>
            <div className="field"><label htmlFor="t-code">Class</label><input id="t-code" value={code} maxLength={20} onChange={e => setCode(e.target.value)} placeholder="MIS 430" /></div>
            <div className="field"><label htmlFor="t-sort">Sort by</label><select id="t-sort" value={sort} onChange={e => setSort(e.target.value as 'best' | 'rate')}><option value="best">Best class match</option><option value="rate">Lowest rate</option></select></div>
          </>}
          <div className="field"><span className="field-label" id="f-where">Where</span>
            <div className="segmented" role="group" aria-labelledby="f-where"><button type="button" aria-pressed={scope === 'campus'} onClick={() => setScope('campus')}>My campus</button><button type="button" aria-pressed={scope === 'network'} onClick={() => setScope('network')}>All open campuses</button></div></div>
          <div className="field"><label htmlFor="f-price">{section === 'tutoring' ? 'Max rate (USD per hour)' : section === 'tickets' ? 'Max price per ticket (USD)' : 'Max price (USD)'}</label><input id="f-price" type="number" min={0} max={1000} value={maxPrice} onChange={e => setMaxPrice(e.target.value)} placeholder="No limit" /></div>
          {section === 'items' && <div className="field"><label htmlFor="f-cond">Condition</label><select id="f-cond" value={cond} onChange={e => setCond(e.target.value)}><option value="">Any</option>{CONDITIONS.map(c => <option key={c}>{c}</option>)}</select></div>}
          {section === 'tickets' && <div className="row"><div className="field" style={{ flex: 1 }}><label htmlFor="f-from">From</label><input id="f-from" type="date" value={from} onChange={e => setFrom(e.target.value)} /></div><div className="field" style={{ flex: 1 }}><label htmlFor="f-to">To</label><input id="f-to" type="date" value={to} onChange={e => setTo(e.target.value)} /></div></div>}
          {section === 'tutoring' && <div className="field"><label htmlFor="f-mode">Format</label><select id="f-mode" value={mode} onChange={e => setMode(e.target.value)}><option value="any">Any</option><option value="in_person">In person</option><option value="online">Online</option></select></div>}
          {section === 'items' && <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>Wanted posts show only when you pick "Wanted".</p>}
        </div>
      </Drawer>
    </div>
  )
}

/* ---------- My listings ---------- */
function Mine({ onEdit, onCreate, push }: { onEdit: (l: ListingV2) => void; onCreate: () => void; push: (k: 'error' | 'success' | 'info', t: string, b?: string) => void }) {
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [items, setItems] = useState<ListingV2[] | null>(null)
  const [error, setError] = useState(false)
  const load = useCallback(async () => {
    try {
      const r = await fetchRef.current('/listings?scope=mine')
      if (!r.ok) throw new Error(String(r.status))
      setItems((await r.json()).listings ?? []); setError(false)
    } catch { setError(true) }
  }, [])
  useEffect(() => { if (user) load() }, [user, load])

  async function setStatus(l: ListingV2, status: 'sold' | 'removed') {
    try {
      const r = await fetchRef.current(`/listings/${l.id}`, { method: 'PATCH', body: JSON.stringify({ status }) })
      if (!r.ok) { push('error', "Couldn't update the listing", await errorMessage(r)); return }
      push('success', status === 'sold' ? 'Marked done' : 'Listing removed'); load()
    } catch { push('error', "Couldn't update the listing", 'Network problem. Try again.') }
  }

  if (error) return <div className="warning" role="alert"><span>We couldn't load your listings.</span><button type="button" className="btn-ghost-sm" onClick={load}>Try again</button></div>
  if (!items) return <div className="skeleton-block" aria-busy="true" aria-label="Loading your listings" />
  if (items.length === 0) return <div className="empty"><Robot name="books" size={72} /><div className="empty-title">You haven't posted anything</div><p className="empty-body">Done with a textbook? Got spare tickets or time to tutor? It takes a minute.</p><button type="button" className="btn-primary" onClick={onCreate}>Sell or post something</button></div>
  return (
    <div className="stack" style={{ gap: 'var(--s-2)' }}>
      {items.map(l => (
        <div key={l.id} className="listing">
          <div><strong>{l.ticket?.event || l.title}</strong><div className="chip-row" style={{ marginTop: 'var(--s-1)' }}><span className={`badge ${l.status === 'available' ? 'badge-ok' : ''}`}>{l.status}</span>{l.flagged && <span className="badge badge-warn">Under review</span>}{l.expired && <span className="badge badge-warn">Event passed</span>}</div></div>
          <div className="stack" style={{ alignItems: 'flex-end', gap: 'var(--s-2)' }}>
            <span className="price">{kindOf(l) === 'free' ? 'Free' : kindOf(l) === 'wanted' ? 'Wanted' : kindOf(l) === 'trade' ? 'Trade' : money(l.price)}</span>
            {l.status === 'available' && <div className="row">
              {!l.expired && <button type="button" className="btn-ghost btn-sm" onClick={() => onEdit(l)}>Edit</button>}
              {!l.expired && <button type="button" className="btn-ghost btn-sm" onClick={() => setStatus(l, 'sold')}>{DONE_LABEL[kindOf(l)]}</button>}
              <button type="button" className="btn-ghost btn-sm" onClick={() => setStatus(l, 'removed')}>Remove</button>
            </div>}
          </div>
        </div>
      ))}
    </div>
  )
}
