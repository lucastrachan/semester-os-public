import { useState } from 'react'
import { View } from 'react-native'
import * as Haptics from 'expo-haptics'
import { Link, useRouter } from 'expo-router'
import { friendlyError } from '../../src/auth/cognito'
import { pending } from '../../src/auth/pending'
import { useAuth } from '../../src/auth/AuthContext'
import { AuthScreen } from '../../src/components/AuthScreen'
import { Button, ErrorNote, space, T, TextField } from '../../src/components/ui'
import { useTheme } from '../../src/theme/ThemeProvider'
import * as cog from '../../src/auth/cognito'

export default function SignIn() {
  const t = useTheme()
  const router = useRouter()
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!email.trim() || !password) { setError('Enter your school email and password.'); return }
    setBusy(true); setError(null)
    try {
      await signIn(email.trim().toLowerCase(), password)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
    } catch (e) {
      const name = (e as { name?: string })?.name
      if (name === 'UserNotConfirmedException') {
        pending.email = email.trim().toLowerCase(); pending.password = password
        try { await cog.resendCode(pending.email) } catch { /* the confirm screen has a resend button */ }
        router.push('/confirm')
        return
      }
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
      setError(friendlyError(e))
    } finally { setBusy(false) }
  }

  return (
    <AuthScreen title="Welcome back" subtitle="Sign in with your school email.">
      <View style={{ gap: space.lg }}>
        <TextField
          label="School email" value={email} onChangeText={setEmail} placeholder="you@ua.edu"
          keyboardType="email-address" autoCapitalize="none" autoCorrect={false}
          autoComplete="email" textContentType="username" returnKeyType="next"
        />
        <TextField
          label="Password" value={password} onChangeText={setPassword} secureTextEntry
          autoComplete="current-password" textContentType="password" returnKeyType="go" onSubmitEditing={submit}
        />
        {error ? <ErrorNote message={error} /> : null}
        <Button title="Sign in" onPress={submit} loading={busy} />
      </View>
      <View style={{ alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: space.xs }}>
        <T kind="body" color={t.muted}>New here?</T>
        <Link href="/sign-up" style={{ color: t.accentStrong, fontSize: 16, fontWeight: '600' }}>Create an account</Link>
      </View>
    </AuthScreen>
  )
}
