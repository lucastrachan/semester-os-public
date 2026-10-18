// Shared API types and small helpers (shapes from API.md, MASTER_API.md). Model/user text is only ever rendered as text.
export type PipelineState = 'pending' | 'running' | 'done' | 'error'
export interface PipelineStep { key: string; label: string; state: PipelineState; detail?: string }

export interface Course {
  id: string
  status: 'BUILDING' | 'READY' | 'ERROR'
  color: string
  pipeline: PipelineStep[]
  courseCode: string
  title: string
  instructor: string
  term: string
  summary: string
  knows?: { materialsCount?: number; assignmentsCount?: number; newItemsCount?: number }
  error?: string
  needsSyllabus?: boolean
  archived?: boolean
  archivedAt?: string
  source?: string
}

export interface SystemAgent {
  id: string
  kind: 'master' | 'class' | 'system'
  name: string
  role: string
  status: string
  detail: string
}

export interface ActivityItem { id: string; agentId: string; kind: string; text: string; at: string }

/** Human message from an API error body, never raw server text beyond the documented `message`. */
export async function errorMessage(r: Response, fallback = 'Something went wrong. Please try again.'): Promise<string> {
  // API Gateway answers an expired token with {"message":"Unauthorized"}: never show that raw word.
  if (r.status === 401) return 'Your session expired. Please sign in again.'
  try {
    const j = await r.json()
    if (j && typeof j.message === 'string' && j.message.length < 300) return j.message
  } catch { /* fall through */ }
  if (r.status === 429) return 'Too many requests right now. Wait a moment and try again.'
  if (r.status === 401) return 'Your session expired. Please sign in again.'
  return fallback
}

export function timeAgo(iso: string, now = Date.now()): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
