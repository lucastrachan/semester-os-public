import { View } from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import type { BriefingResponse, Course } from 'shared/types'
import { plain } from '../tutor/client'
import { ClassTheme, useTheme } from '../theme/ThemeProvider'
import { Card, space, T } from './ui'

function when(iso: string): { text: string; tone: 'overdue' | 'soon' | 'later' } {
  const d = new Date(`${iso}T00:00:00`)
  const now = new Date(); now.setHours(0, 0, 0, 0)
  const diff = Math.round((d.getTime() - now.getTime()) / 86400000)
  const day = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  if (diff < 0) return { text: `Overdue, ${day}`, tone: 'overdue' }
  if (diff === 0) return { text: 'Today', tone: 'soon' }
  if (diff === 1) return { text: 'Tomorrow', tone: 'soon' }
  return { text: day, tone: diff <= 3 ? 'soon' : 'later' }
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const t = useTheme()
  return (
    <View style={{ gap: space.sm }}>
      <T kind="label" color={t.muted}>{title}</T>
      {children}
    </View>
  )
}

function ClassChip({ course }: { course?: Course }) {
  const t = useTheme()
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: course?.color ?? t.accent }} />
      <T kind="callout">{course?.courseCode || course?.title || 'Class'}</T>
    </View>
  )
}

/** The master agent's morning briefing. Every string is model or syllabus text, rendered as plain Text. */
export function BriefingCard({ data, courses }: { data: BriefingResponse; courses: Course[] }) {
  const t = useTheme()
  const b = data.briefing
  const by = (id: string) => courses.find((c) => c.id === id)
  return (
    <View style={{ gap: space.lg }}>
      <Card style={{ backgroundColor: t.accentTint, borderLeftColor: t.accent, borderLeftWidth: 4 }}>
        <T kind="callout">{plain(b.greeting)}</T>
        {data.source === 'computed' ? <T kind="caption" color={t.muted} style={{ marginTop: space.xs }}>Built from your calendar. AI notes are paused.</T> : null}
      </Card>

      {b.warnings.length > 0 ? (
        <Section title="Heads up">
          <Card style={{ gap: space.sm, borderColor: t.danger }}>
            {b.warnings.map((w, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: space.sm }} accessible accessibilityLabel={`Warning: ${w}`}>
                <Ionicons name="warning" size={18} color={t.danger} />
                <T kind="body" style={{ flex: 1 }}>{plain(w)}</T>
              </View>
            ))}
          </Card>
        </Section>
      ) : null}

      <Section title="Classes today">
        {b.classesToday.length === 0 ? <T kind="body" color={t.muted}>No classes today.</T> : b.classesToday.map((c, i) => {
          const course = by(c.courseId)
          return (
            <ClassTheme key={i} hex={course?.color ?? t.accent}>
              <Card style={{ gap: space.xs, borderLeftColor: course?.color ?? t.accent, borderLeftWidth: 4 }}>
                <ClassChip course={course} />
                <T kind="footnote" color={t.muted}>{c.time}{c.location ? `  ·  ${c.location}` : ''}</T>
                {c.prep.length ? (
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.xs, marginTop: space.xs }}>
                    {c.prep.map((p, j) => (
                      <View key={j} style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: t.accentTint }}>
                        <T kind="caption">{plain(p)}</T>
                      </View>
                    ))}
                  </View>
                ) : null}
              </Card>
            </ClassTheme>
          )
        })}
      </Section>

      {b.dueSoon.length > 0 ? (
        <Section title="Due soon">
          {b.dueSoon.map((d) => {
            const course = by(d.courseId)
            return (
              <Card key={d.assignmentId} style={{ gap: 2, borderLeftColor: course?.color ?? t.accent, borderLeftWidth: 4 }}>
                <T kind="callout">{d.title}</T>
                <T kind="footnote" color={when(d.dueDate).tone === 'overdue' ? t.danger : when(d.dueDate).tone === 'soon' ? t.accentStrong : t.muted} style={{ fontWeight: '600' }}>{[course?.courseCode, when(d.dueDate).text].filter(Boolean).join('  ·  ')}</T>
                {d.hint ? <T kind="footnote">{plain(d.hint)}</T> : null}
              </Card>
            )
          })}
        </Section>
      ) : null}

      {b.priorities.length > 0 ? (
        <Section title="Priorities">
          <Card style={{ gap: space.sm }}>
            {b.priorities.map((p, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: space.sm }}>
                <T kind="callout" color={t.accentStrong} style={{ width: 22 }}>{i + 1}.</T>
                <T kind="body" style={{ flex: 1 }}>{plain(p)}</T>
              </View>
            ))}
          </Card>
        </Section>
      ) : null}
    </View>
  )
}
