import { useCallback, useState } from 'react'
import { Pressable, RefreshControl, View } from 'react-native'
import { useFocusEffect, useRouter } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import type { BriefingResponse, Course } from 'shared/types'
import { useAuth } from '../../../src/auth/AuthContext'
import { BriefingCard } from '../../../src/components/BriefingCard'
import { MasterSheet } from '../../../src/components/MasterSheet'
import { SkeletonBlock, SkeletonCards } from '../../../src/components/Skeleton'
import { TabScreen } from '../../../src/components/TabScreen'
import { Button, Card, EmptyState, ErrorNote, space, T } from '../../../src/components/ui'
import { getBriefing, masterError, regenerate } from '../../../src/master/client'
import { useTheme } from '../../../src/theme/ThemeProvider'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

export default function Today() {
  const t = useTheme()
  const router = useRouter()
  const { me, noCampus, meError, reloadMe, email, signOut, api } = useAuth()
  const [refreshing, setRefreshing] = useState(false)
  const [courses, setCourses] = useState<Course[]>([])
  const [brief, setBrief] = useState<BriefingResponse | null>(null)
  const [briefLoaded, setBriefLoaded] = useState(false)
  const [briefError, setBriefError] = useState<string | null>(null)
  const [regen, setRegen] = useState(false)
  const name = me?.profile.displayName || email?.split('@')[0] || ''

  const loadBrief = useCallback(async () => {
    let list: Course[] = []
    try { list = await api.getCourses(); setCourses(list) } catch { /* /courses may be unavailable */ }
    try {
      setBrief(await getBriefing(api, list[0]?.id ?? ''))
      setBriefError(null)
    } catch (e) {
      setBrief(null)
      // 404/403 means the briefing route is not deployed yet: show the quiet empty state, not an error.
      const status = (e as { status?: number })?.status
      setBriefError(status === 404 || status === 403 ? null : masterError(e))
    } finally { setBriefLoaded(true) }
  }, [api])
  useFocusEffect(useCallback(() => { void loadBrief() }, [loadBrief]))

  const onRefresh = async () => { setRefreshing(true); await Promise.all([reloadMe(), loadBrief()]); setRefreshing(false) }
  const onRegen = async () => {
    setRegen(true); setBriefError(null)
    try { setBrief(await regenerate(api, courses[0]?.id ?? '')) } catch (e) { setBriefError(masterError(e)) } finally { setRegen(false) }
  }

  return (
    <View style={{ flex: 1, backgroundColor: t.bg }}>
      <TabScreen
        bottomInset={130}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={t.accentStrong} colors={[t.accent]} />}
      >
        {noCampus ? (
          <>
            <ErrorNote message="Semester OS supports US colleges (.edu email addresses) for now. Sign in with your school email." />
            <Button title="Sign out" variant="secondary" onPress={signOut} />
          </>
        ) : meError ? (
          <>
            <ErrorNote message={meError} />
            <Button title="Try again" onPress={onRefresh} />
          </>
        ) : (
          <>
            <View style={{ gap: space.xs }}>
              <T kind="title">{greeting()}{name ? `, ${name}` : ''}</T>
              {me ? <T kind="body" color={t.muted}>{me.tenant.name}</T> : <SkeletonBlock height={16} width="50%" />}
            </View>
            {me ? (
              <Pressable
                accessibilityRole="button" accessibilityLabel={`${me.tenant.name}. See what's set up`}
                onPress={() => router.push('/today/school')} style={({ pressed }) => ({ opacity: pressed ? 0.75 : 1 })}
              >
                <Card style={{ flexDirection: 'row', gap: space.md, alignItems: 'center', backgroundColor: t.accentTint, borderLeftColor: t.accent, borderLeftWidth: 4 }}>
                  <Ionicons name="school" size={22} color={t.accentStrong} />
                  <View style={{ flex: 1 }}>
                    <T kind="callout">{me.tenant.name}</T>
                    <T kind="footnote" color={t.muted}>{"See what's set up for your campus"}</T>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={t.muted} />
                </Card>
              </Pressable>
            ) : null}

            {!briefLoaded ? <SkeletonCards count={2} /> : brief ? (
              <>
                <BriefingCard data={brief} courses={courses} />
                <Button title="Refresh briefing" variant="secondary" onPress={onRegen} loading={regen} />
              </>
            ) : (
              <EmptyState
                icon="sunny-outline"
                title="No briefing yet"
                body="Add a class and your chief of staff will build your day: classes, what's due, and what to do first."
                actionLabel={courses.length ? 'Build my briefing' : 'Add a syllabus'}
                onAction={courses.length ? onRegen : () => router.push('/study/add')}
              />
            )}
            {briefError ? <ErrorNote message={briefError} /> : null}
          </>
        )}
      </TabScreen>
      {!noCampus && !meError ? <MasterSheet courses={courses} onChanged={loadBrief} /> : null}
    </View>
  )
}
