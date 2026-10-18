import { useRef } from 'react'
import { Pressable, View } from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import ReanimatedSwipeable, { SwipeableMethods } from 'react-native-gesture-handler/ReanimatedSwipeable'
import type { Assignment } from 'shared/types'
import { timeLabel } from '../calendar/data'
import { useTheme } from '../theme/ThemeProvider'
import { radius, space, T } from './ui'

/** One deadline row: checkbox (44pt), swipe right to complete, Estimated and Blackboard tags. Used by Calendar and class Deadlines. */
export function AssignmentRow({ a, onToggle }: { a: Assignment; onToggle: (a: Assignment) => void }) {
  const t = useTheme()
  const ref = useRef<SwipeableMethods>(null)
  const estimated = a.dateSource === 'resolved'
  const body = (
    <View style={{ minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md, backgroundColor: t.surface, borderRadius: radius.control, borderLeftWidth: 4, borderLeftColor: t.accent }}>
      <Pressable
        accessibilityRole="checkbox" accessibilityState={{ checked: a.done }}
        accessibilityLabel={`${a.done ? 'Mark not done' : 'Mark done'}: ${a.title}`}
        hitSlop={8} onPress={() => onToggle(a)}
        style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}
      >
        <Ionicons name={a.done ? 'checkmark-circle' : 'ellipse-outline'} size={26} color={a.done ? t.success : t.accentStrong} />
      </Pressable>
      <View style={{ flex: 1, gap: 2 }} accessible accessibilityLabel={`${a.courseCode ?? ''} ${a.title}, ${a.dueDate ?? 'no date'} ${timeLabel(a)}${estimated ? ', estimated' : ''}`}>
        <T kind="callout" numberOfLines={2} style={{ textDecorationLine: a.done ? 'line-through' : 'none', opacity: a.done ? 0.6 : 1 }}>{a.title}</T>
        <T kind="footnote" color={t.accentStrong} style={{ fontWeight: '600' }}>{[a.courseCode, a.type, timeLabel(a), a.weight ? `${a.weight}%` : '', a.source === 'feed' ? 'from Blackboard' : ''].filter(Boolean).join('  ·  ')}</T>
      </View>
      {estimated ? (
        <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: t.accentTint }}>
          <T kind="caption" color={t.accentStrong} style={{ fontWeight: '700' }}>Estimated</T>
        </View>
      ) : null}
    </View>
  )
  return (
    <ReanimatedSwipeable
      ref={ref}
      overshootLeft={false}
      renderLeftActions={() => (
        <View style={{ width: 96, alignItems: 'center', justifyContent: 'center', backgroundColor: t.success, borderRadius: radius.control, marginRight: space.sm }}>
          <Ionicons name="checkmark" size={26} color={t.scheme === 'dark' ? '#10131A' : '#FFFFFF'} />
        </View>
      )}
      onSwipeableOpen={(dir) => { if (dir === 'left') { onToggle(a); ref.current?.close() } }}
    >
      {body}
    </ReanimatedSwipeable>
  )
}

