import { errorMessage } from './api'

export const ARCHIVE_CONFIRM = 'Hide this class? You can restore it any time in Settings.'

/** PATCH /courses/{id} {archived}. Returns null on success, or a friendly problem. */
export async function setArchived(authFetch: (p: string, i?: RequestInit) => Promise<Response>, id: string, archived: boolean): Promise<string | null> {
  try {
    const r = await authFetch(`/courses/${id}`, { method: 'PATCH', body: JSON.stringify({ archived }) })
    if (!r.ok) return await errorMessage(r, archived ? "We couldn't archive the class. Try again." : "We couldn't restore the class. Try again.")
    return null
  } catch { return 'Network problem. Try again.' }
}
