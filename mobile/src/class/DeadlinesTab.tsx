import { useMemo } from 'react'
import { View } from 'react-native'
import type { Assignment } from 'shared/types'
import { AssignmentRow } from '../components/AssignmentRow'
import { EmptyState, space, T } from '../components/ui'
import { dayLabel } from '../calendar/data'
import { ClassTheme, useTheme } from '../theme/ThemeProvider'

/** The class's deadlines with the same row as Calendar: checkbox, swipe to complete, Estimated pill, from-Blackboard tag. */
export function DeadlinesTab({ items, color, onToggle }: { items: Assignment[]; color: string; onToggle: (a: Assignment) => void }) {
  const t = useTheme()
  const sections = useMemo(() => {
    const dated = items.filter((a) => a.dueDate)
    const undated = items.filter((a) => !a.dueDate)
    const keys = [...new Set(dated.map((a) => a.dueDate!))].sort()
    const out = keys.map((k) => ({ key: k, title: dayLabel(k), data: dated.filter((a) => a.dueDate === k) }))
    if (undated.length) out.push({ key: 'none', title: 'Needs a date', data: undated })
    return out
  }, [items])

  if (!items.length) return <EmptyState icon="checkmark-done-outline" title="No deadlines" body="This class has no dated work yet. Check Blackboard or add a syllabus." />
  return (
    <ClassTheme hex={color}>
      <View style={{ gap: space.sm }}>
        {sections.map((s) => (
          <View key={s.key} style={{ gap: space.sm }}>
            <T kind="label" color={t.muted} style={{ marginTop: space.sm }}>{s.title}</T>
            {s.data.map((a) => <AssignmentRow key={a.id} a={a} onToggle={onToggle} />)}
          </View>
        ))}
      </View>
    </ClassTheme>
  )
}
