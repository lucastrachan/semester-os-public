// Assignment loading for the Calendar tab. Uses GET /assignments (CALENDAR_API.md) and, until that route is
// deployed, falls back to GET /courses + GET /courses/{id} (already live) so the tab works either way.
import type { Api } from 'shared/api'
import { ApiError } from 'shared/api'
import type { Assignment } from 'shared/types'

export async function loadAssignments(api: Api): Promise<Assignment[]> {
  try {
    return await api.listAssignments()
  } catch (e) {
    if (!(e instanceof ApiError) || e.status === 0 || e.status >= 500 || e.status === 401) throw e
  }
  const courses = await api.getCourses()
  const all = await Promise.all(
    courses.filter((c) => c.status === 'READY').map(async (c) => {
      const r = await api.getCourse(c.id)
      return r.assignments.map((a) => ({ ...a, courseCode: c.courseCode || c.title, courseColor: c.color }))
    }),
  )
  return all.flat().sort((a, b) => (a.dueDate ?? '9999').localeCompare(b.dueDate ?? '9999') || (a.dueTime ?? '').localeCompare(b.dueTime ?? ''))
}

export const todayKey = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function dayLabel(key: string): string {
  const today = todayKey()
  const d = new Date(`${key}T00:00:00`)
  const t = new Date(`${today}T00:00:00`)
  const diff = Math.round((d.getTime() - t.getTime()) / 86400000)
  const base = d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
  return diff === 0 ? `Today, ${base}` : diff === 1 ? `Tomorrow, ${base}` : diff < 0 ? `Overdue, ${base}` : base
}

export const timeLabel = (a: Assignment) => (a.dueTime ? a.dueTime : 'All day')
