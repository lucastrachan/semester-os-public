import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { signUp, confirmSignUp, signIn, signOut as amplifySignOut } from 'aws-amplify/auth'
import { useAuth } from '../context/AuthContext'
import { useResolveDomain } from '../lib/resolve'
import { applyCampusTheme } from '../styles/theme'
import { validatePart, cleanName } from '../lib/name'

type Mode = 'signUp' | 'confirm' | 'signIn'

/** Where to go after signing in: the page the student was sent away from (same-site paths only), else null. */
function readReturn(state: unknown): string | null {
  let p: string | null = null
  const from = (state as { from?: { pathname?: string; search?: string } } | null)?.from
  if (from?.pathname) p = from.pathname + (from.search ?? '')
  if (!p) { try { p = sessionStorage.getItem('sos:return') } catch { /* ignore */ } }
  return p && /^\/[A-Za-z0-9]/.test(p) && !p.startsWith('//') && !p.startsWith('/auth') ? p : null
}

export default function AuthPage() {
  const location = useLocation()
  const returnTo = useRef<string | null>(readReturn(location.state))
  const finishReturn = () => { try { sessionStorage.removeItem('sos:return') } catch { /* ignore */ } }
  const [params] = useSearchParams()
  const [mode, setMode] = useState<Mode>(params.get('mode') === 'signin' ? 'signIn' : 'signUp')
  const [first, setFirst] = useState('')
  const [last, setLast] = useState('')
  const [nameError, setNameError] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { refresh, user } = useAuth()
  const navigate = useNavigate()
  const expired = params.get('expired') === '1'

  // Already signed in (for example a returning visitor): skip the form instead of tripping over the live session.
  const justSignedIn = useRef(false) // set by this form's own sign-in so it can choose where to go next
  useEffect(() => { if (user && !justSignedIn.current) navigate(returnTo.current ?? '/today', { replace: true }) }, [user, navigate])
  const school = useResolveDomain(mode === 'signUp' ? email : '')

  // Theme live as the school resolves; unknown or empty goes back to the default accent.
  useEffect(() => {
    applyCampusTheme(school.state === 'resolved' ? school.color : undefined)
  }, [school.state, school.color])

  function clearError() { setError('') }

  /**
   * Sign in, tolerating a stale or half-finished session: if Amplify says someone is already signed in, clear it
   * silently and try once more. Returns null on success, or a friendly message (never a raw Amplify string).
   */
  async function safeSignIn(): Promise<string | null> {
    const attempt = async () => {
      const res = await signIn({ username: email, password })
      if (res.isSignedIn) return null
      const step = (res.nextStep as { signInStep?: string } | undefined)?.signInStep
      if (step === 'CONFIRM_SIGN_UP') { setMode('confirm'); return 'Check your email for the verification code to finish creating your account.' }
      return "We couldn't finish signing you in here. Please try again, or reset your password."
    }
    try {
      return await attempt()
    } catch (err: any) {
      if (err?.name === 'UserAlreadyAuthenticatedException' || /already.*signed in/i.test(err?.message ?? '')) {
        try { await amplifySignOut() } catch { /* nothing to clear */ }
        try { return await attempt() } catch (e2) { return friendlyError(e2) }
      }
      return friendlyError(err)
    }
  }

  async function handleSignUp(e: React.FormEvent) {
    e.preventDefault(); clearError()
    const bad = validatePart(first, 'first') ?? validatePart(last, 'last')
    if (bad) { setNameError(bad); return }
    setNameError(''); setLoading(true)
    try {
      try { await amplifySignOut() } catch { /* no stale session */ }
      await signUp({ username: email, password, options: { userAttributes: { email, name: `${cleanName(first)} ${cleanName(last)}` } } })
      setMode('confirm')
    } catch (err: any) {
      setError(friendlyError(err))
    } finally { setLoading(false) }
  }

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); clearError()
    try {
      try {
        await confirmSignUp({ username: email, confirmationCode: code.trim() })
      } catch (err: any) {
        // Already confirmed (a double tap, or an earlier attempt worked): carry on to sign-in.
        if (!/CONFIRMED|already.*confirm/i.test(`${err?.name} ${err?.message}`)) throw err
      }
      const problem = await safeSignIn()
      if (problem) { setError(problem); return }
      justSignedIn.current = true
      await refresh()
      const back = returnTo.current; finishReturn()
      navigate(back ?? '/onboarding')
    } catch (err: any) {
      setError(friendlyError(err))
    } finally { setLoading(false) }
  }

  async function handleSignIn(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); clearError()
    try {
      const problem = await safeSignIn()
      if (problem) { setError(problem); return }
      justSignedIn.current = true
      await refresh()
      const back = returnTo.current; finishReturn()
      navigate(back ?? '/today')
    } catch (err: any) {
      setError(friendlyError(err))
    } finally { setLoading(false) }
  }

  return (
    <main className="form-page auth-page">
      <Link to="/" className="back-link">← Semester OS</Link>

      {mode === 'signUp' && (
        <>
          <header className="signup-header" data-state={school.state}>
            <h1>Sign up for <span className="signup-campus">{school.state === 'resolved' ? school.name : school.state === 'resolving' ? '…' : 'your school'}</span></h1>
            <p>Use your school email to get started.</p>
            <p className="signup-hint" aria-live="polite" data-kind={school.state === 'resolved' ? 'ok' : school.state === 'unknown' ? 'unknown' : undefined}>
              {school.state === 'resolved' && `Found ${school.name}.`}
              {school.state === 'unknown' && 'Semester OS supports US colleges (.edu email addresses) for now.'}
              {school.state === 'resolved' && school.colorStatus === 'placeholder' && ' We picked a placeholder colour until your school is verified.'}
            </p>
          </header>
          <form className="request-form" onSubmit={handleSignUp} noValidate>
            <div className="field">
              <label htmlFor="su-first">First name</label>
              <input id="su-first" type="text" value={first} onChange={e => { setFirst(e.target.value); setNameError('') }}
                placeholder="First name" required autoFocus autoComplete="given-name" maxLength={40}
                aria-invalid={nameError ? true : undefined} aria-describedby={nameError ? 'su-name-err' : undefined} />
            </div>
            <div className="field">
              <label htmlFor="su-last">Last name</label>
              <input id="su-last" type="text" value={last} onChange={e => { setLast(e.target.value); setNameError('') }}
                placeholder="Last name" required autoComplete="family-name" maxLength={40}
                aria-invalid={nameError ? true : undefined} aria-describedby={nameError ? 'su-name-err' : undefined} />
              {nameError && <span id="su-name-err" className="field-error" role="alert">{nameError}</span>}
            </div>
            <div className="field">
              <label htmlFor="su-email">School email</label>
              <input id="su-email" type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="you@ua.edu" required autoComplete="email" />
            </div>
            <div className="field">
              <label>Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="8+ characters, at least one number" required autoComplete="new-password" />
            </div>
            {error && (
              <div className="auth-error">
                <span>{error}</span>
              </div>
            )}
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Creating account…' : 'Create account'}
            </button>
            <p className="auth-switch">
              Already have an account?{' '}
              <button type="button" className="link-btn" onClick={() => { setMode('signIn'); clearError() }}>
                Sign in
              </button>
            </p>
          </form>
        </>
      )}

      {mode === 'confirm' && (
        <>
          <header>
            <h1>Check your email</h1>
            <p>We sent a verification code to <strong>{email}</strong>.</p>
          </header>
          <form className="request-form" onSubmit={handleConfirm} noValidate>
            <div className="field">
              <label>Verification code</label>
              <input value={code} onChange={e => setCode(e.target.value)}
                placeholder="Enter 6-digit code" required autoFocus inputMode="numeric"
                className="code-input" />
            </div>
            {error && <p className="auth-error">{error}</p>}
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Verifying…' : 'Confirm account'}
            </button>
            <p className="auth-switch">
              Wrong email?{' '}
              <button type="button" className="link-btn" onClick={() => setMode('signUp')}>Go back</button>
            </p>
          </form>
        </>
      )}

      {mode === 'signIn' && (
        <>
          <header>
            <h1>Sign in</h1>
            {expired && <p className="signup-hint" data-kind="unknown" role="status">Your session expired, please sign in again.</p>}
          </header>
          <form className="request-form" onSubmit={handleSignIn} noValidate>
            <div className="field">
              <label>School email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="you@ua.edu" required autoFocus autoComplete="email" />
            </div>
            <div className="field">
              <label>Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                required autoComplete="current-password" />
            </div>
            {error && <p className="auth-error">{error}</p>}
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
            <p className="auth-switch">
              No account?{' '}
              <button type="button" className="link-btn" onClick={() => { setMode('signUp'); clearError() }}>
                Create one
              </button>
            </p>
          </form>
        </>
      )}
    </main>
  )
}

