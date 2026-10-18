import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Pressable, View } from 'react-native'
import * as DocumentPicker from 'expo-document-picker'
import * as Haptics from 'expo-haptics'
import { Ionicons } from '@expo/vector-icons'
import type { Course, Material } from 'shared/types'
import { ApiError } from 'shared/api'
import { useAuth } from '../auth/AuthContext'
import { SkeletonCards } from '../components/Skeleton'
import { Button, Card, ErrorNote, space, T } from '../components/ui'
import { useTheme } from '../theme/ThemeProvider'
import { friendly, notAvailable } from '../util/errors'
import { uploadFile } from '../upload'
import { ComingSoon } from './NotAvailable'

const DEFAULT_NOTICE = 'Upload only your own course materials: your notes, and slides or readings your instructor gave you for this class. Do not upload books or other copyrighted material you do not have the right to copy. Files stay private to you and this class.'

/** Class materials (MATERIALS_API.md): PDF or text upload, status, summary, delete. Text is plain. */
export function MaterialsTab({ course, onChanged }: { course: Course; onChanged: () => void }) {
  const t = useTheme()
  const { api } = useAuth()
  const code = course.courseCode || course.title
  const [items, setItems] = useState<Material[] | null>(null)
  const [notice, setNotice] = useState(DEFAULT_NOTICE)
  const [state, setState] = useState<'loading' | 'ok' | 'na' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await api.getMaterials(course.id)
      setItems(r.materials); if (r.notice) setNotice(r.notice); setState('ok'); setError(null)
      if (r.materials.some((m) => m.status === 'processing')) timer.current = setTimeout(load, 3000)
      else onChanged()
    } catch (e) { setState(notAvailable(e) ? 'na' : 'error'); setError(friendly(e)) }
  }, [api, course.id, onChanged])
  useEffect(() => { void load(); return () => { if (timer.current) clearTimeout(timer.current) } }, [load])

  async function add() {
    setError(null)
    let picked: DocumentPicker.DocumentPickerResult
    try { picked = await DocumentPicker.getDocumentAsync({ type: ['application/pdf', 'text/plain'], copyToCacheDirectory: true }) }
    catch { setError("Couldn't open your files."); return }
    if (picked.canceled || !picked.assets?.[0]) return
    const f = picked.assets[0]
    const isPdf = f.name.toLowerCase().endsWith('.pdf')
    const isTxt = /\.(txt|md)$/i.test(f.name)
    if (!isPdf && !isTxt) { setError('Choose a PDF or a text file.'); return }
    if (f.size != null && f.size > (isPdf ? 10 * 1024 * 1024 : 500 * 1024)) { setError(isPdf ? 'That PDF is over 10 MB.' : 'That text file is over 500 KB.'); return }
    const type = isPdf ? 'application/pdf' : 'text/plain'
    setBusy(true)
    try {
      const { upload } = await api.createMaterialUpload(course.id, f.name, type)
      await uploadFile(upload, { uri: f.uri, name: f.name, type })
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      await load()
    } catch (e) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
      setError(e instanceof ApiError ? friendly(e) : e instanceof Error ? e.message : 'Upload failed.')
    } finally { setBusy(false) }
  }
  function remove(m: Material) {
    Alert.alert('Delete this file?', `${m.title}. Your agent will stop using it.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => { try { await api.deleteMaterial(course.id, m.id); await load() } catch (e) { setError(friendly(e)) } } },
    ])
  }

  if (state === 'loading') return <SkeletonCards count={2} />
  if (state === 'na') {
    return <ComingSoon icon="document-text-outline" title="Materials are coming soon" body={`You will be able to add slides, readings and notes, and your ${code} agent will answer from them and tell you which file it used.`} />
  }
  return (
    <View style={{ gap: space.md }}>
      <T kind="caption" color={t.muted}>{notice}</T>
      <Button title="Add a PDF or text file" variant="secondary" onPress={add} loading={busy} />
      {error ? <ErrorNote message={error} /> : null}
      {items && items.length === 0 ? <T kind="body" color={t.muted}>No materials yet. Add your lecture slides or notes and your agent can use them.</T> : null}
      {items?.map((m) => (
        <Card key={m.id} style={{ gap: space.xs }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
            <T kind="callout" style={{ flex: 1 }}>{m.title}</T>
            <Pressable accessibilityRole="button" accessibilityLabel={`Delete ${m.title}`} onPress={() => remove(m)} style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="trash-outline" size={20} color={t.danger} />
            </Pressable>
          </View>
          <T kind="footnote" color={m.status === 'error' ? t.danger : m.status === 'processing' ? t.accentStrong : t.success} style={{ fontWeight: '600' }}>
            {m.status === 'processing' ? 'Reading this file...' : m.status === 'error' ? m.error || 'Could not read this file' : `Ready${m.pages ? `, ${m.pages} pages` : ''}`}
          </T>
          {m.summary ? <T kind="footnote" color={t.muted} numberOfLines={4}>{m.summary}</T> : null}
        </Card>
      ))}
    </View>
  )
}
