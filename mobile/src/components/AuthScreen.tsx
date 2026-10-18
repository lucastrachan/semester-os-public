import { ReactNode } from 'react'
import { KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { useTheme } from '../theme/ThemeProvider'
import { Logo } from './Logo'
import { space, T } from './ui'

/** Shared frame for sign-in, sign-up and confirm: safe areas, keyboard avoidance, brand mark. */
export function AuthScreen({ title, subtitle, children, titlePending }: { title: string; subtitle: string; children: ReactNode; titlePending?: boolean }) {
  const t = useTheme()
  const insets = useSafeAreaInsets()
  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: t.bg }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{
          flexGrow: 1,
          justifyContent: 'center',
          padding: space.xl,
          paddingTop: insets.top + space.xl,
          paddingBottom: insets.bottom + space.xl,
          gap: space.xl,
        }}
      >
        <View style={{ gap: space.sm }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
            <Logo size={36} />
            <T kind="label" color={t.accentStrong}>Semester OS</T>
          </View>
          {/* Fixed height so the form doesn't jump when the school name arrives. */}
          <View style={{ minHeight: 76, justifyContent: 'center' }}>
            {titlePending ? (
              <View accessibilityLabel="Looking up your school" style={{ height: 30, width: '70%', borderRadius: 15, backgroundColor: t.accentTint }} />
            ) : (
              <T kind="large" style={{ fontWeight: '700' }} numberOfLines={2}>{title}</T>
            )}
          </View>
          <T kind="body" color={t.muted}>{subtitle}</T>
        </View>
        {children}
      </ScrollView>
    </KeyboardAvoidingView>
  )
}
