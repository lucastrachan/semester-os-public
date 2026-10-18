// Tutor network layer (TUTOR_API.md). USE_MOCK stays available until POST /courses/{id}/chat is deployed:
// set EXPO_PUBLIC_TUTOR_MOCK=1 to use local sample data. Default is the real endpoint.
import type { Api } from 'shared/api'
import { ApiError } from 'shared/api'
import type { ChatRequest, ChatResponse } from 'shared/types'

export const USE_MOCK = process.env.EXPO_PUBLIC_TUTOR_MOCK === '1'

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

function mock(req: ChatRequest): ChatResponse {
  const base: ChatResponse = { mode: req.mode, reply: '', actions: [], quiz: null, flashcards: null, handoff: null }
  const last = req.messages[req.messages.length - 1]?.content ?? ''
  if (req.mode === 'quiz') {
    return { ...base, reply: 'Here is a short quiz.', quiz: { questions: [
      { id: 'q1', type: 'mc', question: 'Which document tells you the late-work policy?', choices: ['The syllabus', 'The campus map', 'A textbook index', 'Your email signature'], answerIndex: 0, explanation: 'The syllabus is the class contract.' },
      { id: 'q2', type: 'short', question: 'Why do spaced study sessions beat one long cram?', answer: 'Recall after a gap strengthens memory.', explanation: 'Retrieval after forgetting a little builds durable memory.' },
    ] } }
  }
  if (req.mode === 'flashcards') {
    return { ...base, reply: 'Here are your cards.', flashcards: { cards: [
      { front: 'Retrieval practice', back: 'Testing yourself instead of re-reading.' },
      { front: 'Weighted grade', back: 'Score times weight, summed across items.' },
    ] } }
  }
  if (req.mode === 'cram') {
    if (/calendar|yes/i.test(last)) return { ...base, reply: 'Done. I added the study blocks.', actions: [{ id: 'mockact1', kind: 'study_blocks_created', summary: 'Added 3 study blocks', undoable: true }] }
    return { ...base, reply: 'Plan:\n- Mon 7 PM: review chapters 4-5\n- Tue 7 PM: practice problems\n- Wed 6 PM: flashcards, then sleep early' }
  }
  return { ...base, reply: "Let's work through it together. What do you already know about this, and where does it get fuzzy?" }
}

export async function sendChat(api: Api, courseId: string, req: ChatRequest): Promise<ChatResponse> {
  if (USE_MOCK) { await wait(900); return mock(req) }
  return api.chat(courseId, req)
}

export async function undoAction(api: Api, courseId: string, actionId: string): Promise<void> {
  if (USE_MOCK) { await wait(400); return }
  await api.chatUndo(courseId, actionId)
}

/** Student-readable text for a failed tutor call (TUTOR_API.md error table). */
export function tutorError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case 'not_ready': return 'Your tutor is still being built.'
      case 'not_found': return 'Class not found.'
      case 'bad_model_output': return "I couldn't make that. Try again."
      case 'tutor_busy': return 'The tutor is busy. Try again in a few seconds.'
      case 'rate_limited': case 'ai_disabled': case 'too_large': case 'validation_error': return e.message
      case 'network': return e.message
    }
    if (e.status === 404 || e.status === 403) return 'The tutor is not available yet. Check back soon.'
  }
  return 'Something went wrong. Try again.'
}

/** Light markdown to plain text: drop bold/code/heading markers. Output is always rendered in <Text>, never HTML. */
export const plain = (s: string) => s.replace(/\*\*(.+?)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1').replace(/^#{1,6}\s+/gm, '')
