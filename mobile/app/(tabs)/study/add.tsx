import { useState } from 'react'
import { KeyboardAvoidingView, Platform, ScrollView, TextInput } from 'react-native'
import * as DocumentPicker from 'expo-document-picker'
import * as Haptics from 'expo-haptics'
import { useRouter } from 'expo-router'
import { ApiError } from 'shared/api'
import { useAuth } from '../../../src/auth/AuthContext'
import { Button, ErrorNote, radius, space, T } from '../../../src/components/ui'
import { useTheme } from '../../../src/theme/ThemeProvider'
import { MAX_PDF_BYTES, uploadPdf } from '../../../src/upload'

const MIN = 50
const MAX = 60000

export default function AddSyllabus() {
  const t = useTheme()
  const router = useRouter()
  const { api } = useAuth()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function fail(e: unknown) {
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
    if (e instanceof ApiError && e.code === 'daily_cap') setError('You have added the maximum number of classes for today. Try again tomorrow.')
    else setError(e instanceof Error ? e.message : 'Something went wrong.')
  }

  async function pickPdf() {
    setError(null)
    let picked: DocumentPicker.DocumentPickerResult
    try {
      picked = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true, multiple: false })
    } catch { setError("Couldn't open your files. Try pasting the text instead."); return }
    if (picked.canceled || !picked.assets?.[0]) return
    const f = picked.assets[0]
    if (!f.name.toLowerCase().endsWith('.pdf') || (f.mimeType && f.mimeType !== 'application/pdf')) {
      setError('Choose a PDF file, or paste the text instead.'); return
    }
    if (f.size != null && f.size > MAX_PDF_BYTES) { setError('That PDF is over 10 MB. Try a smaller file or paste the text.'); return }
    setBusy(true)
    try {
      const { course, upload } = await api.createCourseForUpload(f.name)
      await uploadPdf(upload, { uri: f.uri, name: f.name })
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      router.replace({ pathname: '/study/[id]', params: { id: course.id } })
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  async function submit() {
    const body = text.trim()
    if (body.length < MIN) { setError(`Paste more of the syllabus (at least ${MIN} characters).`); return }
    setBusy(true); setError(null)
    try {
      const { course } = await api.createCourseFromText(body)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      router.replace({ pathname: '/study/[id]', params: { id: course.id } })
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: t.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: space.lg, gap: space.lg }}>
        <T kind="body" color={t.muted}>
          Add your syllabus as a PDF, or paste its text. Your class agent reads it, finds the dates and books, and builds your calendar.
        </T>
        <Button title="Choose a PDF" onPress={pickPdf} loading={busy} />
        <T kind="label" color={t.muted}>Or paste the text</T>
        <TextInput
          accessibilityLabel="Syllabus text"
          multiline
          value={text}
          onChangeText={setText}
          maxLength={MAX}
          placeholder="Paste syllabus text here"
          placeholderTextColor={t.muted}
          selectionColor={t.accent}
          textAlignVertical="top"
          style={{
            minHeight: 260, color: t.ink, backgroundColor: t.surface, borderColor: t.border,
            borderWidth: 1, borderRadius: radius.control, padding: space.md, fontSize: 16,
          }}
        />
        <T kind="caption" color={t.muted}>{text.length.toLocaleString()} / {MAX.toLocaleString()}</T>
        {error ? <ErrorNote message={error} /> : null}
        <Button title="Build from pasted text" variant="secondary" onPress={submit} loading={busy} />
      </ScrollView>
    </KeyboardAvoidingView>
  )
}
