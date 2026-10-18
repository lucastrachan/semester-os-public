import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import QRCode from 'qrcode'
import { signIn, confirmSignIn, signOut as amplifySignOut, fetchAuthSession } from 'aws-amplify/auth'
import { api } from './api'

interface Admin { email: string }
interface Ctx { admin: Admin; signOut: () => Promise<void> }
const AuthCtx = createContext<Ctx | null>(null)
export const useAdmin = () => {
  const c = useContext(AuthCtx)
  if (!c) throw new Error('outside AuthGate')
  return c
}

type Step =
  | { kind: 'credentials' }
  | { kind: 'newPassword' }
  | { kind: 'totpSetup'; secret: string }
  | { kind: 'totpCode' }

const IDLE_MS = 15 * 60 * 1000

function friendly(e: unknown): string {
  const name = (e as any)?.name as string | undefined
  switch (name) {
    case 'NotAuthorizedException': return 'Incorrect email or password.'
    case 'CodeMismatchException':
    case 'EnableSoftwareTokenMFAException': return 'That code was not accepted. Check the code and try again.'
    case 'ExpiredCodeException': return 'That code expired. Enter the newest one.'
    case 'InvalidPasswordException': return 'Password must be 12+ characters with upper and lower case, a digit and a symbol.'
    case 'LimitExceededException':
    case 'TooManyRequestsException': return 'Too many attempts. Wait a few minutes and try again.'
    default:
      if (e instanceof TypeError) return 'Could not reach the sign-in service. Check your connection and try again.'
      return 'Something went wrong. Try again.'
  }
}

/** Maps a failed /admin/me call to a safe, readable message (never raw server text). */
function describeVerifyError(e: any): string {
  const status = typeof e?.status === 'number' ? e.status : 0
  if (status === 403) return 'This account is not an administrator.'
  if (status === 401) return 'Your session was not accepted by the server. Sign in again.'
  if (status === 500) return 'The admin service is misconfigured (server error 500). Tell the platform owner.'
  if (status >= 500) return `The admin service had a problem (error ${status}). Try again in a minute.`
  if (status > 0) return `The admin service refused the request (error ${status}).`
  if (e instanceof TypeError || /failed to fetch|network|load failed/i.test(String(e?.message))) {
    return 'Could not reach the admin service. Check your connection; if it keeps happening the service may be blocking this site (network or CORS error).'
  }
  return 'Sign-in could not be completed. Try again.'
}

function isLostSignIn(e: any): boolean {
  const text = `${e?.name ?? ''} ${e?.message ?? ''}`
  return /signIn was not called|before confirmSignIn|no active sign|SignInException|InvalidStateException/i.test(text)
}

/** Shows the staff sign-in flow until a valid admin session exists, then renders children. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<Admin | null>(null)
  const [checking, setChecking] = useState(true)
  const [notice, setNotice] = useState<{ text: string; n: number }>({ text: '', n: 0 })
  const say = (text: string) => setNotice(p => ({ text, n: p.n + 1 }))

  async function establish() {
    let failure = ''
    try {
      const session = await fetchAuthSession()
      if (!session.tokens?.idToken) { setAdmin(null); return }
      const me = await api<{ email: string }>('/admin/me')
      setAdmin({ email: me.email })
      setNotice(p => ({ text: '', n: p.n + 1 }))
      return
    } catch (e: any) {
      failure = describeVerifyError(e)
    } finally {
      setChecking(false)
    }
    // Verification failed after a session exists: drop the session so the next attempt starts clean.
    try { await amplifySignOut() } catch { /* already signed out */ }
    setAdmin(null)
    say(failure)
  }
  useEffect(() => { void establish() }, [])

  async function signOut() {
    await amplifySignOut()
    setAdmin(null)
  }

  // Sign out after 15 minutes without interaction.
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => {
    if (!admin) return
    const reset = () => {
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => { void signOut() }, IDLE_MS)
    }
    const events = ['pointerdown', 'keydown', 'scroll']
    events.forEach(ev => window.addEventListener(ev, reset))
    reset()
    return () => { events.forEach(ev => window.removeEventListener(ev, reset)); window.clearTimeout(timer.current) }
  }, [admin])

  if (checking) return <main className="ops-center"><p className="muted" role="status">Checking session…</p></main>
  if (!admin) return <SignIn notice={notice} onDone={() => establish()} />
  return <AuthCtx.Provider value={{ admin, signOut }}>{children}</AuthCtx.Provider>
}

type SignInResult = Awaited<ReturnType<typeof signIn>>

