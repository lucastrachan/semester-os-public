// API response types. Mirrors API.md (Builder owns the contract). Only fields documented there are required;
// everything planned-but-not-live is optional or left out until it ships.

export interface TenantTheme { primary: string; accent?: string; ink?: string }

export interface Tenant {
  id: string
  name: string
  shortName: string
  domains: string[]
  theme: TenantTheme
  timezone: string
  lms?: { type: string; connector: string }
  tutoringResources?: { name: string; description: string; url: string }[]
  pickupSpots?: string[]
  categories?: string[]
  openToNetwork?: boolean
  autoCreated?: boolean
  /** 'verified' | 'autodetected' | 'needs_review' | 'placeholder' (AUTO_CAMPUS.md v2) */
  colorStatus?: string
  createdAt?: string
}

export interface Profile {
  sub: string
  email: string
  tenantId: string
  displayName: string
  calToken: string // secret: never log
  prefs: { wakeHour: number; sleepHour: number; studyBlockMinutes: number }
  feed?: unknown
  createdAt?: string
  updatedAt?: string
}

export interface MeResponse { profile: Profile; tenant: Tenant }


export interface ApiErrorBody { error: string; message: string }

// ---- /courses (API.md "Coded, not deployed yet", Phase 2 slice 1) ----
export type CourseStatus = 'BUILDING' | 'READY' | 'ERROR'
export interface PipelineStep {
  key: 'read_syllabus' | 'extract_dates' | 'build_calendar' | 'match_books' | 'tutor_ready'
  label: string
  state: 'pending' | 'running' | 'done' | 'error'
  detail?: string
}
export interface Course {
  id: string
  status: CourseStatus
  color: string
  createdAt?: string
  updatedAt?: string
  pipeline: PipelineStep[]
  courseCode: string
  title: string
  instructor: string
  term: string
  officeHours: string
  summary: string
  meetings: { days: string[]; start: string; end: string; location: string }[]
  books: { title: string; author: string; edition: string; isbn: string; required: boolean; notes: string }[]
  grading: { item: string; percent: number }[]
  policies: { late: string; attendance: string; ai: string; other: string }
  knows: { materialsCount: number; assignmentsCount: number; lastUpdatedAt?: string; lastFeedCheckAt?: string; newItemsCount: number }
  error?: string
}
export interface Assignment {
  id: string
  courseId: string
  title: string
  type: 'exam' | 'quiz' | 'homework' | 'project' | 'paper' | 'reading' | 'study' | 'other'
  /** Joined read-only from the course by GET /assignments (CALENDAR_API.md). */
  courseCode?: string
  courseColor?: string
  endTime?: string | null
  dueDate: string | null
  /** The syllabus's own words for the due date. Older items may lack it. */
  dueText?: string
  /** 'resolved' = worked out in code from other dates: show as estimated. */
  dateSource?: 'stated' | 'resolved' | 'manual' | 'feed' | null
  dueTime: string | null
  weight?: number
  notes: string
  done: boolean
  source: string
  createdAt?: string
  updatedAt?: string
}

/** S3 presigned POST from POST /courses with a filename. Short-lived; never log it. */
export interface PresignedPost { url: string; fields: Record<string, string> }

/** GET /public/resolve?domain= (AUTO_CAMPUS.md; exact shape not yet in API.md, so every field is optional). */
export interface ResolvedSchool { name: string; primary: string; autoCreated?: boolean; colorStatus?: string }

// ---- Tutor (TUTOR_API.md) ----
export type TutorMode = 'explain' | 'quiz' | 'flashcards' | 'cram'
export interface TutorAction {
  id: string
  kind?: 'assignment_updated' | 'assignment_added' | 'study_blocks_created'
  summary: string
  courseId?: string
  undoable?: boolean
}
export interface Source { materialId: string; title: string }
export interface ChatMessage { id: string; role: 'user' | 'assistant'; content: string; actions?: TutorAction[]; sources?: Source[] }
export interface QuizQuestion {
  id?: string
  type?: 'mc' | 'short'
  question: string
  choices?: string[]
  answerIndex?: number
  answer?: string
  explanation: string
}
export interface Flashcard { front: string; back: string }
export interface ChatRequest {
  mode: TutorMode
  messages: { role: 'user' | 'assistant'; content: string }[]
  topic?: string
  count?: number
}
export interface ChatResponse {
  mode: TutorMode
  reply: string
  actions: TutorAction[]
  quiz: { questions: QuizQuestion[] } | null
  flashcards: { cards: Flashcard[] } | null
  sources?: Source[]
  handoff: null | { courseId: string; reason: string }
}

