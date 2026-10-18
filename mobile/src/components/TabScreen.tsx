import { ReactNode } from 'react'
import { RefreshControlProps, ScrollView } from 'react-native'
import { useTheme } from '../theme/ThemeProvider'
import { space } from './ui'

/** Scrolling tab body. contentInsetAdjustmentBehavior lets iOS large titles collapse as you scroll. */
export function TabScreen({ children, refreshControl, bottomInset = 0 }: { children: ReactNode; bottomInset?: number; refreshControl?: React.ReactElement<RefreshControlProps> }) {
  const t = useTheme()
  return (
    <ScrollView
      style={{ backgroundColor: t.bg }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={{ padding: space.lg, paddingBottom: space.lg + bottomInset, gap: space.lg, flexGrow: 1 }}
      refreshControl={refreshControl}
    >
      {children}
    </ScrollView>
  )
}
