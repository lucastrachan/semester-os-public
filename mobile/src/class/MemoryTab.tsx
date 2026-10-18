import { useCallback, useEffect, useState } from 'react'
import { Alert, Modal, Platform, Pressable, SafeAreaView, View } from 'react-native'
import * as Haptics from 'expo-haptics'
import { Ionicons } from '@expo/vector-icons'
import type { Course, MemoryNote } from 'shared/types'
import { useAuth } from '../auth/AuthContext'
import { SkeletonCards } from '../components/Skeleton'
import { Button, Card, ErrorNote, space, T, TextField } from '../components/ui'
import { useTheme } from '../theme/ThemeProvider'
import { friendly, notAvailable } from '../util/errors'
import { ComingSoon } from './NotAvailable'

/** What the class agent remembers about the student (MEMORY_API.md). Visible, editable, deletable. Plain text. */
export function MemoryTab({ course }: { course: Course }) {
  const t = useTheme()
  const { api } = useAuth()
  const code = course.courseCode || course.title
  const [notes, setNotes] = useState<MemoryNote[] | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'na' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [edit, setEdit] = useState<{ note: MemoryNote | null; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try { setNotes((await api.getMemory(course.id)).notes); setState('ok'); setError(null) }
    catch (e) { setState(notAvailable(e) ? 'na' : 'error'); setError(friendly(e)) }
  }, [api, course.id])
  useEffect(() => { void load() }, [load])

  async function save() {
    if (!edit) return
    const text = edit.text.trim()
    if (!text) return
    setBusy(true); setError(null)
    try {
      if (edit.note) await api.editMemory(course.id, edit.note.id, text)
      else await api.addMemory(course.id, text)
      setEdit(null); await load()
    } catch (e) { setError(friendly(e)) } finally { setBusy(false) }
  }
  function remove(n: MemoryNote) {
    Alert.alert('Forget this note?', n.text, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Forget', style: 'destructive',
        onPress: async () => {
          try { await api.deleteMemory(course.id, n.id); void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning); await load() }
          catch (e) { setError(friendly(e)) }
        },
      },
    ])
  }
  function clearAll() {
    Alert.alert('Clear all memory?', `Your ${code} agent will forget everything it noted about you. This cannot be undone.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Clear all', style: 'destructive', onPress: async () => { try { await api.deleteMemory(course.id); await load() } catch (e) { setError(friendly(e)) } } },
    ])
  }

  if (state === 'loading') return <SkeletonCards count={2} />
  if (state === 'na') {
    return <ComingSoon icon="bulb-outline" title="Memory is coming soon" body={`Your ${code} agent will keep short notes about how you learn, and you will be able to see, edit and delete every one.`} />
  }
  return (
    <View style={{ gap: space.md }}>
      <T kind="footnote" color={t.muted}>Short notes your {code} agent keeps about you for this class. You control them: edit or delete any time.</T>
      {error ? <ErrorNote message={error} /> : null}
      {notes && notes.length === 0 ? <Card><T kind="body" color={t.muted}>Nothing remembered yet. As you chat, your agent may note things like your level or how you like to study.</T></Card> : null}
      {notes?.map((n) => (
        <Card key={n.id} style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
          <Pressable accessibilityRole="button" accessibilityLabel={`Edit note: ${n.text}`} onPress={() => setEdit({ note: n, text: n.text })} style={{ flex: 1, minHeight: 44, justifyContent: 'center' }}>
            <T kind="body">{n.text}</T>
            {n.source === 'agent' ? <T kind="caption" color={t.muted}>Noted by your agent</T> : null}
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Delete note" onPress={() => remove(n)} style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="trash-outline" size={20} color={t.danger} />
          </Pressable>
        </Card>
      ))}
      <Button title="Add a note" variant="secondary" onPress={() => setEdit({ note: null, text: '' })} />
      {notes && notes.length > 0 ? <Button title="Clear all memory" variant="plain" onPress={clearAll} /> : null}

      <Modal visible={!!edit} animationType="slide" presentationStyle={Platform.OS === 'ios' ? 'pageSheet' : undefined} onRequestClose={() => setEdit(null)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: t.bg, padding: space.lg, gap: space.lg }}>
          <T kind="title">{edit?.note ? 'Edit note' : 'Add a note'}</T>
          <TextField
            label="Note (up to 280 characters, no links)" value={edit?.text ?? ''} multiline maxLength={280}
            onChangeText={(x) => setEdit((e) => (e ? { ...e, text: x } : e))}
            style={{ minHeight: 100, textAlignVertical: 'top', paddingTop: 12 }}
          />
          {error ? <ErrorNote message={error} /> : null}
          <Button title="Save" onPress={save} loading={busy} />
          <Button title="Cancel" variant="plain" onPress={() => { setEdit(null); setError(null) }} />
        </SafeAreaView>
      </Modal>
    </View>
  )
}
