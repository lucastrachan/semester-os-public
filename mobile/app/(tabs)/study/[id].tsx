import { useCallback, useEffect, useRef, useState } from 'react'
import { KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, View } from 'react-native'
import { Stack, useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Ionicons } from '@expo/vector-icons'
import * as Haptics from 'expo-haptics'
import type { Assignment, Course } from 'shared/types'
import { useAuth } from '../../../src/auth/AuthContext'
import { BlackboardTab } from '../../../src/class/BlackboardTab'
import { BooksTab } from '../../../src/class/BooksTab'
import { DeadlinesTab } from '../../../src/class/DeadlinesTab'
import { MaterialsTab } from '../../../src/class/MaterialsTab'
import { MemoryTab } from '../../../src/class/MemoryTab'
import { SyllabusTab } from '../../../src/class/SyllabusTab'
import { RobotClassTutor, RobotStateBuilding, RobotStateError } from '../../../src/components/robots'
import { SkeletonCards } from '../../../src/components/Skeleton'
import { StatusPill } from '../../../src/components/StatusPill'
import { Tutor } from '../../../src/components/Tutor'
import { Button, Card, ErrorNote, radius, space, T } from '../../../src/components/ui'
import { useTheme, useThemeControl } from '../../../src/theme/ThemeProvider'
import { friendly } from '../../../src/util/errors'

type Tab = 'chat' | 'materials' | 'deadlines' | 'blackboard' | 'books' | 'memory' | 'syllabus'
const TABS: { key: Tab; label: string }[] = [
  { key: 'chat', label: 'Chat' },
  { key: 'materials', label: 'Materials' },
  { key: 'deadlines', label: 'Deadlines' },
  { key: 'blackboard', label: 'Blackboard' },
  { key: 'books', label: 'Books' },
  { key: 'memory', label: 'Memory' },
  { key: 'syllabus', label: 'Syllabus' },
]

function TabBar({ value, onChange }: { value: Tab; onChange: (t: Tab) => void }) {
  const t = useTheme()
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} accessibilityRole="tablist" style={{ flexGrow: 0 }} contentContainerStyle={{ paddingHorizontal: space.lg, gap: space.xs, paddingVertical: space.xs }}>
      {TABS.map((x) => {
        const on = x.key === value
        return (
          <Pressable
            key={x.key} accessibilityRole="tab" accessibilityState={{ selected: on }} onPress={() => onChange(x.key)}
            style={{ minHeight: 44, paddingHorizontal: space.md, justifyContent: 'center', borderRadius: radius.control, backgroundColor: on ? t.accent : t.accentTint }}
          >
            <T kind="footnote" color={on ? t.accentInk : t.accentStrong} style={{ fontWeight: '600' }}>{x.label}</T>
          </Pressable>
        )
      })}
    </ScrollView>
  )
}

