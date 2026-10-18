import { useCallback, useEffect, useState } from 'react'
import { Alert, View } from 'react-native'
import * as Haptics from 'expo-haptics'
import type { MeFeed } from 'shared/types'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../theme/ThemeProvider'
import { ago } from '../util/time'
import { friendly, notAvailable } from '../util/errors'
import { Button, Card, ErrorNote, space, T, TextField } from './ui'

/** Settings: connect the secret Blackboard calendar link (FEED_API.md). Typed into a secure field, only the masked form is shown. */
export function FeedCard() {
  const t = useTheme()
  const { api } = useAuth()
  const [feed, setFeed] = useState<MeFeed | null>(null)
  const [na, setNa] = useState(false)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try { setFeed(await api.getMeFeed()); setNa(false) } catch (e) { if (notAvailable(e)) setNa(true) }
  }, [api])
  useEffect(() => { void load() }, [load])

  async function save() {
    const u = url.trim()
    if (!/^(https|webcal):\/\//i.test(u)) { setError('Paste the full calendar link. It starts with https://'); return }
    setBusy(true); setError(null); setMsg(null)
    try {
      const f = await api.putMeFeed(u)
      setUrl('')
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      try { await api.syncMeFeed(); setMsg('Connected. Pulled your calendar.') } catch { setMsg('Connected. First check will run shortly.') }
      setFeed(f); await load()
    } catch (e) { void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning); setError(friendly(e, "That link didn't work.")) } finally { setBusy(false) }
  }
  async function check() {
    setBusy(true); setError(null); setMsg(null)
    try { const r = await api.syncMeFeed(); setMsg(r.added || r.updated ? `Found ${r.added} new and ${r.updated} changed.` : 'Nothing new.'); await load() }
    catch (e) { setError(friendly(e, "Couldn't check Blackboard.")) } finally { setBusy(false) }
  }
  function disconnect() {
    Alert.alert('Disconnect Blackboard?', 'We forget the link and the inbox. Deadlines already added stay.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Disconnect', style: 'destructive', onPress: async () => { try { await api.deleteMeFeed(); setFeed({ connected: false }) } catch (e) { setError(friendly(e)) } } },
    ])
  }

  if (na) {
    return <Card><T kind="body" color={t.muted}>Blackboard connection is not available yet. It is coming soon.</T></Card>
  }
  return (
    <Card style={{ gap: space.md }}>
      {feed?.connected ? (
        <>
          <T kind="callout">Blackboard connected</T>
          <T kind="footnote" color={t.muted}>{feed.urlMasked}</T>
          <T kind="footnote" color={t.muted}>{feed.lastCheckedAt ? `Checked ${ago(feed.lastCheckedAt)}` : 'Not checked yet'}{feed.counts ? `  ·  ${feed.counts.unassigned} in your inbox` : ''}</T>
          {feed.lastError ? <T kind="footnote" color={t.danger}>{feed.lastError.message}</T> : null}
          <Button title="Check now" variant="secondary" onPress={check} loading={busy} disabled={(feed.syncCooldownSeconds ?? 0) > 0} />
          <Button title="Disconnect" variant="plain" onPress={disconnect} />
        </>
      ) : (
        <>
          <T kind="callout">Connect Blackboard</T>
          <T kind="footnote" color={t.muted}>In Blackboard, open Calendar, then Settings, then Share Calendar, and copy the link. It is private: treat it like a password. We never ask for your Blackboard password.</T>
          <View>
            <TextField label="Calendar link" value={url} onChangeText={setUrl} secureTextEntry autoCapitalize="none" autoCorrect={false} placeholder="https://..." textContentType="URL" />
          </View>
          <Button title="Connect" onPress={save} loading={busy} />
        </>
      )}
      {msg ? <T kind="footnote" color={t.success}>{msg}</T> : null}
      {error ? <ErrorNote message={error} /> : null}
      <T kind="caption" color={t.muted}>Blackboard's calendar shares dates and events only, not announcements, files or grades.</T>
    </Card>
  )
}
