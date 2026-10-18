import { useCallback, useEffect, useRef, useState } from 'react'
import { Pressable, RefreshControl, View } from 'react-native'
import { useFocusEffect, useRouter } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { ApiError } from 'shared/api'
import type { Course } from 'shared/types'
import { useAuth } from '../../../src/auth/AuthContext'
import { RobotChiefOfStaff, RobotClassTutor, RobotStateBuilding, RobotStateError } from '../../../src/components/robots'
import { SkeletonCards } from '../../../src/components/Skeleton'
import { AgentStatus, StatusPill } from '../../../src/components/StatusPill'
import { TabScreen } from '../../../src/components/TabScreen'
import { Button, Card, EmptyState, ErrorNote, space, T } from '../../../src/components/ui'
import { ago } from '../../../src/util/time'
import { ClassTheme, useTheme } from '../../../src/theme/ThemeProvider'

const STATUS_OF: Record<Course['status'], AgentStatus> = { READY: 'ready', BUILDING: 'building', ERROR: 'error' }

function Stat({ icon, n, label }: { icon: keyof typeof Ionicons.glyphMap; n: number; label: string }) {
  const t = useTheme()
  return (
    <View accessible accessibilityLabel={`${n} ${label}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: t.accentTint }}>
      <Ionicons name={icon} size={13} color={t.accentStrong} />
      <T kind="caption" style={{ fontWeight: '600' }}>{n} {label}</T>
    </View>
  )
}

function ClassCardBody({ c }: { c: Course }) {
  const t = useTheme()
  const step = c.pipeline?.find((s) => s.state === 'running') ?? c.pipeline?.find((s) => s.state === 'pending')
  const done = c.pipeline?.filter((s) => s.state === 'done').length ?? 0
  const Robot = c.status === 'BUILDING' ? RobotStateBuilding : c.status === 'ERROR' ? RobotStateError : RobotClassTutor
  const title = c.courseCode || c.title || 'New class'
  const checked = ago(c.knows?.lastFeedCheckAt)
  return (
    <Card style={{ flexDirection: 'row', gap: space.md, alignItems: 'center', borderTopColor: t.accent, borderTopWidth: 4 }}>
      <Robot color={t.accent} size={56} />
      <View style={{ flex: 1, gap: space.xs }}>
        <T kind="callout">{title}</T>
        {c.title && c.courseCode ? <T kind="footnote" color={t.muted} numberOfLines={1}>{c.title}</T> : null}
        {c.status === 'BUILDING' ? (
          <T kind="footnote" color={t.muted}>{step?.label ?? 'Starting'} ({done} of {c.pipeline?.length ?? 5})</T>
        ) : c.status === 'ERROR' ? (
          <T kind="footnote" color={t.danger}>{c.error ?? 'Something went wrong building this class.'}</T>
        ) : (
          <>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.xs }}>
              <Stat icon="checkmark-done" n={c.knows?.assignmentsCount ?? 0} label="deadlines" />
              <Stat icon="document-text" n={c.knows?.materialsCount ?? 0} label="materials" />
              {(c.knows?.newItemsCount ?? 0) > 0 ? <Stat icon="notifications" n={c.knows.newItemsCount} label="new" /> : null}
            </View>
            <T kind="caption" color={t.muted}>{checked ? `Checked Blackboard ${checked}` : 'Blackboard not checked yet'}</T>
          </>
        )}
        <StatusPill status={STATUS_OF[c.status]} detail={c.status === 'BUILDING' ? `step ${done + 1} of ${c.pipeline?.length ?? 5}` : undefined} />
      </View>
      <Ionicons name="chevron-forward" size={18} color={t.muted} />
    </Card>
  )
}

export default function Study() {
  const t = useTheme()
  const router = useRouter()
  const { api } = useAuth()
  const [courses, setCourses] = useState<Course[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    try {
      const list = await api.getCourses()
      setCourses(list); setFailed(false)
      return list
    } catch (e) {
      // 4xx from the gateway (route missing): empty state. Network or 5xx: show a retry.
      if (e instanceof ApiError && e.status !== 0 && e.status < 500) { setCourses([]); setFailed(false) } else setFailed(true)
      return null
    }
  }, [api])

  // Load on focus; poll every 2s while any class is BUILDING.
  useFocusEffect(useCallback(() => {
    let alive = true
    const tick = async () => {
      const list = await load()
      if (alive && list?.some((c) => c.status === 'BUILDING')) timer.current = setTimeout(tick, 2000)
    }
    void tick()
    return () => { alive = false; if (timer.current) clearTimeout(timer.current) }
  }, [load]))
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false) }
  const addSyllabus = () => router.push('/study/add')

  return (
    <TabScreen refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={t.accentStrong} colors={[t.accent]} />}>
      <Pressable
        accessibilityRole="button" accessibilityLabel="Chief of Staff. Ask about your week or any class. Opens Today."
        onPress={() => router.navigate('/today')} style={({ pressed }) => ({ opacity: pressed ? 0.75 : 1 })}
      >
        <Card style={{ flexDirection: 'row', gap: space.md, alignItems: 'center', backgroundColor: t.accentTint }}>
          <RobotChiefOfStaff color={t.accent} size={48} />
          <View style={{ flex: 1 }}>
            <T kind="callout">Chief of Staff</T>
            <T kind="footnote" color={t.muted}>Ask about your week or any class. Mention a class and I'll bring in its agent.</T>
          </View>
          <Ionicons name="chevron-forward" size={18} color={t.muted} />
        </Card>
      </Pressable>

      <T kind="label" color={t.muted}>Your class agents</T>
      {failed && !courses ? (
        <>
          <ErrorNote message="Can't load your classes right now. Check your connection." />
          <Button title="Try again" onPress={onRefresh} />
        </>
      ) : !courses ? (
        <SkeletonCards count={2} />
      ) : courses.length > 0 ? (
        <>
          {courses.map((c) => (
            <ClassTheme key={c.id} hex={c.color}>
              <Pressable
                accessibilityRole="button" accessibilityLabel={`Open ${c.courseCode || c.title || 'class'} agent`}
                onPress={() => router.push({ pathname: '/study/[id]', params: { id: c.id } })}
                style={({ pressed }) => ({ opacity: pressed ? 0.75 : 1 })}
              >
                <ClassCardBody c={c} />
              </Pressable>
            </ClassTheme>
          ))}
          <Button title="Add a syllabus" variant="secondary" onPress={addSyllabus} />
        </>
      ) : (
        <Card>
          <EmptyState
            icon="school-outline"
            title="No class agents yet"
            body="Add a syllabus and you get a dedicated agent for that class: it knows your deadlines, materials and Blackboard."
            actionLabel="Add a syllabus"
            onAction={addSyllabus}
          />
        </Card>
      )}
    </TabScreen>
  )
}
