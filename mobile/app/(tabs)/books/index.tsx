import { useCallback, useState } from 'react'
import { Pressable, RefreshControl, View } from 'react-native'
import { useFocusEffect } from 'expo-router'
import * as Haptics from 'expo-haptics'
import type { BookMatchesResponse, Listing, ListingsResponse } from 'shared/types'
import { useAuth } from '../../../src/auth/AuthContext'
import { ListingCard } from '../../../src/components/ListingCard'
import { ListingForm } from '../../../src/components/ListingForm'
import { InterestedSheet, ReportSheet } from '../../../src/components/ListingSheets'
import { SkeletonCards } from '../../../src/components/Skeleton'
import { TabScreen } from '../../../src/components/TabScreen'
import { Button, Card, EmptyState, ErrorNote, radius, space, T } from '../../../src/components/ui'
import { ClassTheme, useTheme } from '../../../src/theme/ThemeProvider'

type View_ = 'books' | 'market'
type Scope = 'campus' | 'network' | 'mine'

function Seg<K extends string>({ options, value, onChange }: { options: { key: K; label: string }[]; value: K; onChange: (k: K) => void }) {
  const t = useTheme()
  return (
    <View accessibilityRole="tablist" style={{ flexDirection: 'row', padding: 4, gap: 4, borderRadius: radius.control, backgroundColor: t.accentTint }}>
      {options.map((o) => {
        const on = o.key === value
        return (
          <Pressable key={o.key} accessibilityRole="tab" accessibilityState={{ selected: on }} onPress={() => onChange(o.key)}
            style={{ flex: 1, minHeight: 40, alignItems: 'center', justifyContent: 'center', borderRadius: radius.control - 3, backgroundColor: on ? t.accent : 'transparent' }}>
            <T kind="footnote" color={on ? t.accentInk : t.accentStrong} style={{ fontWeight: '600' }}>{o.label}</T>
          </Pressable>
        )
      })}
    </View>
  )
}

const unavailable = (e: unknown) => {
  const s = (e as { status?: number })?.status
  return s === 404 || s === 403
}

export default function Books() {
  const t = useTheme()
  const { api, me } = useAuth()
  const [view, setView] = useState<View_>('books')
  const [scope, setScope] = useState<Scope>('campus')
  const [matches, setMatches] = useState<BookMatchesResponse | null>(null)
  const [market, setMarket] = useState<ListingsResponse | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [form, setForm] = useState<{ listing: Listing | null } | null>(null)
  const [interested, setInterested] = useState<Listing | null>(null)
  const [reporting, setReporting] = useState<Listing | null>(null)

  const load = useCallback(async () => {
    try {
      if (view === 'books') setMatches(await api.getBookMatches())
      else setMarket(await api.getListings(scope))
      setError(null)
    } catch (e) {
      if (view === 'books') setMatches(null); else setMarket(null)
      // 404/403 = route not deployed yet: quiet empty state instead of an error.
      setError(unavailable(e) ? null : e instanceof Error ? e.message : "Can't load books right now.")
    } finally { setLoaded(true) }
  }, [api, view, scope])
  useFocusEffect(useCallback(() => { setLoaded(false); void load() }, [load]))

  const markSold = async (l: Listing) => {
    try { await api.updateListing(l.id, { status: 'sold' }); void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); void load() }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't update that listing.") }
  }

  const categories = me?.tenant.categories ?? ['textbooks']
  const pickupSpots = market?.campus.pickupSpots ?? matches?.pickupSpots ?? me?.tenant.pickupSpots ?? []
  const cards = (list: Listing[]) => list.map((l) => (
    <ListingCard key={l.id} l={l} onInterested={setInterested} onReport={setReporting} onEdit={(x) => setForm({ listing: x })} onSold={markSold} />
  ))

  return (
    <>
      <TabScreen refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false) }} tintColor={t.accentStrong} colors={[t.accent]} />}>
        <Seg options={[{ key: 'books', label: 'My books' }, { key: 'market', label: 'Marketplace' }]} value={view} onChange={(v) => { setView(v); setLoaded(false) }} />
        {error ? <ErrorNote message={error} /> : null}

        {view === 'books' ? (
          !loaded ? <SkeletonCards /> : matches && matches.courses.some((c) => c.books.length) ? (
            matches.courses.filter((c) => c.books.length).map((c) => (
              <ClassTheme key={c.courseId} hex={c.color}>
                <View style={{ gap: space.sm }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: c.color }} />
                    <T kind="label" color={t.muted}>{c.courseCode || c.title}</T>
                  </View>
                  {c.books.map((b, i) => (
                    <View key={i} style={{ gap: space.sm }}>
                      <Card style={{ gap: 2, borderLeftColor: c.color, borderLeftWidth: 4 }}>
                        <T kind="callout">{b.title}</T>
                        <T kind="footnote" color={t.muted}>{[b.author, b.edition, b.required ? 'Required' : 'Optional'].filter(Boolean).join(' · ')}</T>
                        <T kind="footnote" color={b.matches.length ? t.accentStrong : t.muted} style={{ fontWeight: '600' }}>
                          {b.matches.length ? `${b.matches.length} match${b.matches.length === 1 ? '' : 'es'}${b.bestOnYourCampus != null ? `, from $${b.bestOnYourCampus} on your campus` : b.bestPrice != null ? `, from $${b.bestPrice}` : ''}` : 'No copies listed yet'}
                        </T>
                      </Card>
                      {cards(b.matches.map((m) => m.listing))}
                    </View>
                  ))}
                </View>
              </ClassTheme>
            ))
          ) : (
            <EmptyState icon="book-outline" title="No books to match"
              body="Once a syllabus lists required books, we'll look for copies from students on your campus first." />
          )
        ) : (
          <>
            <Seg options={[{ key: 'campus', label: 'My campus' }, { key: 'network', label: 'Network' }, { key: 'mine', label: 'Mine' }]} value={scope} onChange={(s) => { setScope(s); setLoaded(false) }} />
            <Button title="List my old copy" variant="secondary" onPress={() => setForm({ listing: null })} />
            {!loaded ? <SkeletonCards /> : market && market.listings.length ? (
              <>
                <T kind="caption" color={t.muted}>{market.safety}</T>
                {cards(market.listings)}
              </>
            ) : (
              <EmptyState icon="pricetag-outline"
                title={scope === 'mine' ? 'You have no listings' : 'No listings yet'}
                body={scope === 'mine' ? 'List a book you no longer need and classmates can find it.' : 'Nothing is for sale here right now. Be the first to list a book.'} />
            )}
          </>
        )}
      </TabScreen>

      {form ? (
        <ListingForm
          key={form.listing?.id ?? 'new'} visible listing={form.listing} categories={categories} pickupSpots={pickupSpots}
          onClose={() => setForm(null)} onSaved={() => { setForm(null); void load() }}
        />
      ) : null}
      <InterestedSheet listing={interested} onClose={() => setInterested(null)} />
      <ReportSheet listing={reporting} onClose={() => setReporting(null)} />
    </>
  )
}