export default function ClassHub() {
  const t = useTheme()
  const router = useRouter()
  const insets = useSafeAreaInsets()
  const headerHeight = Platform.OS === 'ios' ? insets.top + 44 : 0 // standard (non-large) native header
  const { setClassColor } = useThemeControl()
  const { api } = useAuth()
  const { id } = useLocalSearchParams<{ id: string }>()
  const [course, setCourse] = useState<Course | null>(null)
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('chat')
  const [refreshing, setRefreshing] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await api.getCourse(id)
      setCourse(r.course); setAssignments(r.assignments); setError(null)
      return r.course
    } catch (e) { setError(friendly(e, 'Could not load this class.')); return null }
  }, [api, id])
  const reload = useCallback(() => { void load() }, [load])

  // Re-theme the app to the class colour while focused; restore the campus colour on leave.
  useEffect(() => { if (course?.color) setClassColor(course.color) }, [course?.color, setClassColor])
  useFocusEffect(useCallback(() => {
    let alive = true
    const tick = async () => {
      const c = await load()
      if (alive && c?.status === 'BUILDING') timer.current = setTimeout(tick, 2000)
    }
    void tick()
    return () => { alive = false; if (timer.current) clearTimeout(timer.current); setClassColor(null) }
  }, [load, setClassColor]))

  async function toggle(a: Assignment) {
    const done = !a.done
    setAssignments((l) => l.map((x) => (x.id === a.id ? { ...x, done } : x)))
    void Haptics.notificationAsync(done ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning)
    try { await api.patchAssignment(a.id, { done }) } catch (e) {
      setAssignments((l) => l.map((x) => (x.id === a.id ? { ...x, done: a.done } : x)))
      setError(friendly(e, "Couldn't save that. Try again."))
    }
  }

  const title = course ? course.courseCode || course.title || 'Class' : 'Class'
  const Robot = course?.status === 'BUILDING' ? RobotStateBuilding : course?.status === 'ERROR' ? RobotStateError : RobotClassTutor
  const ready = course?.status === 'READY'

  const header = course ? (
    <View style={{ flexDirection: 'row', gap: space.md, alignItems: 'center', paddingHorizontal: space.lg, paddingTop: space.sm }}>
      <Robot color={t.accent} size={48} />
      <View style={{ flex: 1, gap: 2 }}>
        {course.courseCode && course.title ? <T kind="footnote" color={t.muted} numberOfLines={1}>{course.title}</T> : null}
        <StatusPill status={course.status === 'READY' ? 'ready' : course.status === 'ERROR' ? 'error' : 'building'} />
      </View>
    </View>
  ) : null

  const scrollTab = (content: React.ReactNode) => (
    <ScrollView
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ padding: space.lg, gap: space.lg, flexGrow: 1 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false) }} tintColor={t.accentStrong} colors={[t.accent]} />}
    >
      {error ? <ErrorNote message={error} /> : null}
      {content}
    </ScrollView>
  )

  let body: React.ReactNode
  if (error && !course) {
    body = scrollTab(<Button title="Try again" onPress={reload} />)
  } else if (!course) {
    body = scrollTab(<SkeletonCards count={2} />)
  } else if (course.status === 'BUILDING') {
    body = scrollTab(
      <Card style={{ gap: space.sm }}>
        {course.pipeline.map((s) => (
          <View key={s.key} accessible accessibilityLabel={`${s.label}, ${s.state === 'done' ? 'done' : s.state === 'running' ? 'in progress' : s.state === 'error' ? 'failed' : 'waiting'}`} style={{ flexDirection: 'row', gap: space.sm, alignItems: 'center' }}>
            <Ionicons name={s.state === 'done' ? 'checkmark-circle' : s.state === 'error' ? 'alert-circle' : s.state === 'running' ? 'sync-circle' : 'ellipse-outline'} size={20} color={s.state === 'error' ? t.danger : s.state === 'pending' ? t.muted : t.accentStrong} />
            <T kind="body" color={s.state === 'pending' ? t.muted : t.ink}>{s.label}</T>
          </View>
        ))}
      </Card>,
    )
  } else if (course.status === 'ERROR') {
    body = scrollTab(
      <>
        <ErrorNote message={course.error ?? 'Something went wrong building this class.'} />
        <Button title="Paste the syllabus text instead" variant="secondary" onPress={() => router.push('/study/add')} />
      </>,
    )
  } else if (tab === 'chat') {
    body = <Tutor key={course.id} course={course} onChanged={reload} keyboardOffset={headerHeight} />
  } else {
    body = scrollTab(
      tab === 'materials' ? <MaterialsTab course={course} onChanged={reload} />
      : tab === 'deadlines' ? <DeadlinesTab items={assignments} color={course.color} onToggle={toggle} />
      : tab === 'blackboard' ? <BlackboardTab course={course} onChanged={reload} />
      : tab === 'books' ? <BooksTab course={course} />
      : tab === 'memory' ? <MemoryTab course={course} />
      : <SyllabusTab c={course} />,
    )
  }

  return (
    <>
      <Stack.Screen options={{ title }} />
      <View style={{ flex: 1, backgroundColor: t.bg }}>
        {header}
        {ready ? <TabBar value={tab} onChange={setTab} /> : null}
        {body}
      </View>
    </>
  )
}
