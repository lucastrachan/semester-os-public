import { useState } from 'react'
import { View } from 'react-native'
import * as Haptics from 'expo-haptics'
import { useRouter } from 'expo-router'
import { useAuth } from '../../src/auth/AuthContext'
import { confirmSignUp, friendlyError, resendCode } from '../../src/auth/cognito'
import { pending } from '../../src/auth/pending'
import { AuthScreen } from '../../src/components/AuthScreen'
import { Button, ErrorNote, space, T, TextField } from '../../src/components/ui'
import { useTheme } from '../../src/theme/ThemeProvider'

export default function Confirm() {
  const t = useTheme()
  const router = useRouter()
  const { signIn } = useAuth()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  async function submit() {
    if (!code.trim()) { setError('Enter the 6-digit code from your email.'); return }
    setBusy(true); setError(null)
    try {
      await confirmSignUp(pending.email, code)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      try {
        await signIn(pending.email, pending.password) // signing in swaps the auth stack for the tabs
        pending.password = ''
      } catch {
        router.replace('/sign-in') // confirmed, but sign-in failed: let them try by hand
      }
    } catch (e) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
      setError(friendlyError(e))
    } finally { setBusy(false) }
  }

  async function resend() {
    setError(null); setNote(null)
    try { await resendCode(pending.email); setNote('We sent a new code.') } catch (e) { setError(friendlyError(e)) }
  }

  return (
    <AuthScreen title="Check your email" subtitle={`We sent a 6-digit code to ${pending.email || 'your school email'}. It can take a minute and may land in spam.`}>
      <View style={{ gap: space.lg }}>
        <TextField
          label="Confirmation code" value={code} onChangeText={setCode} placeholder="123456"
          keyboardType="number-pad" autoComplete="one-time-code" textContentType="oneTimeCode"
          maxLength={8} returnKeyType="go" onSubmitEditing={submit}
        />
        {error ? <ErrorNote message={error} /> : null}
        {note ? <T kind="footnote" color={t.success}>{note}</T> : null}
        <Button title="Confirm and sign in" onPress={submit} loading={busy} />
        <Button title="Send a new code" variant="plain" onPress={resend} />
        <Button title="Back" variant="plain" onPress={() => router.back()} />
      </View>
    </AuthScreen>
  )
}
