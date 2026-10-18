import { Platform } from 'react-native'
import type { NativeStackNavigationOptions } from 'expo-router'
import type { Theme } from '../theme/ThemeProvider'

/** Native stack header per platform: iOS large collapsing titles, Android Material-style left-aligned app bar. */
export function stackOptions(t: Theme): NativeStackNavigationOptions {
  return Platform.select<NativeStackNavigationOptions>({
    ios: {
      headerLargeTitle: true,
      headerLargeTitleShadowVisible: false,
      headerShadowVisible: false,
      headerStyle: { backgroundColor: t.bg },
      headerLargeStyle: { backgroundColor: t.bg },
      headerTitleStyle: { color: t.ink },
      headerLargeTitleStyle: { color: t.ink },
      headerTintColor: t.accentStrong,
      contentStyle: { backgroundColor: t.bg },
    },
    default: {
      headerTitleAlign: 'left',
      headerShadowVisible: false,
      headerStyle: { backgroundColor: t.surface },
      headerTitleStyle: { color: t.ink, fontSize: 22, fontWeight: '600' },
      headerTintColor: t.accentStrong,
      contentStyle: { backgroundColor: t.bg },
    },
  })!
}
