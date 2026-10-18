import { useCallback, useState } from 'react'
import { Pressable, View } from 'react-native'
import { useFocusEffect } from 'expo-router'
import * as Haptics from 'expo-haptics'
import type { Course, UnassignedItem } from 'shared/types'
import { useAuth } from '../../../src/auth/AuthContext'
import { SkeletonCards } from '../../../src/components/Skeleton'
import { TabScreen } from '../../../src/components/TabScreen'
import { Button, Card, EmptyState, ErrorNote, space, T } from '../../../src/components/ui'
import { useTheme } from '../../../src/theme/ThemeProvider'
import { friendly, notAvailable } from '../../../src/util/errors'

/** Blackboard events we could not place with confidence (FEED_API.md). One tap on a class assigns. A friendly place, not an error. */
export default function Unassigned() {
  const t = useTheme()
  const { api } = useAuth()
  const [items, setItems] = useState<UnassignedItem[] | null>(null)
  const [courses, setCourses] = useState<Course[]>([])
  const [na, setNa] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [list, cs] = await Promise.all([api.getUnassigned(), api.getCourses().catch(() => [] as Course[])])
      setItems(list); setCourses(cs.filter((c) => c.status === 'READY')); setNa(false); setError(null)
    } catch (e) { if (notAvailable(e)) setNa(true); else setError(friendly(e)); setItems((x) => x ?? []) }
  }, [api])
  useFocusEffect(useCallback(() => { void load() }, [load]))

  async function assign(uid: string, courseId: string) {
    try {
      const r = await api.assignFeedItem(uid, courseId)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      setMsg(r.alsoAssigned ? `Added, and ${r.alsoAssigned} similar item${r.alsoAssigned === 1 ? '' : 's'}.` : 'Added.')
      await load()
    } catch (e) { setError(friendly(e)) }
  }
  async function dismiss(uid: string) {
    try { await api.dismissFeedItem(uid); await load() } catch (e) { setError(friendly(e)) }
  }

  if (items === null) return <TabScreen><SkeletonCards count={3} /></TabScreen>
  if (na) return <TabScreen><EmptyState icon="mail-unread-outline" title="Blackboard inbox is coming soon" body="Items from Blackboard that we cannot match to a class will wait here for one tap." /></TabScreen>
  return (
    <TabScreen>
      <T kind="body" color={t.muted}>Blackboard events we could not match to a class with confidence. Tap the class each one belongs to.</T>
      {error ? <ErrorNote message={error} /> : null}
      {msg ? <T kind="footnote" color={t.success}>{msg}</T> : null}
      {items.length === 0 ? <EmptyState icon="checkmark-done-outline" title="Inbox is empty" body="Everything from Blackboard has a class. New items that need a hand will show up here." /> : items.map((u) => {
        const suggested = u.suggestions.map((s) => s.courseId)
        const ordered = [...courses.filter((c) => suggested.includes(c.id)).sort((a, b) => suggested.indexOf(a.id) - suggested.indexOf(b.id)), ...courses.filter((c) => !suggested.includes(c.id))]
        return (
          <Card key={u.uid} style={{ gap: space.sm }}>
            <T kind="callout">{u.title}</T>
            <T kind="footnote" color={t.muted}>{u.dueDate ?? 'No date'}{u.dueTime ? `, ${u.dueTime}` : ''}</T>
            {u.description ? <T kind="footnote" color={t.muted} numberOfLines={3}>{u.description}</T> : null}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.xs }}>
              {ordered.map((c) => (
                <Pressable key={c.id} accessibilityRole="button" accessibilityLabel={`Assign to ${c.courseCode || c.title}`} onPress={() => assign(u.uid, c.id)}
                  style={{ minHeight: 44, paddingHorizontal: space.md, justifyContent: 'center', flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 999, borderWidth: 1, borderColor: c.color, backgroundColor: suggested.includes(c.id) ? t.accentTint : t.surface }}>
                  <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: c.color }} />
                  <T kind="footnote" style={{ fontWeight: '600' }}>{c.courseCode || c.title}</T>
                </Pressable>
              ))}
            </View>
            <Button title="Not a deadline for any class" variant="plain" onPress={() => dismiss(u.uid)} />
          </Card>
        )
      })}
    </TabScreen>
  )
}
