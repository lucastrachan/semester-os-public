import { useState } from 'react'
import { StyleSheet, View } from 'react-native'
import * as Haptics from 'expo-haptics'
import { Gesture, GestureDetector } from 'react-native-gesture-handler'
import Animated, {
  interpolate, runOnJS, useAnimatedStyle, useReducedMotion, useSharedValue, withSpring, withTiming,
} from 'react-native-reanimated'
import type { Flashcard } from 'shared/types'
import { useTheme } from '../theme/ThemeProvider'
import { Button, Card, radius, space, T } from './ui'

/** Tap to flip. Swipe right = known, left = review. Buttons do the same for anyone who can't swipe. */
export function FlashDeck({ cards, onDone }: { cards: Flashcard[]; onDone: () => void }) {
  const t = useTheme()
  const reduce = useReducedMotion()
  const [i, setI] = useState(0)
  const [known, setKnown] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const flip = useSharedValue(0)
  const x = useSharedValue(0)

  const advance = (wasKnown: boolean) => {
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
    if (wasKnown) setKnown((k) => k + 1)
    flip.value = 0
    x.value = 0
    setFlipped(false)
    setI((n) => n + 1)
  }
  const toggle = () => {
    const to = flipped ? 0 : 1
    setFlipped(!flipped)
    flip.value = reduce ? to : withTiming(to, { duration: 280 })
  }
  const commit = (wasKnown: boolean) => {
    if (reduce) { advance(wasKnown); return }
    x.value = withTiming(wasKnown ? 500 : -500, { duration: 180 }, (fin) => { if (fin) runOnJS(advance)(wasKnown) })
  }

  const pan = Gesture.Pan()
    .activeOffsetX([-12, 12])
    .onUpdate((e) => { x.value = e.translationX })
    .onEnd((e) => {
      if (Math.abs(e.translationX) > 110) runOnJS(commit)(e.translationX > 0)
      else x.value = withSpring(0, { damping: 20 })
    })
  const tap = Gesture.Tap().onEnd(() => runOnJS(toggle)())
  const gesture = Gesture.Race(pan, tap)

  const wrap = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }, { rotate: `${x.value / 40}deg` }] }))
  const front = useAnimatedStyle(() => ({
    transform: [{ perspective: 800 }, { rotateY: `${interpolate(flip.value, [0, 1], [0, 180])}deg` }],
    opacity: reduce ? 1 - flip.value : 1,
  }))
  const back = useAnimatedStyle(() => ({
    transform: [{ perspective: 800 }, { rotateY: `${interpolate(flip.value, [0, 1], [180, 360])}deg` }],
    opacity: reduce ? flip.value : 1,
  }))

  if (i >= cards.length) {
    return (
      <Card style={{ alignItems: 'center', gap: space.md }}>
        <T kind="title">Deck finished</T>
        <T kind="body" color={t.muted}>You knew {known} of {cards.length}.</T>
        <Button title="Done" onPress={onDone} style={{ alignSelf: 'stretch' }} />
      </Card>
    )
  }
  const c = cards[i]
  const face = { backgroundColor: t.surface, borderColor: t.border }
  return (
    <View style={{ gap: space.md }}>
      <T kind="label" color={t.muted}>Card {i + 1} of {cards.length}</T>
      <GestureDetector gesture={gesture}>
        <Animated.View
          style={[{ height: 260 }, wrap]}
          accessible
          accessibilityRole="button"
          accessibilityLabel={flipped ? `Answer: ${c.back}` : `Question: ${c.front}. Double tap to flip.`}
          accessibilityActions={[{ name: 'activate' }]}
          onAccessibilityAction={toggle}
        >
          <Animated.View style={[styles.face, face, front]} pointerEvents="none">
            <T kind="label" color={t.accentStrong}>Front</T>
            <T kind="title" style={{ textAlign: 'center' }}>{c.front}</T>
          </Animated.View>
          <Animated.View style={[styles.face, face, back, { backgroundColor: t.accentTint }]} pointerEvents="none">
            <T kind="label" color={t.accentStrong}>Back</T>
            <T kind="callout" style={{ textAlign: 'center', fontWeight: '400' }}>{c.back}</T>
          </Animated.View>
        </Animated.View>
      </GestureDetector>
      <T kind="caption" color={t.muted} style={{ textAlign: 'center' }}>Tap to flip. Swipe right if you know it, left to review.</T>
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <Button title="Review" variant="secondary" style={{ flex: 1 }} onPress={() => commit(false)} />
        <Button title="Known" style={{ flex: 1 }} onPress={() => commit(true)} />
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  face: {
    position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
    backfaceVisibility: 'hidden',
    borderRadius: radius.card,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.md,
  },
})
