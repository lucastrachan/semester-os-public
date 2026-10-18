// Master agent network layer (MASTER_API.md). EXPO_PUBLIC_MASTER_MOCK=1 switches to local sample data while the
// endpoints are undeployed. Default is the real API.
import type { Api } from 'shared/api'
import { ApiError } from 'shared/api'
import type { BriefingResponse, MasterChatRequest, MasterChatResponse } from 'shared/types'

export const USE_MOCK = process.env.EXPO_PUBLIC_MASTER_MOCK === '1'
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

const MOCK_BRIEFING = (courseId: string): BriefingResponse => ({
  date: '2026-10-17', generatedAt: new Date().toISOString(), source: 'model',
  briefing: {
    greeting: 'Good morning. One class today and a quiz coming up.',
    classesToday: [{ courseId, time: '09:00-09:50', location: 'Room 101', prep: ['Finish the chapter 3 reading'] }],
    dueSoon: [{ assignmentId: 'a1', title: 'Quiz 3', courseId, dueDate: '2026-10-19', hint: 'Review slides 10-20' }],
    priorities: ['Start the lab write-up tonight', 'Review slides for Quiz 3'],
    warnings: ['3 deadlines on Fri Oct 23: Quiz 3, Lab 4, Essay 1'],
    suggestedStudyBlocks: [],
  },
})

export async function getBriefing(api: Api, firstCourseId: string): Promise<BriefingResponse> {
  if (USE_MOCK) { await wait(500); return MOCK_BRIEFING(firstCourseId) }
  return api.getBriefing()
}
export async function regenerate(api: Api, firstCourseId: string): Promise<BriefingResponse> {
  if (USE_MOCK) { await wait(900); return MOCK_BRIEFING(firstCourseId) }
  return api.regenerateBriefing()
}

export async function chat(api: Api, req: MasterChatRequest, courseIds: string[]): Promise<MasterChatResponse> {
  if (!USE_MOCK) return api.chatMaster(req)
  await wait(900)
  const last = req.messages[req.messages.length - 1]?.content ?? ''
  const base = { actions: [], handoff: null, clarify: null }
  if (req.target && req.target !== 'master') return { ...base, agent: 'class', courseId: req.target, reply: 'Happy to help with that. What part is confusing?' }
  const cid = courseIds[0]
  if (cid && /exam|quiz|homework/i.test(last)) {
    return { ...base, agent: 'class', courseId: cid, reply: 'Let us go through it step by step. What have you tried so far?',
      handoff: { courseId: cid, courseCode: 'CLASS', title: 'Your class', reason: 'You asked about coursework', confidence: 0.86 } }
  }
  if (cid && /\bhelp\b/i.test(last)) {
    return { ...base, agent: 'master', courseId: null, reply: 'Is this about your class or about planning your week?',
      clarify: { question: 'Is this about your class or about planning your week?', options: [{ target: cid, label: 'My class' }, { target: 'master', label: 'Planning' }] } }
  }
  return { ...base, agent: 'master', courseId: null, reply: 'Here is how I would plan your week: knock out the nearest deadline first, then block study time for the exam.' }
}

export function masterError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case 'not_ready': return 'That class is still being built.'
      case 'not_found': return 'Class not found.'
      case 'master_busy': return 'Your chief of staff is busy. Try again in a few seconds.'
      case 'bad_model_output': return "I couldn't make that. Try again."
      case 'rate_limited': case 'ai_disabled': case 'too_large': case 'validation_error': case 'network': return e.message
    }
    if (e.status === 404 || e.status === 403) return 'The chief of staff is not available yet. Check back soon.'
  }
  return 'Something went wrong. Try again.'
}
