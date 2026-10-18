// Pure colour logic (Designer). NO DOM, NO React, NO React Native imports: safe to share with the Expo app
// (copy or alias this file as shared/tokens.ts). Every theme it derives passes WCAG AA for text on bg, surface and tint.
// web/src/styles/themes.css was generated from this same algorithm.

export type Scheme = 'light' | 'dark'

export const NEUTRALS: Record<Scheme, { bg: string; surface: string; tintMix: number }> = {
  light: { bg: '#F4F5F7', surface: '#FFFFFF', tintMix: 0.11 },
  dark: { bg: '#0B0D11', surface: '#13161C', tintMix: 0.2 },
}
const DARK_INK = '#10131A'
const MIN_CONTRAST = 4.65 // AA is 4.5; small margin for rounding

export const CLASS_PALETTE = [
  '#4F46E5', '#0D9488', '#D97706', '#E11D48', '#059669', '#0284C7', '#7C3AED', '#EA580C',
] as const

const toRgb = (h: string): number[] => {
  const s = h.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16))
}
const toHex = (c: number[]): string =>
  '#' + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('')
const luminance = (h: string): number => {
  const [r, g, b] = toRgb(h).map((v) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
export const contrast = (a: string, b: string): number => {
  const x = luminance(a), y = luminance(b)
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}
const mix = (a: string, b: string, t: number): string => {
  const A = toRgb(a), B = toRgb(b)
  return toHex(A.map((v, i) => v * (1 - t) + B[i] * t))
}

export interface Derived { accent: string; accentInk: string; accentTint: string; accentStrong: string }

export function deriveTheme(accent: string, scheme: Scheme): Derived {
  const n = NEUTRALS[scheme]
  const tint = mix(n.surface, accent, n.tintMix)
  const accentInk = contrast('#FFFFFF', accent) >= contrast(DARK_INK, accent) ? '#FFFFFF' : DARK_INK
  const toward = scheme === 'light' ? '#000000' : '#FFFFFF'
  let strong = accent
  let t = 0
  const ok = (c: string) => [n.bg, n.surface, tint].every((bg) => contrast(c, bg) >= MIN_CONTRAST)
  while (!ok(strong) && t < 1) { t += 0.02; strong = mix(accent, toward, t) }
  return { accent, accentInk, accentTint: tint, accentStrong: strong }
}


/** Neutral surfaces per scheme, so native code can paint the same bg/surface/ink/muted/border as the web. */
export const NEUTRAL_TOKENS: Record<Scheme, { bg: string; surface: string; surface2: string; ink: string; muted: string; border: string; borderStrong: string }> = {
  light: { bg: '#F4F5F7', surface: '#FFFFFF', surface2: '#F9FAFB', ink: '#12151C', muted: '#586071', border: '#DDE0E7', borderStrong: '#B9BFCC' },
  dark: { bg: '#0B0D11', surface: '#13161C', surface2: '#0F1217', ink: '#ECEEF3', muted: '#98A0B0', border: '#262B35', borderStrong: '#4A5160' },
}

/** All 8 class themes for one scheme, indexed like CLASS_PALETTE. */
export const classThemes = (scheme: Scheme): Derived[] => CLASS_PALETTE.map((c) => deriveTheme(c, scheme))

/** Tolerant hex check shared by web and native. */
export const isHex = (h: unknown): h is string => typeof h === 'string' && /^#[0-9a-fA-F]{6}$/.test(h)

/** Map a stored course colour (hex from the palette) to its palette index, or -1. */
export const classIndexFromHex = (hex: string): number =>
  CLASS_PALETTE.findIndex((c) => c.toLowerCase() === String(hex).toLowerCase())

/** ~12 curated campus hues. Each one has white ink >= 4.9:1 and passes the same text-contrast derivation as the class palette
 *  in light and dark. Generated placeholder brand colours for auto-created campuses, NOT a school's real brand. */
export const CAMPUS_PALETTE = [
  '#9E1B32', // crimson
  '#C2410C', // burnt orange
  '#A16207', // gold
  '#4D7C0F', // olive
  '#166534', // forest
  '#0F766E', // teal
  '#0E7490', // cyan
  '#1D4ED8', // blue
  '#1E3A8A', // navy
  '#6D28D9', // violet
  '#A21CAF', // magenta
  '#BE185D', // rose
] as const

const NAME_NOISE = new Set(['the', 'of', 'at', 'and', 'in', 'for', 'university', 'college', 'institute', 'school'])

/** Canonical form so "The University of Alabama" and "Alabama University" hash the same (generic words like university/college/state are dropped so the distinctive part decides). */
export const normalizeSchoolName = (name: string): string =>
  String(name ?? '')
    .toLowerCase()
    .normalize('NFKD').replace(/[̀-ͯ]/g, '') // strip accents
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((w) => w && !NAME_NOISE.has(w))
    .join(' ')

/** Deterministic (FNV-1a 32-bit) school name -> one of CAMPUS_PALETTE. Same input, same colour, on every platform. */
export function autoThemeFromName(name: string): string {
  const s = normalizeSchoolName(name)
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  // avalanche (murmur3 finalizer) so similar names don't land on neighbouring hues
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b) >>> 0
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35) >>> 0
  h ^= h >>> 16
  h >>>= 0
  return CAMPUS_PALETTE[h % CAMPUS_PALETTE.length]
}
