import { Platform } from 'react-native'
import { Stack } from 'expo-router'
import { stackOptions } from '../../../src/components/stackOptions'
import { useTheme } from '../../../src/theme/ThemeProvider'

export default function Layout() {
  const t = useTheme()
  return (
    <Stack screenOptions={stackOptions(t)}>
      <Stack.Screen name="index" options={{ title: 'Study' }} />
      <Stack.Screen name="[id]" options={{ title: '', headerLargeTitle: false }} />
      <Stack.Screen
        name="add"
        options={{ title: 'Add a syllabus', headerLargeTitle: false, presentation: Platform.OS === 'ios' ? 'modal' : 'card' }}
      />
    </Stack>
  )
}
