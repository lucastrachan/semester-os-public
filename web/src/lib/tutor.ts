// Class tutor API client (TUTOR_API.md). All text from the model is rendered as plain text by the callers.
import { errorMessage } from './api'

export type TutorMode = 'explain' | 'quiz' | 'flashcards' | 'cram'
export interface ChatTurn { role: 'user' | 'assistant'; content: string }
export interface TutorAction { id: string; kind: string; summary: string; courseId: string; undoable: boolean }
export interface QuizQuestion {
  id: string; type: 'mc' | 'short'; question: string
  choices?: string[]; answerIndex?: number; answer?: string; explanation?: string
}
export interface Flashcard { front: string; back: string }
export interface TutorReply {
  mode: TutorMode
  reply: string
  actions: TutorAction[]
  quiz: { questions: QuizQuestion[] } | null
  flashcards: { cards: Flashcard[] } | null
  sources?: { materialId?: string; title: string; url?: string; path?: string }[]
  /** The question named a specific item that has not been fetched yet. */
  fetchSuggestion?: { title: string; url: string; path?: string } | null
}

export class TutorError extends Error {
  retryAfter?: number
  constructor(message: string, retryAfter?: number) { super(message); this.retryAfter = retryAfter }
}

type AuthFetch = (path: string, init?: RequestInit) => Promise<Response>

async function failure(r: Response): Promise<TutorError> {
  const retry = Number(r.headers.get('Retry-After')) || undefined
  let code = ''
  try { code = (await r.clone().json()).error } catch { /* no body */ }
  if (code === 'not_ready') return new TutorError('Your tutor is still being built.')
  if (code === 'tutor_busy') return new TutorError('The tutor is busy. Try again in a few seconds.', retry)
  if (code === 'bad_model_output') return new TutorError("I couldn't make that. Try again.")
  if (r.status === 404) return new TutorError('Class not found.')
  return new TutorError(await errorMessage(r, 'The tutor ran into a problem. Try again.'), retry)
}

/** Every chat failure becomes one specific red message plus a Retry. The reason is logged to the console without any message content. */
export const EMPTY_REPLY = 'EMPTY_REPLY'
export function failText(e: unknown): string {
  const raw = e instanceof TutorError ? e.message : 'something unexpected went wrong'
  // eslint-disable-next-line no-console
  console.warn('[chat] failed:', raw === EMPTY_REPLY ? 'empty reply' : raw)
  if (raw === EMPTY_REPLY) return 'The assistant returned an empty answer. Try again.'
  const known = /network/i.test(raw) ? 'no connection' : /took too long/i.test(raw) ? 'it took too long' : /busy/i.test(raw) ? 'the assistant is busy' : /session expired/i.test(raw) ? 'your session expired, please sign in again' : ''
  const reason = known || raw.replace(/\s*(Please )?try again( in a (moment|few seconds))?\.?$/i, '').replace(/\.$/, '').trim() || 'no reason given'
  return `The assistant didn't answer (${reason.charAt(0).toLowerCase() + reason.slice(1)}). Try again.`
}

export const CHAT_TIMEOUT_MS = 40000
export const TIMEOUT_TEXT = 'That took too long. Try again.'

/** POST a chat call with a hard timeout. Every failure (timeout, network, non-2xx, a body that never arrives) becomes a TutorError, so callers always clear their loading state. */
export async function chatRequest<T>(authFetch: AuthFetch, path: string, body: unknown, onFail: (r: Response) => Promise<TutorError>): Promise<T> {
  const ac = new AbortController()
  const timer = window.setTimeout(() => ac.abort(), CHAT_TIMEOUT_MS)
  try {
    let r: Response
    try { r = await authFetch(path, { method: 'POST', body: JSON.stringify(body), signal: ac.signal }) }
    catch { throw new TutorError(ac.signal.aborted ? TIMEOUT_TEXT : 'Network problem. Check your connection and try again.') }
    if (!r.ok) throw await onFail(r)
    try { return (await r.json()) as T } catch { throw new TutorError(ac.signal.aborted ? TIMEOUT_TEXT : 'The answer got cut off. Try again.') }
  } finally { window.clearTimeout(timer) }
}

export async function callTutor(
  authFetch: AuthFetch, courseId: string,
  body: { mode: TutorMode; messages?: ChatTurn[]; topic?: string; count?: number },
): Promise<TutorReply> {
  return chatRequest<TutorReply>(authFetch, `/courses/${courseId}/chat`, body, failure)
}

export async function undoAction(authFetch: AuthFetch, courseId: string, actionId: string): Promise<void> {
  let r: Response
  try {
    r = await authFetch(`/courses/${courseId}/chat/undo`, { method: 'POST', body: JSON.stringify({ actionId }) })
  } catch {
    throw new TutorError('Network problem. Try again.')
  }
  if (r.ok) return
  let code = ''
  try { code = (await r.clone().json()).error } catch { /* no body */ }
  if (code === 'already_undone') throw new TutorError('That change was already undone.')
  if (code === 'changed_since') throw new TutorError('That item was edited since, so nothing was changed.')
  if (code === 'not_found') throw new TutorError('That change can no longer be undone.')
  throw await failure(r)
}

/** Per-class conversation memory for this browser tab only (the server stores no chat text). */
export function loadTurns<T>(key: string): T[] {
  try { const v = JSON.parse(sessionStorage.getItem(key) ?? '[]'); return Array.isArray(v) ? v : [] } catch { return [] }
}
export function saveTurns<T>(key: string, turns: T[]): void {
  try { sessionStorage.setItem(key, JSON.stringify(turns.slice(-40))) } catch { /* storage unavailable */ }
}
