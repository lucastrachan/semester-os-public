import { useCallback, useEffect, useRef, useState } from 'react'
import { AccessibilityInfo, ActivityIndicator, Pressable, View } from 'react-native'
import BottomSheet, { BottomSheetScrollView, BottomSheetTextInput } from '@gorhom/bottom-sheet'
import * as Haptics from 'expo-haptics'
import { useRouter } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import type { ChatMessage, ClarifyOption, Course, MasterChatResponse } from 'shared/types'
import { useAuth } from '../auth/AuthContext'
import { chat, masterError } from '../master/client'
import { plain, undoAction } from '../tutor/client'
import { ClassTheme, useTheme, useThemeControl } from '../theme/ThemeProvider'
import { Chips } from './Tutor'
import { RobotClassTutor } from './robots'
import { Button, ErrorNote, radius, space, T } from './ui'

type Msg = ChatMessage & { from?: string; clarify?: ClarifyOption[] }
interface Active { course: Course; reason: string; materials: string[] }
let seq = 0
const mid = () => `s${Date.now()}-${seq++}`
const SNAPS = [112, '55%', '92%'] // fixed peek in points so it never clips with large text

/** Chief of Staff chat in a bottom sheet (peek, half, full). Hands off to a class tutor and re-themes to its colour. */
function HandoffBanner({ banner, themed, onUndo, onOpen, onBack }: { banner: Active; themed: boolean; onUndo: () => void; onOpen: () => void; onBack: () => void }) {
  const t = useTheme()
  const code = banner.course.courseCode || banner.course.title
  const link = { minHeight: 44, justifyContent: 'center' as const, paddingRight: space.md }
  return (
    <View accessibilityLiveRegion="polite" style={{ marginHorizontal: space.lg, marginBottom: space.sm, padding: space.md, borderRadius: radius.control, backgroundColor: t.accentTint, borderLeftWidth: 4, borderLeftColor: t.accent, gap: space.xs }}>
      <View style={{ flexDirection: 'row', gap: space.md, alignItems: 'center' }}>
        <RobotClassTutor color={t.accent} size={40} />
        <View style={{ flex: 1 }}>
          <T kind="footnote" style={{ fontWeight: '700' }}>Switching you to your {code} agent</T>
          <T kind="caption" color={t.muted}>{banner.reason}</T>
        </View>
      </View>
      {banner.materials.length ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.xs }}>
          {banner.materials.map((m) => (
            <View key={m} style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: t.surface }}>
              <T kind="caption">Using: {m}</T>
            </View>
          ))}
        </View>
      ) : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        <Pressable accessibilityRole="button" onPress={onUndo} style={link}><T kind="footnote" color={t.accentStrong} style={{ fontWeight: '700' }}>Undo</T></Pressable>
        {themed ? (
          <>
            <Pressable accessibilityRole="button" onPress={onOpen} style={link}><T kind="footnote" color={t.accentStrong} style={{ fontWeight: '700' }}>Open {code} agent</T></Pressable>
            <Pressable accessibilityRole="button" onPress={onBack} style={link}><T kind="footnote" color={t.accentStrong} style={{ fontWeight: '700' }}>Back to Chief of Staff</T></Pressable>
          </>
        ) : null}
      </View>
    </View>
  )
}

