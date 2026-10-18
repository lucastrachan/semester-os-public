import { Stack } from 'expo-router'
import { stackOptions } from '../../../src/components/stackOptions'
import { useTheme } from '../../../src/theme/ThemeProvider'

export default function Layout() {
  const t = useTheme()
  return (
    <Stack screenOptions={stackOptions(t)}>
      <Stack.Screen name="index" options={{ title: 'Calendar' }} />
      <Stack.Screen name="unassigned" options={{ title: 'Blackboard inbox', headerLargeTitle: false }} />
    </Stack>
  )
}
