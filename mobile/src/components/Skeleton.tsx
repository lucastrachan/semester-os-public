import { useEffect } from 'react'
import { View, ViewStyle } from 'react-native'
import Animated, { cancelAnimation, useAnimatedStyle, useReducedMotion, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated'
import { useTheme } from '../theme/ThemeProvider'
import { radius, space } from './ui'

/** Shimmering placeholder. Static under Reduce Motion. Hidden from screen readers (the screen announces loading itself). */
export function SkeletonBlock({ height = 16, width = '100%', style }: { height?: number; width?: number | `${number}%`; style?: ViewStyle }) {
  const t = useTheme()
  const reduce = useReducedMotion()
  const o = useSharedValue(0.55)
  useEffect(() => {
    if (reduce) { o.value = 0.7; return }
    o.value = withRepeat(withTiming(1, { duration: 900 }), -1, true)
    return () => cancelAnimation(o)
  }, [reduce, o])
  const anim = useAnimatedStyle(() => ({ opacity: o.value }))
  return (
    <Animated.View
      accessibilityElementsHidden importantForAccessibility="no-hide-descendants"
      style={[{ height, width, borderRadius: radius.control, backgroundColor: t.border }, anim, style]}
    />
  )
}

/** A card-shaped placeholder list that matches the final layout (robot + two text lines). */
export function SkeletonCards({ count = 3 }: { count?: number }) {
  const t = useTheme()
  return (
    <View accessible accessibilityLabel="Loading" style={{ gap: space.sm }}>
      {Array.from({ length: count }).map((_, i) => (
        <View key={i} style={{ flexDirection: 'row', gap: space.md, alignItems: 'center', padding: space.lg, borderRadius: radius.card, borderWidth: 1, borderColor: t.border, backgroundColor: t.surface }}>
          <SkeletonBlock height={52} width={52} />
          <View style={{ flex: 1, gap: space.sm }}>
            <SkeletonBlock height={16} width="55%" />
            <SkeletonBlock height={12} width="85%" />
          </View>
        </View>
      ))}
    </View>
  )
}
