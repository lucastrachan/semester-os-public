import { createContext, useContext, useEffect, useRef, useState, ReactNode } from 'react'
import { getCurrentUser, fetchAuthSession, signOut as amplifySignOut } from 'aws-amplify/auth'
import { applyCampusTheme } from '../styles/theme'

interface User { sub: string; email: string }

interface AuthState {
  loading: boolean
  user: User | null
  token: string | null
  tenant: any | null
  profile: any | null
}

interface AuthContextValue extends AuthState {
  refresh: () => Promise<void>
  signOut: () => Promise<void>
  setProfile: (p: any, t: any) => void
  authFetch: (path: string, init?: RequestInit) => Promise<Response>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    loading: true, user: null, token: null, tenant: null, profile: null,
  })

  const cfg = () => (window as any).__config
  const stateRef = useRef(state)
  stateRef.current = state

  async function refresh() {
    try {
      const cu = await getCurrentUser()
      const session = await fetchAuthSession()
      const token = session.tokens?.idToken?.toString() ?? null
      setState(s => ({
        ...s,
        loading: false,
        user: { sub: cu.userId, email: cu.signInDetails?.loginId ?? '' },
        token,
      }))
    } catch {
      setState({ loading: false, user: null, token: null, tenant: null, profile: null })
    }
  }

  useEffect(() => { refresh() }, [])

  async function signOut() {
    await amplifySignOut()
    setState({ loading: false, user: null, token: null, tenant: null, profile: null })
    applyCampusTheme(undefined)
  }

  function setProfile(profile: any, tenant: any) {
    setState(s => ({ ...s, profile, tenant }))
    applyCampusTheme(tenant?.theme?.primary)
  }

  /** A usable ID token. Amplify refreshes expired tokens itself; we also refresh when under 5 minutes are left, or when forced. */
  async function freshToken(force = false): Promise<string | null> {
    let session = await fetchAuthSession({ forceRefresh: force })
    const exp = Number((session.tokens?.idToken?.payload as { exp?: number } | undefined)?.exp ?? 0) * 1000
    if (!force && session.tokens?.idToken && exp && exp - Date.now() < 5 * 60 * 1000) session = await fetchAuthSession({ forceRefresh: true })
    const t = session.tokens?.idToken?.toString() ?? null
    if (t && t !== stateRef.current.token) setState(s => ({ ...s, token: t }))
    return t
  }

  /** The session could not be renewed: sign out quietly and come back to the same page after signing in again. */
  const expiring = useRef(false)
  async function expireSession() {
    if (expiring.current) return
    expiring.current = true
    try { sessionStorage.setItem('sos:return', window.location.pathname + window.location.search) } catch { /* storage unavailable */ }
    try { await amplifySignOut() } catch { /* already signed out */ }
    window.location.assign('/auth?mode=signin&expired=1')
  }

  /** One API client: on a 401 refresh the session and retry ONCE; only if that also fails, sign out with a friendly message. */
  async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
    const call = (token: string | null) => fetch(`${cfg().apiUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init.headers ?? {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
    let token: string | null
    try { token = await freshToken() } catch { token = stateRef.current.token }
    let r: Response
    try { r = await call(token) } catch (err) {
      // An expired token's 401 from the API gateway carries no CORS headers, so the browser reports it as a network error ("Failed to fetch").
      // On an authenticated call that is "maybe expired": renew the session and retry ONCE before giving up (a timeout abort is not retried).
      if (!token || init.signal?.aborted) throw err
      window.dispatchEvent(new CustomEvent('sos:reconnecting'))
      let again: string | null = null
      try { again = await freshToken(true) } catch { again = null }
      if (!again) throw err
      r = await call(again)
      if (r.status === 401) void expireSession()
      return r
    }
    if (r.status === 401 && token) {
      window.dispatchEvent(new CustomEvent('sos:reconnecting')) // chats show "Reconnecting…" while we renew the session
      let again: string | null = null
      try { again = await freshToken(true) } catch { again = null }
      if (again) r = await call(again)
      if (r.status === 401) void expireSession()
    }
    return r
  }

  // Keep tokens fresh: when the tab regains focus and every 10 minutes while the app is open.
  useEffect(() => {
    const keep = () => { if (stateRef.current.user) void freshToken().catch(() => {}) }
    const t = window.setInterval(keep, 10 * 60 * 1000)
    window.addEventListener('focus', keep)
    return () => { window.clearInterval(t); window.removeEventListener('focus', keep) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // A tiny bridge for the browser helper: only when it asks (same window and origin), it gets a FRESH ID token, only back to this origin. Nothing is ever broadcast unprompted.
  useEffect(() => {
    const onMsg = async (e: MessageEvent) => {
      if (e.source !== window || e.origin !== window.location.origin) return
      const d = e.data as { source?: unknown; type?: unknown } | null
      if (!d || d.source !== 'sos-helper' || d.type !== 'getToken') return
      let idToken: string | null = null
      try { idToken = await freshToken() } catch { idToken = null }
      window.postMessage({ source: 'sos-site', type: 'token', idToken }, window.location.origin)
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <AuthContext.Provider value={{ ...state, refresh, signOut, setProfile, authFetch }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be inside AuthProvider')
  return ctx
}
