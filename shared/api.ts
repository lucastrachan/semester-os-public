// Typed fetch wrapper. No React, no React Native. The app passes the base URL and a token getter.
import type { ApiErrorBody, Assignment, BookMatchesResponse, BriefingResponse, Listing, ListingInput, ListingsResponse, ReportReason, ChatRequest, ClassFeed, HistoryMessage, Material, MeFeed, MemoryNote, Opening, UnassignedItem, ChatResponse, MasterChatRequest, MasterChatResponse, Course, MeResponse, PresignedPost, Tenant } from './types'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export interface ApiOptions {
  baseUrl: string
  /** Returns the Cognito ID token (not the access token), or null when signed out. */
  getToken: () => Promise<string | null>
  /** Called on a 401 so the app can sign out. */
  onUnauthorized?: () => void
}

export function createApi({ baseUrl, getToken, onUnauthorized }: ApiOptions) {
  async function request<T>(method: string, path: string, opts: { body?: unknown; auth?: boolean } = {}): Promise<T> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (opts.auth) {
      const token = await getToken()
      if (token) headers.Authorization = `Bearer ${token}`
    }
    let res: Response
    try {
      res = await fetch(`${baseUrl}${path}`, {
        method,
        headers,
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      })
    } catch {
      throw new ApiError(0, 'network', "Can't reach Semester OS. Check your connection and try again.")
    }
    const text = await res.text()
    let data: unknown = null
    try { data = text ? JSON.parse(text) : null } catch { /* non-JSON body */ }
    if (!res.ok) {
      const e = (data ?? {}) as Partial<ApiErrorBody>
      if (res.status === 401) onUnauthorized?.()
      throw new ApiError(res.status, e.error ?? 'error', e.message ?? `Request failed (${res.status})`)
    }
    return data as T
  }

  return {
    getTenants: () => request<{ tenants: Tenant[] }>('GET', '/public/tenants').then((r) => r.tenants),
    getCourses: () => request<{ courses: Course[] }>('GET', '/courses', { auth: true }).then((r) => r.courses),
    getCourse: (id: string) => request<{ course: Course; assignments: Assignment[] }>('GET', `/courses/${id}`, { auth: true }),
    createCourseFromText: (text: string) => request<{ course: Course }>('POST', '/courses', { auth: true, body: { text } }),
    /** Step 1 of PDF upload: makes the class and returns an S3 presigned POST (url + fields). Treat both as secret. */
    createCourseForUpload: (filename: string) =>
      request<{ course: Course; upload: PresignedPost }>('POST', '/courses', {
        auth: true, body: { filename, contentType: 'application/pdf' },
      }),
    chat: (courseId: string, b: ChatRequest) =>
      request<ChatResponse>('POST', `/courses/${courseId}/chat`, { auth: true, body: b }),
    chatUndo: (courseId: string, actionId: string) =>
      request<{ undone: string }>('POST', `/courses/${courseId}/chat/undo`, { auth: true, body: { actionId } }),
    /** CALENDAR_API.md (coded, not deployed at time of writing). */
    listAssignments: () => request<{ assignments: Assignment[] }>('GET', '/assignments?undated=include', { auth: true }).then((r) => r.assignments),
    patchAssignment: (id: string, body: { done?: boolean }) =>
      request<{ assignment: Assignment }>('PATCH', `/assignments/${id}`, { auth: true, body }).then((r) => r.assignment),
    rotateCalendarToken: () =>
      request<{ calToken: string; calendarPath: string }>('POST', '/me/calendar-token/rotate', { auth: true }),
    /** MASTER_API.md (coded, not deployed at time of writing). */
    getBriefing: () => request<BriefingResponse>('GET', '/briefing/today', { auth: true }),
    regenerateBriefing: () => request<BriefingResponse>('POST', '/briefing/regenerate', { auth: true, body: {} }),
    chatMaster: (b: MasterChatRequest) => request<MasterChatResponse>('POST', '/chat/master', { auth: true, body: b }),
    /** MARKETPLACE_API.md (coded, not deployed at time of writing). */
    getListings: (scope: 'campus' | 'network' | 'mine') => request<ListingsResponse>('GET', `/listings?scope=${scope}`, { auth: true }),
    createListing: (b: ListingInput) => request<{ listing: Listing }>('POST', '/listings', { auth: true, body: b }).then((r) => r.listing),
    updateListing: (id: string, b: Partial<ListingInput> & { status?: 'available' | 'sold' | 'removed' }) =>
      request<{ listing: Listing }>('PATCH', `/listings/${id}`, { auth: true, body: b }).then((r) => r.listing),
    reportListing: (id: string, reason: ReportReason, note?: string) =>
      request<{ reported: boolean }>('POST', `/listings/${id}/report`, { auth: true, body: note ? { reason, note } : { reason } }),
    getBookMatches: () => request<BookMatchesResponse>('GET', '/books/matches', { auth: true }),
    /** HISTORY_API.md */
    getHistory: (courseId: string, before?: string) =>
      request<{ messages: HistoryMessage[]; nextBefore: string | null }>('GET', `/courses/${courseId}/chat/history?limit=40${before ? `&before=${encodeURIComponent(before)}` : ''}`, { auth: true }),
    getMasterHistory: () => request<{ messages: HistoryMessage[]; nextBefore: string | null }>('GET', '/chat/master/history?limit=40', { auth: true }),
    getOpening: (courseId: string) => request<Opening>('GET', `/courses/${courseId}/opening`, { auth: true }),
    /** MEMORY_API.md */
    getMemory: (courseId: string) => request<{ notes: MemoryNote[]; limit: number; count: number }>('GET', `/courses/${courseId}/memory`, { auth: true }),
    addMemory: (courseId: string, text: string) => request<{ note: MemoryNote }>('POST', `/courses/${courseId}/memory`, { auth: true, body: { text } }).then((r) => r.note),
    editMemory: (courseId: string, id: string, text: string) => request<{ note: MemoryNote }>('PATCH', `/courses/${courseId}/memory/${id}`, { auth: true, body: { text } }).then((r) => r.note),
    deleteMemory: (courseId: string, id?: string) => request<{ deleted: string | number }>('DELETE', `/courses/${courseId}/memory${id ? `/${id}` : ''}`, { auth: true }),
    /** MATERIALS_API.md */
    getMaterials: (courseId: string) => request<{ materials: Material[]; limit: number; notice?: string }>('GET', `/courses/${courseId}/materials`, { auth: true }),
    createMaterialUpload: (courseId: string, filename: string, contentType: string) =>
      request<{ material: Material; upload: PresignedPost }>('POST', `/courses/${courseId}/materials`, { auth: true, body: { filename, contentType } }),
    deleteMaterial: (courseId: string, id: string) => request<{ deleted: string }>('DELETE', `/courses/${courseId}/materials/${id}`, { auth: true }),
    /** FEED_API.md */
    getMeFeed: () => request<MeFeed>('GET', '/me/feed', { auth: true }),
    putMeFeed: (url: string) => request<MeFeed>('PUT', '/me/feed', { auth: true, body: { url } }),
    deleteMeFeed: () => request<{ connected: false }>('DELETE', '/me/feed', { auth: true }),
    syncMeFeed: () => request<{ status: string; added: number; updated: number; unassigned: number }>('POST', '/me/feed/sync', { auth: true, body: {} }),
    getClassFeed: (courseId: string) => request<ClassFeed>('GET', `/courses/${courseId}/feed`, { auth: true }),
    syncClassFeed: (courseId: string) => request<{ status: string; added: number; updated: number; unassigned: number; stats: ClassFeed['stats'] }>('POST', `/courses/${courseId}/feed/sync`, { auth: true, body: {} }),
    feedSeen: (courseId?: string) => request<{ ok: boolean }>('POST', '/feed/seen', { auth: true, body: courseId ? { courseId } : {} }),
    getUnassigned: () => request<{ unassigned: UnassignedItem[] }>('GET', '/feed/unassigned', { auth: true }).then((r) => r.unassigned),
    assignFeedItem: (uid: string, courseId: string) =>
      request<{ assignment: Assignment; alsoAssigned: number }>('POST', `/feed/unassigned/${uid}/assign`, { auth: true, body: { courseId, remember: true } }),
    dismissFeedItem: (uid: string) => request<{ dismissed: boolean }>('POST', `/feed/unassigned/${uid}/dismiss`, { auth: true, body: {} }),
    deleteCourse: (id: string) => request<{ deleted: string }>('DELETE', `/courses/${id}`, { auth: true }),
    /** POST /me returns the same as GET /me and accepts the device time zone for newly created campuses. */
    getMe: (tz?: string) => request<MeResponse>('POST', '/me', { auth: true, body: tz ? { tz } : {} }),
    /** Raw resolve call. Shape is not documented yet, so callers must parse defensively (see mobile/src/resolve.ts). */
    resolveDomainRaw: (domain: string) => request<unknown>('GET', `/public/resolve?domain=${encodeURIComponent(domain)}`),
  }
}

export type Api = ReturnType<typeof createApi>
