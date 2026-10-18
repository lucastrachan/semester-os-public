// Class group chats (ROOMS_API.md). Enrollment is NOT verified: always say "classmates who added this class".
export interface Room {
  id: string; code: string; displayCode: string; title: string; term: string
  campus: { id: string; shortName: string }; verified: false
  memberCount: number; muted: boolean; left: boolean; closed: boolean; canSend: boolean
  lastMessage: { from: 'me' | 'them'; name: string; text: string; at: string } | null
  unread: number; lastMessageAt: string | null
}
export interface RoomMessage { id: string; from: 'me' | 'them'; name: string; text: string; at: string; avatar?: string; userId?: string }

export const ROOM_NOTICE = 'Class chats: classmates who added this class. Be kind, share no personal info. Enrollment is not verified.'
export const normCode = (c: string) => c.toUpperCase().replace(/[^A-Z0-9]/g, '')

/** Mirror of the server's rules so the composer can explain a rejection before sending (the server still decides). */
export function messageProblem(text: string): string {
  const t = text.trim()
  if (!t) return ''
  if (t.length > 500) return 'Keep it under 500 characters.'
  if (/https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|org|edu|io|co|me|ly)\b/i.test(t)) return "Links aren't allowed in class chats."
  if (/[@<>]/.test(t)) return "Please leave out @, < and > (no mentions, emails or markup)."
  if (/\d{7,}/.test(t.replace(/\d{4}-\d{2}-\d{2}/g, ''))) return "Please don't share phone numbers or ID numbers."
  return ''
}

export function dayLabel(iso: string, now = new Date()): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((start(now) - start(d)) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}
export const timeOf = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) }
