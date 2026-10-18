import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

/** Loads a GET route and keeps data, error and loading state. Error text is already safe to show. */
export function useLoad<T>(path: string) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    setLoading(true)
    try { setData(await api<T>(path)); setError('') } catch (e: any) { setError(e.message) } finally { setLoading(false) }
  }, [path])
  useEffect(() => { void load() }, [load])
  return { data, error, loading, reload: load, setData }
}

export function ago(iso: string) {
  const m = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`
}
