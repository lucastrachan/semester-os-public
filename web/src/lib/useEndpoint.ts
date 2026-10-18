import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'

export type EndpointState = 'loading' | 'ok' | 'unavailable' | 'error'

/**
 * GET a JSON endpoint defensively. "unavailable" means the route isn't deployed yet (404/403/405/501),
 * which the UI shows as a calm "coming soon" state, not as an error.
 */
export function useEndpoint<T>(path: string | null) {
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [data, setData] = useState<T | null>(null)
  const [state, setState] = useState<EndpointState>('loading')

  const load = useCallback(async () => {
    if (!path) return
    try {
      const r = await fetchRef.current(path)
      if ([403, 404, 405, 501].includes(r.status)) { setState('unavailable'); return }
      if (!r.ok) throw new Error(String(r.status))
      setData((await r.json()) as T)
      setState('ok')
    } catch { setState('error') }
  }, [path])

  useEffect(() => { if (user && path) { setState('loading'); load() } }, [user, path, load])
  return { data, state, reload: load, setData }
}
