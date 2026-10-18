import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import type { Course } from './api'

/** Loads the student's classes and polls every 2s while any class is still building. */
export function useCourses() {
  const { authFetch, user } = useAuth()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await fetchRef.current('/courses')
      if (!r.ok) throw new Error(String(r.status))
      const j = await r.json()
      // Archived classes never show up in Study, Today or Calendar (filtered here too in case the server returns them).
      setCourses(Array.isArray(j.courses) ? (j.courses as Course[]).filter(c => !c.archived) : [])
      setError(null)
    } catch {
      setError("We couldn't load your classes. Check your connection and try again.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { if (user) load() }, [user, load])

  const building = courses.some(c => c.status === 'BUILDING')
  useEffect(() => {
    if (!building) return
    const t = window.setTimeout(load, 2000)
    return () => window.clearTimeout(t)
  }, [building, courses, load])

  return { courses, loading, error, reload: load }
}