export function MasterSheet({ courses, onChanged }: { courses: Course[]; onChanged: () => void }) {
  const t = useTheme()
  const { api } = useAuth()
  const router = useRouter()
  const { setClassColor } = useThemeControl()
  const sheet = useRef<BottomSheet>(null)
  const scroll = useRef<React.ComponentRef<typeof BottomSheetScrollView>>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const history = useRef<Msg[]>([]) // conversation up to and including the last user message
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cool, setCool] = useState(0)
  const [undone, setUndone] = useState<Set<string>>(new Set())
  const [pending, setPending] = useState<Active | null>(null) // handoff banner showing, theme not applied yet
  const [active, setActive] = useState<Active | null>(null) // themed into this class
  const ready = courses.filter((c) => c.status === 'READY')

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); setClassColor(null) }, [setClassColor])
  // Chief of Staff history from the server (HISTORY_API.md); silently skipped when the route is not available yet.
  useEffect(() => {
    let alive = true
    api.getMasterHistory().then((h) => {
      if (!alive || !h.messages.length) return
      const loaded: Msg[] = h.messages.map((m) => ({ id: m.id, role: m.role, content: m.content, actions: m.actions, from: m.role === 'assistant' ? 'Chief of Staff' : undefined }))
      setMsgs((cur) => (cur.length ? cur : loaded))
    }).catch(() => {})
    return () => { alive = false }
  }, [api])
  useEffect(() => { scroll.current?.scrollToEnd({ animated: true }) }, [msgs.length, busy])

  const enterClass = useCallback((a: Active) => {
    setPending(a)
    AccessibilityInfo.announceForAccessibility(`Switching you to your ${a.course.courseCode || a.course.title} agent. ${a.reason}`)
    timer.current = setTimeout(() => {
      setPending(null); setActive(a); setClassColor(a.course.color)
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
    }, 1200)
  }, [setClassColor])

  const leaveClass = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    setPending(null); setActive(null); setClassColor(null)
  }, [setClassColor])

  async function call(hist: Msg[], target?: string) {
    setBusy(true); setError(null)
    history.current = hist
    try {
      const res: MasterChatResponse = await chat(
        api,
        { messages: hist.slice(-20).map((m) => ({ role: m.role, content: m.content })), ...(target ? { target } : {}) },
        ready.map((c) => c.id),
      )
      const course = res.courseId ? ready.find((c) => c.id === res.courseId) : undefined
      const reply: Msg = {
        id: mid(), role: 'assistant', content: res.reply, actions: res.actions,
        from: res.agent === 'class' ? course?.courseCode || res.handoff?.courseCode || 'Tutor' : 'Chief of Staff',
        clarify: res.clarify?.options,
      }
      setMsgs([...hist, reply])
      if (res.actions.length) onChanged()
      if (res.agent === 'class' && course) {
        if (!active || active.course.id !== course.id) enterClass({ course, reason: res.handoff?.reason ?? `This looks like a question about ${course.courseCode || course.title}`, materials: (res.handoff?.materials ?? []).map((m) => m.title) })
      } else if (target === 'master') leaveClass()
    } catch (e) {
      setError(masterError(e))
      if ((e as { code?: string })?.code === 'rate_limited') setCool(Date.now() + 15000)
    } finally { setBusy(false) }
  }

  async function send(text: string) {
    const body = text.trim()
    if (!body || busy || Date.now() < cool) return
    const hist = [...msgs, { id: mid(), role: 'user' as const, content: body }]
    setMsgs(hist); setInput('')
    await call(hist, active?.course.id) // inside a class, stay with that tutor until "Back"
  }

  // Undo is client-side: show the master chat again and re-send the same message with target "master".
  async function undoHandoff() {
    leaveClass()
    const hist = history.current
    setMsgs(hist)
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
    await call(hist, 'master')
  }

  async function undoChip(courseId: string | null, id: string) {
    try { await undoAction(api, courseId ?? active?.course.id ?? '', id); setUndone((s) => new Set(s).add(id)); onChanged() }
    catch (e) { setError(masterError(e)) }
  }

  const banner = pending ?? active
  return (
    <BottomSheet
      ref={sheet} index={0} snapPoints={SNAPS} keyboardBehavior="interactive" keyboardBlurBehavior="restore"
      android_keyboardInputMode="adjustResize"
      backgroundStyle={{ backgroundColor: t.surface }} handleIndicatorStyle={{ backgroundColor: t.borderStrong }}
    >
      <Pressable
        accessibilityRole="button" accessibilityLabel="Chief of Staff chat. Double tap to open." onPress={() => sheet.current?.snapToIndex(1)}
        style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingHorizontal: space.lg, paddingBottom: space.sm, minHeight: 44 }}
      >
        <Ionicons name="chatbubble-ellipses" size={20} color={t.accentStrong} />
        <T kind="callout" style={{ flex: 1 }}>{active ? `${active.course.courseCode || active.course.title} agent` : 'Ask your chief of staff'}</T>
        <Ionicons name="chevron-up" size={18} color={t.muted} />
      </Pressable>

      {banner ? (
        <ClassTheme hex={banner.course.color}>
          <HandoffBanner
            banner={banner} themed={!!active}
            onUndo={undoHandoff}
            onOpen={() => router.push({ pathname: '/study/[id]', params: { id: banner.course.id } })}
            onBack={leaveClass}
          />
        </ClassTheme>
      ) : null}

      <View style={{ flex: 1 }}>
        <BottomSheetScrollView ref={scroll} contentContainerStyle={{ padding: space.lg, gap: space.sm }} keyboardShouldPersistTaps="handled">
          {msgs.length === 0 ? (
            <T kind="body" color={t.muted}>Ask about your week, your deadlines, or any class. I will bring in the right tutor when it helps. Nothing changes in your calendar from here.</T>
          ) : msgs.map((m) => (
            <View key={m.id} style={{ gap: space.xs, alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
              {m.role === 'assistant' && m.from ? <T kind="caption" color={t.muted}>{m.from}</T> : null}
              <View style={{ maxWidth: '88%', padding: space.md, borderRadius: radius.card, backgroundColor: m.role === 'user' ? t.accent : t.bg, borderWidth: m.role === 'user' ? 0 : 1, borderColor: t.border }}>
                <T kind="body" color={m.role === 'user' ? t.accentInk : t.ink}>{m.role === 'user' ? m.content : plain(m.content)}</T>
              </View>
              {m.actions?.length ? <Chips actions={m.actions} onUndo={(a) => undoChip(a.courseId ?? null, a.id)} undone={undone} /> : null}
              {m.clarify && m === msgs[msgs.length - 1] && !busy ? (
                <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
                  {m.clarify.map((o) => (
                    <Button key={o.target} title={o.label} variant="secondary" onPress={() => void call(history.current, o.target)} />
                  ))}
                </View>
              ) : null}
            </View>
          ))}
          {busy ? (
            <View accessibilityLabel="Typing" style={{ flexDirection: 'row', gap: space.sm, alignItems: 'center' }}>
              <ActivityIndicator color={t.accentStrong} /><T kind="footnote" color={t.muted}>Thinking, this can take a few seconds</T>
            </View>
          ) : null}
          {error ? <ErrorNote message={error} /> : null}
        </BottomSheetScrollView>
        <View style={{ flexDirection: 'row', gap: space.sm, alignItems: 'flex-end', padding: space.md, borderTopWidth: 1, borderTopColor: t.border }}>
          <BottomSheetTextInput
            accessibilityLabel="Message your chief of staff" value={input} onChangeText={setInput} multiline maxLength={4000}
            placeholder="Ask anything" placeholderTextColor={t.muted} selectionColor={t.accent}
            style={{ flex: 1, minHeight: 48, maxHeight: 110, color: t.ink, backgroundColor: t.bg, borderColor: t.border, borderWidth: 1, borderRadius: radius.control, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 16 }}
          />
          <Pressable accessibilityRole="button" accessibilityLabel="Send" disabled={busy || !input.trim()} onPress={() => send(input)}
            style={{ width: 48, height: 48, borderRadius: radius.control, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center', opacity: busy || !input.trim() ? 0.5 : 1 }}>
            <Ionicons name="arrow-up" size={22} color={t.accentInk} />
          </Pressable>
        </View>
      </View>
    </BottomSheet>
  )
}
