import { useCallback, useEffect, useRef, useState } from 'react'
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import * as Haptics from 'expo-haptics'
import { Ionicons } from '@expo/vector-icons'
import type { ChatMessage, Course, Flashcard, Opening, QuizQuestion, TutorAction, TutorMode } from 'shared/types'
import { useAuth } from '../auth/AuthContext'
import { plain, sendChat, tutorError, undoAction } from '../tutor/client'
import { useTheme } from '../theme/ThemeProvider'
import { FlashDeck } from './FlashDeck'
import { Quiz } from './Quiz'
import { Button, Card, ErrorNote, radius, space, T } from './ui'

const MODES: { key: TutorMode; label: string }[] = [
  { key: 'explain', label: 'Explain' },
  { key: 'quiz', label: 'Quiz' },
  { key: 'flashcards', label: 'Cards' },
  { key: 'cram', label: 'Cram' },
]
let seq = 0
const mid = () => `l${Date.now()}-${seq++}`
const CACHE = (id: string) => `semesteros.chat.${id}`

export function Chips({ actions, onUndo, undone }: { actions: TutorAction[]; onUndo: (a: TutorAction) => void; undone: Set<string> }) {
  const t = useTheme()
  return (
    <View style={{ gap: space.xs }}>
      {actions.map((a) => (
        <View key={a.id} style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingLeft: space.md, borderRadius: 999, backgroundColor: t.accentTint, alignSelf: 'flex-start' }}>
          <Ionicons name="checkmark-circle" size={16} color={t.accentStrong} />
          <T kind="footnote" style={{ flexShrink: 1, textDecorationLine: undone.has(a.id) ? 'line-through' : 'none' }}>{a.summary}</T>
          {a.undoable && !undone.has(a.id) ? (
            <Pressable accessibilityRole="button" accessibilityLabel={`Undo: ${a.summary}`} onPress={() => onUndo(a)} style={{ minHeight: 44, justifyContent: 'center', paddingHorizontal: space.md }}>
              <T kind="footnote" color={t.accentStrong} style={{ fontWeight: '700' }}>Undo</T>
            </Pressable>
          ) : <View style={{ width: space.md }} />}
        </View>
      ))}
    </View>
  )
}

function fallbackOpening(code: string): Opening {
  return {
    message: `Hi, I'm your ${code} agent. I know your syllabus and deadlines. What do you want to work on?`,
    chips: [
      { label: "What's due this week?", prompt: "What's due this week in this class?", mode: 'explain' },
      { label: 'Quiz me', prompt: 'Quiz me on this class', mode: 'quiz' },
      { label: 'Make a study plan', prompt: 'Make me a study plan for my next exam', mode: 'cram' },
    ],
  }
}

