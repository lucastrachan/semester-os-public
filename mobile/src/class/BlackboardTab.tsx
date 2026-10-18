import { useCallback, useEffect, useState } from 'react'
import { Pressable, View } from 'react-native'
import { useRouter } from 'expo-router'
import * as Haptics from 'expo-haptics'
import { Ionicons } from '@expo/vector-icons'
import type { ClassFeed, Course } from 'shared/types'
import { useAuth } from '../auth/AuthContext'
import { SkeletonCards } from '../components/Skeleton'
import { Button, Card, ErrorNote, space, T } from '../components/ui'
import { useTheme } from '../theme/ThemeProvider'
import { ago } from '../util/time'
import { friendly, notAvailable } from '../util/errors'
import { ComingSoon } from './NotAvailable'

/** Class Blackboard tab (FEED_API.md): status, Check now, "Is this <class>?" one-tap rows, items from Blackboard. */
export function BlackboardTab({ course, onChanged }: { course: Course; onChanged: () => void }) {
  const t = useTheme()
  const router = useRouter()
  const { api } = useAuth()
  const code = course.courseCode || course.title
  const [feed, setFeed] = useState<ClassFeed | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'na' | 'error'>('loading')
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [coolUntil, setCoolUntil] = useState(0)

  const load = useCallback(async () => {
    try {
      const f = await api.getClassFeed(course.id)
      setFeed(f); setState('ok'); setMsg(null)
      if (f.stats?.syncCooldownSeconds) setCoolUntil(Date.now() + f.stats.syncCooldownSeconds * 1000)
      if (f.connected) void api.feedSeen(course.id).catch(() => {})
    } catch (e) { setState(notAvailable(e) ? 'na' : 'error'); setMsg(friendly(e)) }
  }, [api, course.id])
  useEffect(() => { void load() }, [load])

  async function check() {
    setBusy(true); setMsg(null)
    try {
      const r = await api.syncClassFeed(course.id)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      setMsg(r.added || r.updated ? `Found ${r.added} new and ${r.updated} changed.` : 'Nothing new.')
      if (r.stats?.syncCooldownSeconds) setCoolUntil(Date.now() + r.stats.syncCooldownSeconds * 1000)
      else setCoolUntil(Date.now() + 120000)
      await load(); onChanged()
    } catch (e) { setMsg(friendly(e, "Couldn't check Blackboard.")) } finally { setBusy(false) }
  }

  async function assign(uid: string) {
    try {
      await api.assignFeedItem(uid, course.id)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      await load(); onChanged()
    } catch (e) { setMsg(friendly(e)) }
  }

  if (state === 'loading') return <SkeletonCards count={2} />
  if (state === 'na') return <ComingSoon icon="logo-web-component" title="Blackboard is coming soon" body={`Your ${code} agent will watch your Blackboard calendar for new deadlines. This isn't switched on yet.`} />
  if (state === 'error') return <><ErrorNote message={msg ?? 'Could not load Blackboard.'} /><Button title="Try again" onPress={load} /></>
  if (!feed?.connected) {
    return (
      <Card style={{ gap: space.md }}>
        <T kind="callout">Connect Blackboard</T>
        <T kind="body" color={t.muted}>Add your Blackboard calendar link in Settings and your {code} agent will pick up its deadlines.</T>
        <Button title="Open Settings" onPress={() => router.navigate('/settings')} />
      </Card>
    )
  }
  const s = feed.stats
  const cooling = Date.now() < coolUntil
  return (
    <View style={{ gap: space.lg }}>
      <Card style={{ gap: space.sm }}>
        <T kind="callout">{s?.lastStatus === 'error' ? 'Last check had a problem' : s?.lastCheckedAt ? `Checked ${ago(s.lastCheckedAt)}` : 'Not checked yet'}</T>
        {s?.lastError ? <T kind="footnote" color={t.danger}>{s.lastError.message}</T> : null}
        <T kind="footnote" color={t.muted}>{s ? `${s.itemCount} items from Blackboard, ${s.newItemsCount} new` : ''}</T>
        <Button title={cooling ? 'Checked recently' : 'Check now'} variant="secondary" onPress={check} loading={busy} disabled={cooling} />
        {msg ? <T kind="footnote" color={t.accentStrong}>{msg}</T> : null}
      </Card>

      {feed.unassigned.length > 0 ? (
        <View style={{ gap: space.sm }}>
          <T kind="label" color={t.muted}>Is this {code}?</T>
          {feed.unassigned.map((u) => (
            <Card key={u.uid} style={{ gap: space.xs }}>
              <T kind="callout">{u.title}</T>
              <T kind="footnote" color={t.muted}>{u.dueDate ?? 'No date'}{u.dueTime ? `, ${u.dueTime}` : ''}</T>
              <Button title={`Yes, it's ${code}`} variant="secondary" onPress={() => assign(u.uid)} />
            </Card>
          ))}
        </View>
      ) : null}

      <View style={{ gap: space.sm }}>
        <T kind="label" color={t.muted}>From Blackboard</T>
        {feed.items.length === 0 ? <T kind="body" color={t.muted}>Nothing from Blackboard for this class yet.</T> : feed.items.map((i) => (
          <Card key={i.uid} style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
            <View style={{ flex: 1, gap: 2 }}>
              <T kind="callout">{i.title}</T>
              <T kind="footnote" color={t.muted}>{[i.type, i.dueDate ?? 'No date', i.removedFromFeed ? 'removed from Blackboard' : ''].filter(Boolean).join('  ·  ')}</T>
            </View>
            {i.isNew ? <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: t.accent }}><T kind="caption" color={t.accentInk} style={{ fontWeight: '700' }}>New</T></View> : null}
          </Card>
        ))}
      </View>
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <Ionicons name="information-circle-outline" size={18} color={t.muted} />
        <T kind="caption" color={t.muted} style={{ flex: 1 }}>Blackboard's calendar shares dates and events only, not announcements, files or grades. Some instructors don't use it.</T>
      </View>
    </View>
  )
}
