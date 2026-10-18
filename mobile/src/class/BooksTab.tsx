import { View } from 'react-native'
import { useRouter } from 'expo-router'
import type { Course } from 'shared/types'
import { Button, Card, EmptyState, space, T } from '../components/ui'
import { useTheme } from '../theme/ThemeProvider'

/** This class's syllabus books with Required/Optional, and a way into the Books tab for marketplace matches. */
export function BooksTab({ course }: { course: Course }) {
  const t = useTheme()
  const router = useRouter()
  if (!course.books?.length) {
    return <EmptyState icon="book-outline" title="No books listed" body="This syllabus did not list any books." />
  }
  return (
    <View style={{ gap: space.md }}>
      {course.books.map((b, i) => (
        <Card key={i} style={{ gap: 2 }}>
          <T kind="callout">{b.title}</T>
          <T kind="footnote" color={t.muted}>{[b.author, b.edition].filter(Boolean).join(' · ')}</T>
          <T kind="footnote" color={b.required ? t.accentStrong : t.muted} style={{ fontWeight: '600' }}>{b.required ? 'Required' : 'Optional'}</T>
          {b.notes ? <T kind="footnote" color={t.muted}>{b.notes}</T> : null}
        </Card>
      ))}
      <Button title="Find copies on the Books tab" variant="secondary" onPress={() => router.navigate('/books')} />
    </View>
  )
}
