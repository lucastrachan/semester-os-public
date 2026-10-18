// Chat history + opening message (HISTORY_API.md). Routes may not be deployed yet: callers fall back gracefully.
import type { TutorAction } from './tutor'

export interface HistMsg {
  id: string
  role: 'user' | 'assistant'
  content: string
  mode?: 'explain' | 'quiz' | 'flashcards' | 'cram'
  actions?: TutorAction[]
  sources?: { materialId?: string; title: string; url?: string; path?: string }[]
  handoff?: { courseId: string; courseCode: string; title: string; reason: string; materials?: { id: string; title: string }[] } | null
  at?: string
}
export interface HistoryPage { messages: HistMsg[]; nextBefore: string | null }
export interface Opening { message: string; chips: { label: string; prompt: string; mode: 'explain' | 'quiz' | 'flashcards' | 'cram' }[] }

type AuthFetch = (path: string, init?: RequestInit) => Promise<Response>

/** null = the route isn't available (not deployed, or any failure): keep the local fallback. */
export async function fetchHistory(authFetch: AuthFetch, path: string, before?: string): Promise<HistoryPage | null> {
  try {
    const r = await authFetch(`${path}?limit=50${before ? `&before=${encodeURIComponent(before)}` : ''}`)
    if (!r.ok) return null
    const j = await r.json()
    if (!Array.isArray(j.messages)) return null
    return { messages: j.messages, nextBefore: typeof j.nextBefore === 'string' ? j.nextBefore : null }
  } catch { return null }
}

export async function fetchOpening(authFetch: AuthFetch, courseId: string): Promise<Opening | null> {
  try {
    const r = await authFetch(`/courses/${courseId}/opening`)
    if (!r.ok) return null
    const j = await r.json()
    if (typeof j.message !== 'string' || !Array.isArray(j.chips)) return null
    const chips = j.chips
      .filter((c: Opening['chips'][number]) => c && typeof c.label === 'string' && typeof c.prompt === 'string' && ['explain', 'quiz', 'flashcards', 'cram'].includes(c.mode))
      .slice(0, 5)
    return { message: j.message, chips }
  } catch { return null }
}