/** Maps any error to a plain sentence. Raw Amplify/Cognito strings are never shown. */
function friendlyError(err: any): string {
  const raw: string = `${err?.name ?? ''} ${err?.message ?? String(err)}`
  // Our own pre-signup message (the school isn't supported): Cognito wraps it, so strip the prefix and show it.
  const wrapped = /PreSignUp failed with error\s*(.*)$/is.exec(raw)
  if (wrapped && wrapped[1].trim()) return wrapped[1].trim().slice(0, 240)
  if (/UserNotFoundException|NotAuthorizedException|Incorrect username or password/i.test(raw)) return 'Incorrect email or password.'
  if (/UserNotConfirmedException/i.test(raw)) return 'Please verify your email first. Check your inbox for the code.'
  if (/UsernameExistsException/i.test(raw)) return 'An account with this email already exists. Sign in instead.'
  if (/InvalidPasswordException|InvalidParameterException.*password/i.test(raw)) return 'Password must be at least 8 characters and include a number.'
  if (/CodeMismatchException/i.test(raw)) return 'That code is incorrect. Check your email and try again.'
  if (/ExpiredCodeException/i.test(raw)) return 'That code has expired. Sign up again to get a new one.'
  if (/LimitExceededException|TooManyRequests|TooManyFailedAttempts/i.test(raw)) return 'Too many attempts. Wait a few minutes and try again.'
  if (/NetworkError|Failed to fetch|network/i.test(raw)) return 'Network problem. Check your connection and try again.'
  return 'Something went wrong. Please try again.'
}