// ---- Master agent (MASTER_API.md) ----
export interface Briefing {
  greeting: string
  classesToday: { courseId: string; time: string; location: string; prep: string[] }[]
  dueSoon: { assignmentId: string; title: string; courseId: string; dueDate: string; hint: string }[]
  priorities: string[]
  warnings: string[]
  suggestedStudyBlocks: { courseId: string; start: string; end: string; focus: string }[]
}
export interface BriefingResponse { date: string; generatedAt: string; source: 'model' | 'computed'; briefing: Briefing }
export interface MasterChatRequest {
  messages: { role: 'user' | 'assistant'; content: string }[]
  target?: string
  mode?: TutorMode
}
export interface ClarifyOption { target: string; label: string }
export interface MasterChatResponse {
  agent: 'master' | 'class'
  courseId: string | null
  reply: string
  actions: TutorAction[]
  quiz?: { questions: QuizQuestion[] } | null
  flashcards?: { cards: Flashcard[] } | null
  sources?: Source[]
  handoff: null | { courseId: string; courseCode: string; title: string; reason: string; confidence: number; materials?: { id: string; title: string }[] }
  clarify: null | { question: string; options: ClarifyOption[] }
}

// ---- Marketplace (MARKETPLACE_API.md) ----
export type ListingCondition = 'New' | 'Like new' | 'Good' | 'Acceptable'
export interface ListingCampus { id: string; name: string; shortName: string; pickupSpots?: string[]; onYourCampus?: boolean }
export interface Listing {
  id: string
  title: string
  author: string
  isbn: string | null
  edition: string
  price: number
  condition: ListingCondition
  category: string
  courseCode: string
  description: string
  pickupSpot: string
  status: 'available' | 'sold' | 'removed'
  flagged: boolean
  demo: boolean
  sellerName: string
  campus: { id: string; name: string; shortName: string }
  onYourCampus: boolean
  mine: boolean
  createdAt?: string
  updatedAt?: string
}
export interface ListingsResponse {
  listings: Listing[]
  campuses: Record<string, ListingCampus>
  campus: ListingCampus
  safety: string
  nextBefore: string | null
}
export interface ListingInput {
  title: string; price: number; condition: ListingCondition; category: string
  author?: string; isbn?: string | null; edition?: string; courseCode?: string; description?: string; pickupSpot?: string
}
export interface BookMatch { matchType: 'isbn' | 'title'; score: number; listing: Listing }
export interface MatchedBook {
  title: string; author: string; edition: string; isbn: string; required: boolean; notes: string
  matches: BookMatch[]; bestPrice: number | null; bestOnYourCampus: number | null
}
export interface BookMatchesResponse {
  courses: { courseId: string; courseCode: string; title: string; color: string; books: MatchedBook[] }[]
  campuses: Record<string, ListingCampus>
  pickupSpots: string[]
}
export type ReportReason = 'spam' | 'scam' | 'prohibited' | 'wrong_info' | 'other'

// ---- History / opening (HISTORY_API.md) ----
export interface HistoryMessage {
  id: string; role: 'user' | 'assistant'; content: string; mode?: TutorMode
  actions?: TutorAction[]; sources?: Source[]; at?: string
}
export interface Opening { message: string; chips: { label: string; prompt: string; mode: TutorMode }[] }

// ---- Memory (MEMORY_API.md) ----
export interface MemoryNote { id: string; text: string; createdAt?: string; source?: string }

// ---- Materials (MATERIALS_API.md) ----
export interface Material {
  id: string; title: string; filename?: string; kind?: string
  status: 'processing' | 'ready' | 'error'
  summary: string; pages?: number | null; error?: string; addedAt?: string
}

// ---- Blackboard feed (FEED_API.md) ----
export interface FeedSuggestion { courseId: string; courseCode: string; confidence: number }
export interface UnassignedItem {
  uid: string; title: string; description?: string; categories?: string[]
  dueDate: string | null; dueTime: string | null; allDay?: boolean; type?: string
  suggestions: FeedSuggestion[]
}
export interface FeedStats {
  lastCheckedAt: string | null
  lastStatus: 'never' | 'ok' | 'unchanged' | 'changed' | 'error'
  lastError: null | { code: string; message: string }
  newItemsCount: number; unassignedCount: number; itemCount: number; syncCooldownSeconds: number
}
export interface ClassFeed {
  connected: boolean
  stats: FeedStats | null
  items: { uid: string; assignmentId: string; title: string; type: string; dueDate: string | null; dueTime: string | null; isNew: boolean; removedFromFeed: boolean }[]
  unassigned: UnassignedItem[]
}
export interface MeFeed {
  connected: boolean
  urlMasked?: string
  lastCheckedAt?: string | null
  lastStatus?: FeedStats['lastStatus']
  lastError?: null | { code: string; message: string }
  counts?: { events: number; matched: number; unassigned: number; newSinceSeen: number }
  syncCooldownSeconds?: number
}
