import { useState } from 'react'
import { KeyboardAvoidingView, Modal, Platform, Pressable, SafeAreaView, ScrollView, View } from 'react-native'
import * as Haptics from 'expo-haptics'
import { ApiError } from 'shared/api'
import type { Listing, ListingCondition } from 'shared/types'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../theme/ThemeProvider'
import { Button, ErrorNote, radius, space, T, TextField } from './ui'

const CONDITIONS: ListingCondition[] = ['New', 'Like new', 'Good', 'Acceptable']

function Chips({ options, value, onChange, label }: { options: string[]; value: string; onChange: (v: string) => void; label: string }) {
  const t = useTheme()
  return (
    <View style={{ gap: space.xs }}>
      <T kind="footnote" color={t.muted} style={{ fontWeight: '600' }}>{label}</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.xs }}>
        {options.map((o) => {
          const on = o === value
          return (
            <Pressable key={o} accessibilityRole="button" accessibilityState={{ selected: on }} onPress={() => onChange(on ? '' : o)}
              style={{ minHeight: 44, paddingHorizontal: space.md, justifyContent: 'center', borderRadius: radius.control, backgroundColor: on ? t.accent : t.surface, borderWidth: 1, borderColor: on ? t.accent : t.border }}>
              <T kind="footnote" color={on ? t.accentInk : t.ink} style={{ fontWeight: '600' }}>{o}</T>
            </Pressable>
          )
        })}
      </View>
    </View>
  )
}

/** Create or edit a listing. Links in the description are rejected by the server, so we warn up front. */
export function ListingForm({
  visible, listing, categories, pickupSpots, onClose, onSaved,
}: {
  visible: boolean
  listing: Listing | null
  categories: string[]
  pickupSpots: string[]
  onClose: () => void
  onSaved: () => void
}) {
  const t = useTheme()
  const { api } = useAuth()
  const [title, setTitle] = useState(listing?.title ?? '')
  const [author, setAuthor] = useState(listing?.author ?? '')
  const [isbn, setIsbn] = useState(listing?.isbn ?? '')
  const [edition, setEdition] = useState(listing?.edition ?? '')
  const [price, setPrice] = useState(listing ? String(listing.price) : '')
  const [condition, setCondition] = useState<string>(listing?.condition ?? 'Good')
  const [category, setCategory] = useState(listing?.category ?? categories[0] ?? 'textbooks')
  const [courseCode, setCourseCode] = useState(listing?.courseCode ?? '')
  const [description, setDescription] = useState(listing?.description ?? '')
  const [pickupSpot, setPickupSpot] = useState(listing?.pickupSpot ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    const p = Number(price)
    if (title.trim().length < 3) { setError('Add a title (at least 3 characters).'); return }
    if (price.trim() === '' || !Number.isFinite(p) || p < 0 || p > 1000) { setError('Enter a price from 0 to 1000 (0 means free).'); return }
    if (!category) { setError('Pick a category.'); return }
    if (/https?:|www\./i.test(description)) { setError("Links aren't allowed in the description.") ; return }
    setBusy(true); setError(null)
    const body = {
      title: title.trim(), price: Math.round(p * 100) / 100, condition: condition as ListingCondition, category,
      author: author.trim(), edition: edition.trim(), courseCode: courseCode.trim(), description: description.trim(), pickupSpot: pickupSpot.trim(),
      isbn: isbn.trim() ? isbn.trim() : null,
    }
    try {
      if (listing) await api.updateListing(listing.id, body)
      else await api.createListing(body)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      onSaved()
    } catch (e) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
      if (e instanceof ApiError && e.code === 'daily_cap') setError('You have listed the maximum for today. Try again tomorrow.')
      else if (e instanceof ApiError && e.code === 'limit') setError('You have 40 active listings. Mark one sold first.')
      else setError(e instanceof Error ? e.message : 'Could not save the listing.')
    } finally { setBusy(false) }
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle={Platform.OS === 'ios' ? 'pageSheet' : undefined} onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: space.lg, gap: space.lg }}>
            <T kind="title">{listing ? 'Edit listing' : 'List my old copy'}</T>
            <TextField label="Title" value={title} onChangeText={setTitle} maxLength={160} />
            <TextField label="Author (optional)" value={author} onChangeText={setAuthor} />
            <TextField label="ISBN (optional)" value={isbn} onChangeText={setIsbn} keyboardType="number-pad" maxLength={17} />
            <TextField label="Edition (optional)" value={edition} onChangeText={setEdition} placeholder="8th" />
            <TextField label="Price in dollars" value={price} onChangeText={setPrice} keyboardType="decimal-pad" placeholder="0 for free" />
            <Chips label="Condition" options={CONDITIONS} value={condition} onChange={(v) => v && setCondition(v)} />
            <Chips label="Category" options={categories.length ? categories : ['textbooks']} value={category} onChange={(v) => v && setCategory(v)} />
            <TextField label="Class code (optional)" value={courseCode} onChangeText={setCourseCode} autoCapitalize="characters" placeholder="MIS 405" />
            <TextField label="Description (optional, no links)" value={description} onChangeText={setDescription} multiline maxLength={500} style={{ minHeight: 90, textAlignVertical: 'top', paddingTop: 12 }} />
            {pickupSpots.length ? <Chips label="Pickup spot" options={pickupSpots} value={pickupSpot} onChange={setPickupSpot} /> : (
              <TextField label="Pickup spot (optional)" value={pickupSpot} onChangeText={setPickupSpot} maxLength={80} />
            )}
            <T kind="caption" color={t.muted}>Meet in a public, well-lit campus spot. Payment happens in person, never through this app.</T>
            {error ? <ErrorNote message={error} /> : null}
            <Button title={listing ? 'Save changes' : 'Post listing'} onPress={save} loading={busy} />
            <Button title="Cancel" variant="plain" onPress={onClose} />
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Modal>
  )
}
