import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { createApi, Api, ApiError } from 'shared/api'
import type { MeResponse } from 'shared/types'
import { config } from '../config'
import * as cog from './cognito'

type Status = 'loading' | 'signedOut' | 'signedIn'

interface AuthValue {
  status: Status
  email: string | null
  me: MeResponse | null
  /** True when GET /me returned 403 no_campus. */
  noCampus: boolean
  meError: string | null
  api: Api
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  reloadMe: () => Promise<void>
}

const Ctx = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [email, setEmail] = useState<string | null>(null)
  const [me, setMe] = useState<MeResponse | null>(null)
  const [noCampus, setNoCampus] = useState(false)
  const [meError, setMeError] = useState<string | null>(null)

  const signOutRef = useRef<() => Promise<void>>(async () => {})
  const api = useMemo(
    () =>
      createApi({
        baseUrl: config.apiUrl,
        getToken: cog.getIdToken,
        onUnauthorized: () => { void signOutRef.current() },
      }),
    [],
  )

  const reloadMe = useCallback(async () => {
    setMeError(null)
    try {
      setMe(await api.getMe(Intl.DateTimeFormat().resolvedOptions().timeZone))
      setNoCampus(false)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'no_campus') { setNoCampus(true); setMe(null) }
      else setMeError(e instanceof Error ? e.message : 'Something went wrong.')
    }
  }, [api])

  const signOut = useCallback(async () => {
    await cog.signOut()
    setMe(null); setEmail(null); setNoCampus(false); setMeError(null)
    setStatus('signedOut')
  }, [])
  signOutRef.current = signOut

  useEffect(() => {
    (async () => {
      const e = await cog.restoreSession()
      if (e) { setEmail(e); setStatus('signedIn'); void reloadMe() } else setStatus('signedOut')
    })()
  }, [reloadMe])

  const signIn = useCallback(async (e: string, p: string) => {
    await cog.signIn(e, p)
    setEmail(e); setStatus('signedIn')
    void reloadMe()
  }, [reloadMe])

  const value = useMemo(
    () => ({ status, email, me, noCampus, meError, api, signIn, signOut, reloadMe }),
    [status, email, me, noCampus, meError, api, signIn, signOut, reloadMe],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be inside AuthProvider')
  return v
}
