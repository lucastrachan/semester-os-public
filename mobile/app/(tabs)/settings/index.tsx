import { useCallback, useState } from 'react'
import { ActionSheetIOS, Alert, Platform, Pressable, View } from 'react-native'
import { useFocusEffect } from 'expo-router'
import * as Haptics from 'expo-haptics'
import { Ionicons } from '@expo/vector-icons'
import type { Course } from 'shared/types'
import Constants from 'expo-constants'
import { useAuth } from '../../../src/auth/AuthContext'
import { FeedCard } from '../../../src/components/FeedCard'
import { TabScreen } from '../../../src/components/TabScreen'
import { Button, Card, space, T } from '../../../src/components/ui'
import { useTheme } from '../../../src/theme/ThemeProvider'

function Row({ label, value }: { label: string; value: string }) {
  const t = useTheme()
  return (
    <View style={{ minHeight: 44, justifyContent: 'center', gap: 2 }}>
      <T kind="caption" color={t.muted}>{label}</T>
      <T kind="body">{value}</T>
    </View>
  )
}

export default function Settings() {
  const t = useTheme()
  const { me, email, signOut, api } = useAuth()
  const [courses, setCourses] = useState<Course[]>([])
  const [deleting, setDeleting] = useState<string | null>(null)
  const loadCourses = useCallback(async () => {
    try { setCourses(await api.getCourses()) } catch { /* /courses may be unavailable: show no classes */ }
  }, [api])
  useFocusEffect(useCallback(() => { void loadCourses() }, [loadCourses]))

  const doDelete = async (c: Course) => {
    setDeleting(c.id)
    try {
      await api.deleteCourse(c.id)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
      setCourses((l) => l.filter((x) => x.id !== c.id))
    } catch (e) {
      Alert.alert("Couldn't delete", e instanceof Error ? e.message : 'Try again.')
    } finally { setDeleting(null) }
  }
  const confirmDelete = (c: Course) => {
    const name = c.courseCode || c.title || 'this class'
    const msg = `Deletes ${name}, its deadlines and the uploaded PDF. This can't be undone.`
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        { title: `Delete ${name}?`, message: msg, options: ['Delete class', 'Cancel'], destructiveButtonIndex: 0, cancelButtonIndex: 1 },
        (i) => { if (i === 0) void doDelete(c) },
      )
    } else {
      Alert.alert(`Delete ${name}?`, msg, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => void doDelete(c) },
      ])
    }
  }
  const tenant = me?.tenant

  return (
    <TabScreen>
      <T kind="label" color={t.muted}>Account</T>
      <Card><Row label="Email" value={email ?? '-'} /></Card>

      <T kind="label" color={t.muted}>Campus</T>
      <Card style={{ gap: space.sm }}>
        <Row label="School" value={tenant?.name ?? '-'} />
        <Row label="Time zone" value={tenant?.timezone ?? '-'} />
        <Row label="Learning system" value={tenant?.lms?.type ?? '-'} />
        <Row label="Email domains" value={tenant?.domains?.join(', ') ?? '-'} />
      </Card>

      <T kind="label" color={t.muted}>Blackboard</T>
      <FeedCard />

      <T kind="label" color={t.muted}>Your classes</T>
      <Card style={{ gap: space.xs }}>
        {courses.length === 0 ? (
          <T kind="body" color={t.muted}>No classes yet.</T>
        ) : courses.map((c) => (
          <View key={c.id} style={{ minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: space.md }}>
            <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: c.color }} />
            <T kind="body" style={{ flex: 1 }} numberOfLines={1}>{c.courseCode || c.title || 'New class'}</T>
            <Pressable
              accessibilityRole="button" accessibilityLabel={`Delete ${c.courseCode || c.title || 'class'}`}
              hitSlop={8} disabled={deleting === c.id} onPress={() => confirmDelete(c)}
              style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center', opacity: deleting === c.id ? 0.4 : 1 }}
            >
              <Ionicons name="trash-outline" size={22} color={t.danger} />
            </Pressable>
          </View>
        ))}
      </Card>

      <T kind="label" color={t.muted}>About</T>
      <Card><Row label="Version" value={Constants.expoConfig?.version ?? '1.0.0'} /></Card>

      <Button
        title="Sign out"
        variant="secondary"
        onPress={() => Alert.alert('Sign out?', 'You can sign back in any time.', [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Sign out', style: 'destructive', onPress: () => void signOut() },
        ])}
      />
    </TabScreen>
  )
}
