import { useState } from 'react'
import { Alert, Modal, Platform, Pressable, SafeAreaView, View } from 'react-native'
import * as Haptics from 'expo-haptics'
import type { Listing, ReportReason } from 'shared/types'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../theme/ThemeProvider'
import { Button, ErrorNote, radius, space, T } from './ui'

const sheetProps = { animationType: 'slide' as const, presentationStyle: Platform.OS === 'ios' ? ('pageSheet' as const) : undefined }

/** PLACEHOLDER. Buyer-to-seller contact is undecided (Luca is choosing), so this only says "coming soon". */
export function InterestedSheet({ listing, onClose }: { listing: Listing | null; onClose: () => void }) {
  const t = useTheme()
  return (
    <Modal visible={!!listing} {...sheetProps} onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: t.bg, padding: space.lg, gap: space.lg, justifyContent: 'center' }}>
        <T kind="title">Coming soon</T>
        <T kind="body" color={t.muted}>
          Messaging the seller is not ready yet. For now, pickup happens at campus spots, and payment is in person, never through this app.
        </T>
        <Button title="Got it" onPress={onClose} />
      </SafeAreaView>
    </Modal>
  )
}

const REASONS: { key: ReportReason; label: string }[] = [
  { key: 'spam', label: 'Spam' },
  { key: 'scam', label: 'Scam' },
  { key: 'prohibited', label: 'Not allowed here' },
  { key: 'wrong_info', label: 'Wrong information' },
  { key: 'other', label: 'Something else' },
]

export function ReportSheet({ listing, onClose }: { listing: Listing | null; onClose: () => void }) {
  const t = useTheme()
  const { api } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function pick(r: { key: ReportReason; label: string }) {
    if (!listing) return
    Alert.alert('Report this listing?', `Reason: ${r.label}. Three reports from different students hide a listing.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Report', style: 'destructive',
        onPress: async () => {
          setBusy(true); setError(null)
          try {
            await api.reportListing(listing.id, r.key)
            void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
            Alert.alert('Thanks', 'We got your report.')
            onClose()
          } catch (e) { setError(e instanceof Error ? e.message : 'Could not send the report.') } finally { setBusy(false) }
        },
      },
    ])
  }

  return (
    <Modal visible={!!listing} {...sheetProps} onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: t.bg, padding: space.lg, gap: space.md }}>
        <T kind="title">Report listing</T>
        <T kind="body" color={t.muted}>What is wrong with it?</T>
        {REASONS.map((r) => (
          <Pressable key={r.key} accessibilityRole="button" disabled={busy} onPress={() => pick(r)}
            style={{ minHeight: 52, justifyContent: 'center', paddingHorizontal: space.md, borderRadius: radius.control, backgroundColor: t.surface, borderWidth: 1, borderColor: t.border }}>
            <T kind="body">{r.label}</T>
          </Pressable>
        ))}
        {error ? <ErrorNote message={error} /> : null}
        <View><Button title="Cancel" variant="plain" onPress={onClose} /></View>
      </SafeAreaView>
    </Modal>
  )
}