/** The class agent's Chat tab: a full-height chat surface (list + pinned composer), history, opening message, chips. */
export function Tutor({ course, onChanged, keyboardOffset }: { course: Course; onChanged: () => void; keyboardOffset: number }) {
  const t = useTheme()
  const { api } = useAuth()
  const code = course.courseCode || course.title || 'class'
  const [mode, setMode] = useState<TutorMode>('explain')
  const [msgs, setMsgs] = useState<ChatMessage[]>([])
  const [opening, setOpening] = useState<Opening>(fallbackOpening(code))
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [coolUntil, setCoolUntil] = useState(0)
  const [undone, setUndone] = useState<Set<string>>(new Set())
  const [quiz, setQuiz] = useState<QuizQuestion[] | null>(null)
  const [cards, setCards] = useState<Flashcard[] | null>(null)
  const list = useRef<FlatList<ChatMessage>>(null)
  const loaded = useRef(false)

  // History: server first (HISTORY_API.md), then the on-device copy. Opening message from the server, else a local greeting.
  useEffect(() => {
    let alive = true
    ;(async () => {
      let initial: ChatMessage[] = []
      try {
        const h = await api.getHistory(course.id)
        initial = h.messages.map((m) => ({ id: m.id, role: m.role, content: m.content, actions: m.actions, sources: m.sources }))
      } catch {
        try { initial = JSON.parse((await AsyncStorage.getItem(CACHE(course.id))) ?? '[]') } catch { initial = [] }
      }
      if (alive) { setMsgs(initial); loaded.current = true }
      try { const o = await api.getOpening(course.id); if (alive && o?.message) setOpening(o) } catch { /* local greeting stays */ }
    })()
    return () => { alive = false }
  }, [api, course.id])

  useEffect(() => {
    if (loaded.current) void AsyncStorage.setItem(CACHE(course.id), JSON.stringify(msgs.slice(-60))).catch(() => {})
    setTimeout(() => list.current?.scrollToEnd({ animated: true }), 50)
  }, [msgs, busy, course.id])

  const call = useCallback(async (m: TutorMode, history: ChatMessage[]) => {
    setBusy(true); setError(null)
    try {
      const res = await sendChat(api, course.id, { mode: m, messages: history.slice(-20).map((x) => ({ role: x.role, content: x.content })) })
      if (m === 'quiz' && res.quiz) setQuiz(res.quiz.questions)
      else if (m === 'flashcards' && res.flashcards) setCards(res.flashcards.cards)
      setMsgs([...history, { id: mid(), role: 'assistant', content: res.reply, actions: res.actions, sources: res.sources }])
      if (res.actions.length) onChanged()
    } catch (e) {
      setError(tutorError(e))
      if ((e as { code?: string })?.code === 'rate_limited') setCoolUntil(Date.now() + 15000)
    } finally { setBusy(false) }
  }, [api, course.id, onChanged])

  async function send(text: string, as: TutorMode = mode) {
    const body = text.trim()
    if (!body || busy || Date.now() < coolUntil) return
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
    const history = [...msgs, { id: mid(), role: 'user' as const, content: body }]
    setMsgs(history); setInput('')
    await call(as, history)
  }

  function tapChip(c: Opening['chips'][number]) {
    setMode(c.mode); setError(null)
    void send(c.prompt, c.mode)
  }

  async function undo(a: TutorAction) {
    try { await undoAction(api, course.id, a.id); setUndone((s) => new Set(s).add(a.id)); onChanged() }
    catch (e) { setError((e as { code?: string })?.code === 'already_undone' ? 'Already undone.' : tutorError(e)) }
  }

  const lastAssistant = [...msgs].reverse()[0]
  const cramOffer = mode === 'cram' && lastAssistant?.role === 'assistant' && !lastAssistant.actions?.length && msgs.length > 1

  const modeBar = (
    <View accessibilityRole="tablist" style={{ flexDirection: 'row', gap: space.xs, paddingHorizontal: space.lg, paddingVertical: space.sm }}>
      {MODES.map((x) => {
        const on = x.key === mode
        return (
          <Pressable key={x.key} accessibilityRole="tab" accessibilityState={{ selected: on }} onPress={() => { setMode(x.key); setError(null) }}
            style={{ flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radius.control, backgroundColor: on ? t.accent : t.surface, borderWidth: 1, borderColor: on ? t.accent : t.border }}>
            <T kind="footnote" color={on ? t.accentInk : t.ink} style={{ fontWeight: '600' }}>{x.label}</T>
          </Pressable>
        )
      })}
    </View>
  )

  if (mode === 'quiz' || mode === 'flashcards') {
    return (
      <View style={{ flex: 1 }}>
        {modeBar}
        <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.md }} keyboardShouldPersistTaps="handled">
          {mode === 'quiz' ? (
            quiz ? <Quiz questions={quiz} onDone={() => setQuiz(null)} /> : (
              <Card style={{ gap: space.md }}>
                <T kind="body">Quick questions from {code}, one at a time, with explanations.</T>
                <Button title="Start a quiz" onPress={() => call('quiz', [])} loading={busy} />
              </Card>
            )
          ) : cards ? <FlashDeck cards={cards} onDone={() => setCards(null)} /> : (
            <Card style={{ gap: space.md }}>
              <T kind="body">A deck of cards from {code}. Swipe right if you know it, left to review.</T>
              <Button title="Make flashcards" onPress={() => call('flashcards', [])} loading={busy} />
            </Card>
          )}
          {error ? <ErrorNote message={error} /> : null}
        </ScrollView>
      </View>
    )
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={keyboardOffset}>
      {modeBar}
      <FlatList
        ref={list}
        style={{ flex: 1 }}
        data={msgs}
        keyExtractor={(m) => m.id}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingHorizontal: space.lg, paddingVertical: space.sm, gap: space.sm }}
        ListHeaderComponent={(
          <View style={{ gap: space.xs, alignItems: 'flex-start', marginBottom: space.sm }}>
            <T kind="caption" color={t.muted}>{code} agent</T>
            <View style={{ maxWidth: '90%', padding: space.md, borderRadius: radius.card, backgroundColor: t.surface, borderWidth: 1, borderColor: t.border }}>
              <T kind="body">{plain(opening.message)}</T>
            </View>
          </View>
        )}
        renderItem={({ item: m }) => (
          <View style={{ gap: space.xs, alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <View style={{ maxWidth: '88%', padding: space.md, borderRadius: radius.card, backgroundColor: m.role === 'user' ? t.accent : t.surface, borderWidth: m.role === 'user' ? 0 : 1, borderColor: t.border }}>
              <T kind="body" color={m.role === 'user' ? t.accentInk : t.ink}>{m.role === 'user' ? m.content : plain(m.content)}</T>
            </View>
            {m.sources?.length ? <T kind="caption" color={t.muted}>Used: {m.sources.map((s) => s.title).join(', ')}</T> : null}
            {m.actions?.length ? <Chips actions={m.actions} onUndo={undo} undone={undone} /> : null}
          </View>
        )}
        ListFooterComponent={(
          <View style={{ gap: space.sm }}>
            {busy ? (
              <View accessibilityLabel="The agent is typing" style={{ flexDirection: 'row', gap: space.sm, alignItems: 'center' }}>
                <ActivityIndicator color={t.accentStrong} /><T kind="footnote" color={t.muted}>Thinking, this can take a few seconds</T>
              </View>
            ) : null}
            {error ? <ErrorNote message={error} /> : null}
          </View>
        )}
      />
      {cramOffer && !busy ? (
        <View style={{ paddingHorizontal: space.lg, paddingBottom: space.sm }}>
          <Button title="Add these study blocks to my calendar" onPress={() => send('Yes, put those in my calendar.')} />
        </View>
      ) : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" style={{ flexGrow: 0 }} contentContainerStyle={{ paddingHorizontal: space.lg, gap: space.sm, paddingVertical: space.xs }}>
        {opening.chips.map((c) => (
          <Pressable key={c.label} accessibilityRole="button" disabled={busy} onPress={() => tapChip(c)}
            style={{ minHeight: 44, paddingHorizontal: space.md, justifyContent: 'center', borderRadius: 999, backgroundColor: t.accentTint }}>
            <T kind="footnote" color={t.accentStrong} style={{ fontWeight: '600' }}>{c.label}</T>
          </Pressable>
        ))}
      </ScrollView>
      <View style={{ flexDirection: 'row', gap: space.sm, alignItems: 'flex-end', paddingHorizontal: space.lg, paddingVertical: space.sm, borderTopWidth: 1, borderTopColor: t.border, backgroundColor: t.bg }}>
        <TextInput
          accessibilityLabel={`Message your ${code} agent`} value={input} onChangeText={setInput} multiline maxLength={4000}
          placeholder={mode === 'cram' ? 'Reply to the planner' : `Ask your ${code} agent`} placeholderTextColor={t.muted} selectionColor={t.accent}
          style={{ flex: 1, minHeight: 48, maxHeight: 120, color: t.ink, backgroundColor: t.surface, borderColor: t.border, borderWidth: 1, borderRadius: radius.control, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 16 }}
        />
        <Pressable accessibilityRole="button" accessibilityLabel="Send" disabled={busy || !input.trim()} onPress={() => send(input)}
          style={{ width: 48, height: 48, borderRadius: radius.control, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center', opacity: busy || !input.trim() ? 0.5 : 1 }}>
          <Ionicons name="arrow-up" size={22} color={t.accentInk} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  )
}
