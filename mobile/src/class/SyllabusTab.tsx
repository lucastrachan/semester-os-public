import { View } from 'react-native'
import type { Course } from 'shared/types'
import { Card, space, T } from '../components/ui'
import { useTheme } from '../theme/ThemeProvider'

function Fact({ label, value }: { label: string; value?: string }) {
  const t = useTheme()
  if (!value) return null
  return (
    <View style={{ gap: 2 }}>
      <T kind="caption" color={t.muted}>{label}</T>
      <T kind="body">{value}</T>
    </View>
  )
}

export function SyllabusTab({ c }: { c: Course }) {
  const t = useTheme()
  return (
    <View style={{ gap: space.lg }}>
      {c.summary ? <Card><T kind="body">{c.summary}</T></Card> : null}
      <Card style={{ gap: space.md }}>
        <Fact label="Instructor" value={c.instructor} />
        <Fact label="Term" value={c.term} />
        <Fact label="Office hours" value={c.officeHours} />
        {c.meetings?.map((m, i) => (
          <Fact key={i} label="Meets" value={`${m.days.join(', ')} ${m.start}-${m.end}${m.location ? `, ${m.location}` : ''}`} />
        ))}
      </Card>
      {c.grading?.length ? (
        <>
          <T kind="label" color={t.muted}>Grading</T>
          <Card style={{ gap: space.sm }}>
            {c.grading.map((g, i) => (
              <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <T kind="body" style={{ flex: 1 }}>{g.item}</T>
                <T kind="body" color={t.accentStrong} style={{ fontWeight: '600' }}>{g.percent}%</T>
              </View>
            ))}
          </Card>
        </>
      ) : null}
      {c.policies && Object.values(c.policies).some(Boolean) ? (
        <>
          <T kind="label" color={t.muted}>Policies</T>
          <Card style={{ gap: space.md }}>
            <Fact label="Late work" value={c.policies.late} />
            <Fact label="Attendance" value={c.policies.attendance} />
            <Fact label="AI use" value={c.policies.ai} />
            <Fact label="Other" value={c.policies.other} />
          </Card>
        </>
      ) : null}
      {c.books?.length ? (
        <>
          <T kind="label" color={t.muted}>Books</T>
          <Card style={{ gap: space.md }}>
            {c.books.map((b, i) => (
              <View key={i} style={{ gap: 2 }}>
                <T kind="body" style={{ fontWeight: '600' }}>{b.title}</T>
                <T kind="footnote" color={t.muted}>{[b.author, b.edition, b.required ? 'Required' : 'Optional'].filter(Boolean).join(' · ')}</T>
              </View>
            ))}
          </Card>
        </>
      ) : null}
    </View>
  )
}

