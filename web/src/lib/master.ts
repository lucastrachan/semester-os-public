// Master agent API client (MASTER_API.md). Model text is plain text; ids from the server are only used to look up the student's own classes.
import { errorMessage } from './api'
import { chatRequest, TutorError, type ChatTurn, type TutorAction, type QuizQuestion, type Flashcard } from './tutor'

export interface Briefing {
  greeting: string
  classesToday: { courseId: string; time: string; location?: string; prep?: string[] }[]
  dueSoon: { assignmentId: string; title: string; courseId: string; dueDate: string; hint?: string }[]
  priorities: string[]
  warnings: string[]
  suggestedStudyBlocks: { courseId: string; start: string; end: string; focus?: string }[]
}
export interface BriefingResponse { date: string; generatedAt: string; source: 'model' | 'computed'; briefing: Briefing }

export interface MasterReply {
  agent: 'master' | 'class'
  courseId: string | null
  reply: string
  actions: TutorAction[]
  handoff: { courseId: string; courseCode: string; title: string; reason: string; confidence: number; materials?: { id: string; title: string }[] } | null
  clarify: { question: string; options: { target: string; label: string }[] } | null
  quiz?: { questions: QuizQuestion[] } | null
  flashcards?: { cards: Flashcard[] } | null
  sources?: { materialId?: string; title: string; url?: string; path?: string }[]
  /** The question named a specific item that has not been fetched yet. */
  fetchSuggestion?: { title: string; url: string; path?: string } | null
}

type AuthFetch = (path: string, init?: RequestInit) => Promise<Response>

async function fail(r: Response): Promise<TutorError> {
  const retry = Number(r.headers.get('Retry-After')) || undefined
  let code = ''
  try { code = (await r.clone().json()).error } catch { /* no body */ }
  if (code === 'master_busy') return new TutorError('Your Chief of Staff is busy. Try again in a few seconds.', retry)
  if (code === 'not_ready') return new TutorError('That class is still being built.')
  return new TutorError(await errorMessage(r, 'Something went wrong. Try again.'), retry)
}

export async function getBriefing(authFetch: AuthFetch, regenerate = false): Promise<BriefingResponse> {
  let r: Response
  try {
    r = regenerate
      ? await authFetch('/briefing/regenerate', { method: 'POST', body: '{}' })
      : await authFetch('/briefing/today')
  } catch { throw new TutorError('Network problem. Try again.') }
  if (!r.ok) throw await fail(r)
  return (await r.json()) as BriefingResponse
}

export async function askMaster(authFetch: AuthFetch, messages: ChatTurn[], target?: string): Promise<MasterReply> {
  return chatRequest<MasterReply>(authFetch, '/chat/master', { messages: messages.slice(-20), ...(target ? { target } : {}) }, fail)
}
