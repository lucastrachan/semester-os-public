import { useEffect, useRef, useState } from 'react'
import { AccessibilityInfo, View } from 'react-native'
import * as Haptics from 'expo-haptics'
import { Link, useRouter } from 'expo-router'
import { EDU_ONLY, friendlyError, signUp } from '../../src/auth/cognito'
import { pending } from '../../src/auth/pending'
import { AuthScreen } from '../../src/components/AuthScreen'
import { Button, ErrorNote, space, T, TextField } from '../../src/components/ui'
import { useAuth } from '../../src/auth/AuthContext'
import { domainOf, resolveSchool } from '../../src/resolve'
import { useTheme, useThemeControl } from '../../src/theme/ThemeProvider'

export default function SignUp() {
  const t = useTheme()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { api } = useAuth()
  const { setCampusColor } = useThemeControl()
  type Res = { state: 'idle' | 'resolving' | 'unknown' } | { state: 'resolved'; name: string; placeholder: boolean }
  const [res, setRes] = useState<Res>({ state: 'idle' })
  const lastDomain = useRef<string | null>(null)

  // Debounced (400ms) domain lookup. Resolved: theme the screen to the school. Unknown: stay neutral.
  useEffect(() => {
    const domain = domainOf(email)
    if (!domain) { lastDomain.current = null; setRes({ state: 'idle' }); setCampusColor(null); return }
    if (domain === lastDomain.current) return
    setRes({ state: 'resolving' })
    let alive = true
    const timer = setTimeout(async () => {
      const school = await resolveSchool(api, domain)
      if (!alive) return
      lastDomain.current = domain
      if (school) {
        setCampusColor(school.primary)
        setRes({ state: 'resolved', name: school.name, placeholder: school.colorStatus === 'placeholder' || school.colorStatus === 'needs_review' || (!school.colorStatus && !!school.autoCreated) })
        void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
        AccessibilityInfo.announceForAccessibility(`Sign up for ${school.name}`)
      } else {
        setCampusColor(null)
        setRes({ state: 'unknown' })
        AccessibilityInfo.announceForAccessibility('This is not a .edu address')
      }
    }, 400)
    return () => { alive = false; clearTimeout(timer) }
  }, [email, api, setCampusColor])
  useEffect(() => () => setCampusColor(null), [setCampusColor])

  async function submit() {
    const e = email.trim().toLowerCase()
    if (!e || !password) { setError('Enter your school email and a password.'); return }
    setBusy(true); setError(null)
    try {
      await signUp(e, password)
      pending.email = e; pending.password = password
      router.push('/confirm')
    } catch (err) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
      setError(friendlyError(err))
    } finally { setBusy(false) }
  }

  return (
    <AuthScreen
      title={res.state === 'resolved' ? `Sign up for ${res.name}` : 'Sign up for your school'}
      subtitle="Use your school email to get started."
      titlePending={res.state === 'resolving'}
    >
      <View style={{ gap: space.lg }}>
        <TextField
          label="School email" value={email} onChangeText={setEmail} placeholder="you@ua.edu"
          keyboardType="email-address" autoCapitalize="none" autoCorrect={false}
          autoComplete="email" textContentType="username" returnKeyType="next"
        />
        <TextField
          label="Password" value={password} onChangeText={setPassword} secureTextEntry
          placeholder="8+ characters, at least one number"
          autoComplete="new-password" textContentType="newPassword" returnKeyType="go" onSubmitEditing={submit}
        />
        {res.state === 'unknown' ? (
          <T kind="footnote" color={t.muted}>{`This isn't a .edu address. ${EDU_ONLY}`}</T>
        ) : res.state === 'resolved' && res.placeholder ? (
          <T kind="footnote" color={t.muted}>Colours for this school are still being detected. Yours is a placeholder for now.</T>
        ) : null}
        {error ? <ErrorNote message={error} /> : null}
        <Button title="Create account" onPress={submit} loading={busy} />
      </View>
      <View style={{ alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: space.xs }}>
        <T kind="body" color={t.muted}>Already have an account?</T>
        <Link href="/sign-in" style={{ color: t.accentStrong, fontSize: 16, fontWeight: '600' }}>Sign in</Link>
      </View>
    </AuthScreen>
  )
}
