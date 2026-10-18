import 'react-native-get-random-values'
import { useEffect } from 'react'
import { ActivityIndicator, View } from 'react-native'
import { Stack } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import * as SystemUI from 'expo-system-ui'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { Logo } from '../src/components/Logo'
import { AuthProvider, useAuth } from '../src/auth/AuthContext'
import { ThemeProvider, useTheme, useThemeControl } from '../src/theme/ThemeProvider'

function Gate() {
  const { status, me } = useAuth()
  const t = useTheme()
  const { setCampusColor } = useThemeControl()

  // Campus theming: GET /me -> tenant.theme.primary -> derived colours. Signing out restores the default.
  useEffect(() => { setCampusColor(status === 'signedIn' ? me?.tenant.theme?.primary ?? null : null) }, [status, me, setCampusColor])
  useEffect(() => { void SystemUI.setBackgroundColorAsync(t.bg) }, [t.bg])

  if (status === 'loading') {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: t.bg }}>
        <Logo size={72} decorative={false} />
        <ActivityIndicator color={t.accentStrong} style={{ marginTop: 24 }} />
      </View>
    )
  }
  return (
    <>
      <StatusBar style={t.scheme === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: t.bg } }}>
        <Stack.Protected guard={status === 'signedIn'}>
          <Stack.Screen name="(tabs)" />
        </Stack.Protected>
        <Stack.Protected guard={status === 'signedOut'}>
          <Stack.Screen name="(auth)" />
        </Stack.Protected>
      </Stack>
    </>
  )
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <AuthProvider>
            <Gate />
          </AuthProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}