function SignIn({ notice, onDone }: { notice: { text: string; n: number }; onDone: () => Promise<void> }) {
  const [step, setStep] = useState<Step>({ kind: 'credentials' })
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [newPw, setNewPw] = useState('')
  const [newPw2, setNewPw2] = useState('')
  const [code, setCode] = useState('')
  const [qr, setQr] = useState('')
  const [err, setErr] = useState(notice.text)
  const [busy, setBusy] = useState(false)
  const [verifying, setVerifying] = useState(false)

  // Show messages raised by the gate (denied, network error...) and return to the first step.
  useEffect(() => {
    if (!notice.n) return
    setErr(notice.text)
    if (notice.text) { setStep({ kind: 'credentials' }); setCode(''); setPassword('') }
  }, [notice])

  async function handleNext(out: SignInResult) {
    const s = out.nextStep
    switch (s.signInStep) {
      case 'DONE': setVerifying(true); try { await onDone() } finally { setVerifying(false) } return
      case 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED': setStep({ kind: 'newPassword' }); return
      case 'CONTINUE_SIGN_IN_WITH_TOTP_SETUP': {
        const uri = s.totpSetupDetails.getSetupUri('Semester OS Admin', email).toString()
        setQr(await QRCode.toDataURL(uri, { margin: 1, width: 192 }))
        setStep({ kind: 'totpSetup', secret: s.totpSetupDetails.sharedSecret })
        setCode('')
        return
      }
      case 'CONFIRM_SIGN_IN_WITH_TOTP_CODE': setStep({ kind: 'totpCode' }); setCode(''); return
      default: setErr('This account needs a sign-in step this console does not support. Ask another admin.')
    }
  }

  async function run(fn: () => Promise<SignInResult>) {
    setBusy(true); setErr('')
    try { await handleNext(await fn()) } catch (e) {
      if (isLostSignIn(e)) {
        try { await amplifySignOut() } catch { /* nothing to sign out */ }
        setStep({ kind: 'credentials' }); setCode(''); setPassword('')
        setErr('Your sign-in session expired, sign in again.')
      } else setErr(friendly(e))
    } finally { setBusy(false) }
  }

  async function submitCredentials(ev: React.FormEvent) {
    ev.preventDefault()
    const username = email.trim().toLowerCase()
    await run(async () => {
      try {
        return await signIn({ username, password })
      } catch (e: any) {
        if (e?.name === 'UserAlreadyAuthenticatedException') {
          await amplifySignOut()
          return await signIn({ username, password })
        }
        throw e
      }
    })
    setPassword('')
  }

  async function submitNewPassword(ev: React.FormEvent) {
    ev.preventDefault()
    if (newPw !== newPw2) { setErr('The two passwords do not match.'); return }
    await run(() => confirmSignIn({ challengeResponse: newPw }))
    setNewPw(''); setNewPw2('')
  }

  async function submitCode(ev: React.FormEvent) {
    ev.preventDefault()
    await run(() => confirmSignIn({ challengeResponse: code.replace(/\s/g, '') }))
  }

  const title = {
    credentials: 'Sign in', newPassword: 'Choose a new password',
    totpSetup: 'Set up two-step verification', totpCode: 'Two-step verification',
  }[step.kind]
  const codeOk = code.replace(/\s/g, '').length === 6

  return (
    <main className="ops-center">
      <div className="window">
        <div className="window-bar"><span className="window-dots"><i /><i /><i /></span><span className="window-title">Semester OS admin</span></div>
        <div className="window-body ops-form">
          <h1 className="ops-h1">{title}</h1>

          {step.kind === 'credentials' && (
            <form className="ops-form" onSubmit={submitCredentials}>
              <p className="muted">Staff only. Accounts are created by an existing administrator.</p>
              <div className="field"><label htmlFor="em">Email</label>
                <input id="em" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} autoFocus /></div>
              <div className="field"><label htmlFor="pw">Password</label>
                <input id="pw" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></div>
              <button className="btn-primary" disabled={busy || !email || !password} aria-busy={busy}>Continue</button>
            </form>
          )}

          {step.kind === 'newPassword' && (
            <form className="ops-form" onSubmit={submitNewPassword}>
              <p className="muted">First sign-in. Use 12 or more characters with upper and lower case, a digit and a symbol.</p>
              <div className="field"><label htmlFor="np">New password</label>
                <input id="np" type="password" autoComplete="new-password" minLength={12} required value={newPw} onChange={e => setNewPw(e.target.value)} autoFocus /></div>
              <div className="field"><label htmlFor="np2">Repeat new password</label>
                <input id="np2" type="password" autoComplete="new-password" minLength={12} required value={newPw2} onChange={e => setNewPw2(e.target.value)} /></div>
              <button className="btn-primary" disabled={busy} aria-busy={busy}>Set password</button>
            </form>
          )}

          {step.kind === 'totpSetup' && (
            <form className="ops-form" onSubmit={submitCode}>
              <p className="muted">Scan this QR code with an authenticator app (1Password, Authy, Google Authenticator), then enter the 6-digit code.</p>
              {qr && <img className="ops-qr" src={qr} alt="QR code for your authenticator app" />}
              <details><summary className="muted">Cannot scan? Enter the key by hand</summary>
                <div className="ops-secret">{step.secret}</div></details>
              <div className="field"><label htmlFor="c1">6-digit code</label>
                <input id="c1" inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={e => setCode(e.target.value)} autoFocus /></div>
              <button className="btn-primary" disabled={busy || !codeOk} aria-busy={busy}>{verifying ? 'Verifying…' : 'Verify and sign in'}</button>
            </form>
          )}

          {step.kind === 'totpCode' && (
            <form className="ops-form" onSubmit={submitCode}>
              <p className="muted">Enter the 6-digit code from your authenticator app.</p>
              <div className="field"><label htmlFor="c2">6-digit code</label>
                <input id="c2" inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={e => setCode(e.target.value)} autoFocus /></div>
              <button className="btn-primary" disabled={busy || !codeOk} aria-busy={busy}>{verifying ? 'Verifying…' : 'Verify'}</button>
            </form>
          )}

          {verifying && <p className="muted" role="status">Verifying your account…</p>}
          {err && <p className="ops-msg-err" role="alert">{err}</p>}
          {step.kind !== 'credentials' && (
            <button className="btn-ghost-sm" onClick={() => { setStep({ kind: 'credentials' }); setErr('') }}>Start over</button>
          )}
        </div>
      </div>
    </main>
  )
}
