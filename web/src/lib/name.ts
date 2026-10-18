/** Real-name helpers. A display name is clean text; an email (or its prefix) is never used as a name. */
const NAME_RE = /^[\p{L}\p{M}][\p{L}\p{M} '’.\-]*$/u

/** One part of a name (first or last): 1-40 characters, letters, spaces, apostrophes, hyphens and periods. */
export function validatePart(raw: string, label: 'first' | 'last'): string | null {
  const v = raw.trim().replace(/\s+/g, ' ')
  if (v.length < 1) return `Please enter your ${label} name.`
  if (v.length > 40) return `Your ${label} name can be up to 40 characters.`
  if (!NAME_RE.test(v)) return 'Use letters, spaces, apostrophes, hyphens and periods only.'
  return null
}

export const cleanName = (raw: string) => raw.trim().replace(/\s+/g, ' ')

/** First word of a full name, or '' when it is missing or looks like an email. */
export function firstName(name?: string | null): string {
  if (!name || name.includes('@')) return ''
  return name.trim().split(/\s+/)[0] ?? ''
}

/** The name to greet: profile.firstName, else the first word of a clean displayName, else nothing (never an email). */
export function greetName(profile?: { firstName?: string; displayName?: string } | null): string {
  return (profile?.firstName && !profile.firstName.includes('@') ? profile.firstName.trim() : '') || firstName(profile?.displayName)
}
