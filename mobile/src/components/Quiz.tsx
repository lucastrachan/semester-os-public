import { useState } from 'react'
import { Pressable, View } from 'react-native'
import * as Haptics from 'expo-haptics'
import { Ionicons } from '@expo/vector-icons'
import type { QuizQuestion } from 'shared/types'
import { useTheme } from '../theme/ThemeProvider'
import { Button, Card, radius, space, T } from './ui'

/** One question per screen. Multiple choice (>=48pt rows) or short answer with self-grading. Plain Text only. */
export function Quiz({ questions, onDone }: { questions: QuizQuestion[]; onDone: () => void }) {
  const t = useTheme()
  const [i, setI] = useState(0)
  const [picked, setPicked] = useState<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [correct, setCorrect] = useState(0)
  const [finished, setFinished] = useState(false)

  if (finished) {
    return (
      <Card style={{ alignItems: 'center', gap: space.md }}>
        <T kind="label" color={t.muted}>Score</T>
        <T kind="large" color={t.accentStrong}>{correct} / {questions.length}</T>
        <T kind="body" color={t.muted} style={{ textAlign: 'center' }}>
          {correct === questions.length ? 'Perfect. Nice work.' : 'Review the explanations, then try again.'}
        </T>
        <Button title="Done" onPress={onDone} style={{ alignSelf: 'stretch' }} />
      </Card>
    )
  }
  const q = questions[i]
  const mc = !!q.choices
  const answered = mc ? picked !== null : revealed
  const last = i + 1 >= questions.length

  const grade = (ok: boolean) => {
    void Haptics.notificationAsync(ok ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning)
    if (ok) setCorrect((c) => c + 1)
  }
  const choose = (idx: number) => {
    if (picked !== null) return
    setPicked(idx); setRevealed(true)
    grade(idx === q.answerIndex)
  }
  const next = () => {
    if (last) { setFinished(true); return }
    setI(i + 1); setPicked(null); setRevealed(false)
  }
  const selfGrade = (ok: boolean) => { grade(ok); next() }

  return (
    <View style={{ gap: space.md }}>
      <T kind="label" color={t.muted}>Question {i + 1} of {questions.length}</T>
      <T kind="title">{q.question}</T>
      {mc ? q.choices!.map((c, idx) => {
        const isAns = idx === q.answerIndex
        const isPick = idx === picked
        const border = answered ? (isAns ? t.success : isPick ? t.danger : t.border) : t.border
        return (
          <Pressable
            key={idx}
            accessibilityRole="button"
            accessibilityState={{ selected: isPick, disabled: answered }}
            accessibilityLabel={answered ? `${c}${isAns ? ', correct' : isPick ? ', your answer, wrong' : ''}` : c}
            onPress={() => choose(idx)}
            style={{ minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingHorizontal: space.md, borderRadius: radius.control, borderWidth: answered && (isAns || isPick) ? 2 : 1, borderColor: border, backgroundColor: t.surface }}
          >
            <T kind="body" style={{ flex: 1 }}>{c}</T>
            {answered && isAns ? <Ionicons name="checkmark-circle" size={22} color={t.success} /> : null}
            {answered && isPick && !isAns ? <Ionicons name="close-circle" size={22} color={t.danger} /> : null}
          </Pressable>
        )
      }) : !revealed ? (
        <Button title="Show the answer" variant="secondary" onPress={() => setRevealed(true)} />
      ) : (
        <Card style={{ backgroundColor: t.accentTint }}><T kind="body">{q.answer}</T></Card>
      )}

      {answered ? (
        <>
          <Card><T kind="footnote" color={t.muted}>{q.explanation}</T></Card>
          {!mc ? (
            <View style={{ flexDirection: 'row', gap: space.sm }}>
              <Button title="Missed it" variant="secondary" style={{ flex: 1 }} onPress={() => selfGrade(false)} />
              <Button title="Got it" style={{ flex: 1 }} onPress={() => selfGrade(true)} />
            </View>
          ) : (
            <Button title={last ? 'See score' : 'Next question'} onPress={next} />
          )}
        </>
      ) : null}
    </View>
  )
}
