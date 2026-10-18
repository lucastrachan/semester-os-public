import { ApiError } from 'shared/api'

/** Student-readable text for any failed call. Never shows raw "Network request failed". */
export function friendly(e: unknown, fallback = 'Something went wrong. Try again.'): string {
  if (e instanceof ApiError) {
    if (e.code === 'network') return e.message
    if (e.status === 429) return e.message || 'Slow down a little and try again in a moment.'
    if (e.status >= 500) return 'Our server had a problem. Try again in a moment.'
    return e.message || fallback
  }
  return fallback
}

/** True when the route is not deployed yet (gateway 404/403): show a calm "not available yet" state instead of an error. */
export const notAvailable = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.status === 403)
