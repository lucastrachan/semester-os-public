import { useCallback, useMemo, useRef, useState } from 'react'
import { Alert, Pressable, RefreshControl, SectionList, View } from 'react-native'
import { useFocusEffect, useRouter } from 'expo-router'
import * as Haptics from 'expo-haptics'
import { Ionicons } from '@expo/vector-icons'
import type { Assignment } from 'shared/types'
import { useAuth } from '../../../src/auth/AuthContext'
import { addToPhoneCalendar, countNew } from '../../../src/calendar/phone'
import { dayLabel, loadAssignments } from '../../../src/calendar/data'
import { AssignmentRow as Row } from '../../../src/components/AssignmentRow'
import { SkeletonCards } from '../../../src/components/Skeleton'
import { SubscribeSheet } from '../../../src/components/SubscribeSheet'
import { Button, EmptyState, ErrorNote, radius, space, T } from '../../../src/components/ui'
import { ClassTheme, useTheme } from '../../../src/theme/ThemeProvider'

export default function CalendarTab() {
  const t = useTheme()
  const { api } = useAuth()
  const router = useRouter()
  const [items, setItems] = useState<Assignment[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [sheet, setSheet] = useState(false)
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    try { setItems(await loadAssignments(api)); setError(null) }
    catch (e) { setError(e instanceof Error ? e.message : "Can't load your deadlines."); setItems((x) => x ?? []) }
  }, [api])
  useFocusEffect(useCallback(() => { void load() }, [load]))

  const sections = useMemo(() => {
    const open = (items ?? [])
    const map = new Map<string, Assignment[]>()
    for (const a of open) { const k = a.dueDate ?? 'none'; map.set(k, [...(map.get(k) ?? []), a]) }
    const keys = [...map.keys()].filter((k) => k !== 'none').sort()
    const out = keys.map((k) => ({ key: k, title: dayLabel(k), data: map.get(k)! }))
    if (map.has('none')) out.push({ key: 'none', title: 'No date yet', data: map.get('none')! })
    return out
  }, [items])

  async function toggle(a: Assignment) {
    const done = !a.done
    setItems((l) => (l ?? []).map((x) => (x.id === a.id ? { ...x, done } : x))) // optimistic
    void Haptics.notificationAsync(done ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning)
    try { await api.patchAssignment(a.id, { done }) }
    catch (e) {
      setItems((l) => (l ?? []).map((x) => (x.id === a.id ? { ...x, done: a.done } : x)))
      setError(e instanceof Error ? e.message : "Couldn't save that. Try again.")
    }
  }

  async function addToPhone() {
    const n = await countNew(items ?? [])
    if (n === 0) { Alert.alert('Already up to date', 'Your open deadlines are already in your phone calendar.'); return }
    Alert.alert(`Add ${n} deadline${n === 1 ? '' : 's'} to your calendar?`, "They'll be copied into your phone's calendar as events. Your phone will ask for permission first.", [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Add', onPress: async () => {
          setAdding(true)
          try {
            const r = await addToPhoneCalendar(items ?? [], t.accent)
            if (r.denied) Alert.alert('Calendar access is off', 'Allow calendar access for this app in your phone settings to add deadlines.')
            else { void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); Alert.alert('Added', `${r.added} event${r.added === 1 ? '' : 's'} added to your calendar.`) }
          } catch { Alert.alert("Couldn't add events", 'Something went wrong talking to your calendar. Try again.') }
          finally { setAdding(false) }
        },
      },
    ])
  }

  const header = (
    <View style={{ gap: space.sm, paddingBottom: space.sm }}>
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <Button title="Add to my calendar" variant="secondary" style={{ flex: 1 }} onPress={addToPhone} loading={adding} disabled={!items?.length} />
        <Button title="Subscribe" variant="secondary" onPress={() => setSheet(true)} />
      </View>
      <Button title="Blackboard inbox" variant="plain" onPress={() => router.push('/calendar/unassigned')} />
      {error ? <ErrorNote message={error} /> : null}
    </View>
  )

  return (
    <>
      <SectionList
        style={{ backgroundColor: t.bg }}
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={{ padding: space.lg, flexGrow: 1 }}
        sections={sections}
        keyExtractor={(a) => a.id}
        stickySectionHeadersEnabled={false}
        ListHeaderComponent={header}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false) }} tintColor={t.accentStrong} colors={[t.accent]} />}
        renderSectionHeader={({ section }) => <T kind="label" color={t.muted} style={{ marginTop: space.lg, marginBottom: space.sm }}>{section.title}</T>}
        renderItem={({ item }) => (
          <View style={{ marginBottom: space.sm }}>
            {item.courseColor ? <ClassTheme hex={item.courseColor}><Row a={item} onToggle={toggle} /></ClassTheme> : <Row a={item} onToggle={toggle} />}
          </View>
        )}
        ListEmptyComponent={items ? (
          <EmptyState icon="calendar-outline" title="Nothing scheduled" body="Deadlines and study blocks from your classes show up here. Swipe right on one to mark it done." />
        ) : <SkeletonCards />}
      />
      <SubscribeSheet visible={sheet} onClose={() => setSheet(false)} />
    </>
  )
}
