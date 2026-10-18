import { useState } from 'react'
import { Alert, Modal, Platform, SafeAreaView, ScrollView, Share, View } from 'react-native'
import * as Clipboard from 'expo-clipboard'
import * as Haptics from 'expo-haptics'
import { useAuth } from '../auth/AuthContext'
import { config } from '../config'
import { useTheme } from '../theme/ThemeProvider'
import { Button, Card, ErrorNote, mono, space, T } from './ui'

/** Subscribe-URL sheet: masked URL, copy, share, rotate. The token is a secret: never logged, masked on screen. */
export function SubscribeSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const t = useTheme()
  const { me, api, reloadMe } = useAuth()
  const [override, setOverride] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const token = override ?? me?.profile.calToken ?? ''
  const url = token ? `${config.apiUrl}/cal/${token}.ics` : ''
  const masked = token ? `${config.apiUrl}/cal/${token.slice(0, 4)}${'•'.repeat(12)}.ics` : 'Not available yet'

  async function copy() {
    await Clipboard.setStringAsync(url)
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
    setNote('Copied. Paste it into Google Calendar, Apple Calendar or Outlook as a subscription.')
  }
  async function share() {
    try { await Share.share(Platform.OS === 'ios' ? { url } : { message: url }) } catch { /* cancelled */ }
  }
  function rotate() {
    Alert.alert('Make a new link?', 'The current link stops working right away, so any calendar subscribed to it will need the new one.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Make new link', style: 'destructive',
        onPress: async () => {
          setBusy(true); setError(null); setNote(null)
          try {
            const r = await api.rotateCalendarToken()
            setOverride(r.calToken)
            void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
            setNote('New link ready. The old one no longer works.')
            void reloadMe()
          } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not make a new link.')
          } finally { setBusy(false) }
        },
      },
    ])
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle={Platform.OS === 'ios' ? 'pageSheet' : undefined} onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
        <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.lg }}>
          <T kind="title">Subscribe to your calendar</T>
          <T kind="body" color={t.muted}>
            This private link shows your deadlines in any calendar app. Treat it like a password: anyone with it can see your deadlines.
          </T>
          <Card style={{ gap: space.sm }}>
            <T kind="caption" color={t.muted}>Your link</T>
            <T kind="footnote" style={{ fontFamily: mono }}>{masked}</T>
          </Card>
          {error ? <ErrorNote message={error} /> : null}
          {note ? <T kind="footnote" color={t.success}>{note}</T> : null}
          <Button title="Copy link" onPress={copy} disabled={!url} />
          <Button title="Share link" variant="secondary" onPress={share} disabled={!url} />
          <Button title="Make a new link" variant="plain" onPress={rotate} loading={busy} disabled={!url} />
          <T kind="caption" color={t.muted}>
            Google Calendar refreshes subscribed links on its own schedule, often many hours. Apple and Outlook are faster. The Calendar tab here is always live.
          </T>
          <View><Button title="Done" variant="secondary" onPress={onClose} /></View>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  )
}
