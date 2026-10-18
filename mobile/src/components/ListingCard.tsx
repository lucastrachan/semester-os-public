import { Pressable, View } from 'react-native'
import type { Listing } from 'shared/types'
import { useTheme } from '../theme/ThemeProvider'
import { Card, mono, space, T } from './ui'

function Badge({ text, strong }: { text: string; strong?: boolean }) {
  const t = useTheme()
  return (
    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: strong ? t.accent : t.surface2, borderWidth: strong ? 0 : 1, borderColor: t.border }}>
      <T kind="caption" color={strong ? t.accentInk : t.ink} style={{ fontWeight: '600' }}>{text}</T>
    </View>
  )
}

export const priceLabel = (p: number) => (p === 0 ? 'Free' : `$${Number.isInteger(p) ? p : p.toFixed(2)}`)

/** One listing. All text (title, description, seller name) is user text: plain Text, never auto-linked. */
export function ListingCard({
  l, onInterested, onReport, onEdit, onSold,
}: {
  l: Listing
  onInterested?: (l: Listing) => void
  onReport?: (l: Listing) => void
  onEdit?: (l: Listing) => void
  onSold?: (l: Listing) => void
}) {
  const t = useTheme()
  return (
    <Card style={{ gap: space.sm }}>
      <View style={{ flexDirection: 'row', gap: space.md, alignItems: 'flex-start' }}>
        <View style={{ flex: 1, gap: 2 }}>
          <T kind="callout">{l.title}</T>
          {l.author || l.edition ? <T kind="footnote" color={t.muted}>{[l.author, l.edition].filter(Boolean).join(' · ')}</T> : null}
        </View>
        <T kind="title" color={t.accentStrong} style={{ fontFamily: mono }}>{priceLabel(l.price)}</T>
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.xs }}>
        <Badge text={l.condition} />
        <Badge text={l.onYourCampus ? `${l.campus.shortName} · your campus` : l.campus.shortName} strong={l.onYourCampus} />
        {l.courseCode ? <Badge text={l.courseCode} /> : null}
        {l.demo ? <Badge text="Demo listing" /> : null}
        {l.mine && l.status !== 'available' ? <Badge text={l.status === 'sold' ? 'Sold' : 'Hidden'} /> : null}
        {l.mine && l.flagged ? <Badge text="Reported" /> : null}
      </View>
      {l.description ? <T kind="footnote">{l.description}</T> : null}
      {l.pickupSpot ? <T kind="footnote" color={t.muted}>Pickup: {l.pickupSpot}</T> : null}
      <T kind="caption" color={t.muted}>Seller: {l.sellerName}</T>
      <View style={{ flexDirection: 'row', gap: space.md, alignItems: 'center', flexWrap: 'wrap' }}>
        {l.mine ? (
          <>
            {onEdit ? <Action label="Edit" onPress={() => onEdit(l)} /> : null}
            {onSold && l.status === 'available' ? <Action label="Mark sold" onPress={() => onSold(l)} /> : null}
          </>
        ) : (
          <>
            {/* PLACEHOLDER: buyer-to-seller contact is not decided yet. */}
            {onInterested ? <Action label="I'm interested" onPress={() => onInterested(l)} /> : null}
            {onReport ? <Action label="Report" onPress={() => onReport(l)} danger /> : null}
          </>
        )}
      </View>
    </Card>
  )
}

function Action({ label, onPress, danger }: { label: string; onPress: () => void; danger?: boolean }) {
  const t = useTheme()
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={{ minHeight: 44, justifyContent: 'center' }}>
      <T kind="footnote" color={danger ? t.danger : t.accentStrong} style={{ fontWeight: '700' }}>{label}</T>
    </Pressable>
  )
}
