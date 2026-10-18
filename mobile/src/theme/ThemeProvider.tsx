import { createContext, ReactNode, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { AccessibilityInfo, useColorScheme } from 'react-native'
import { CLASS_PALETTE, deriveTheme, isHex, NEUTRAL_TOKENS, Scheme } from 'shared/tokens'

export interface Theme {
  scheme: Scheme
  bg: string; surface: string; surface2: string; ink: string; muted: string; border: string; borderStrong: string
  accent: string; accentInk: string; accentTint: string; accentStrong: string
  danger: string; success: string
}

const STATUS = {
  light: { danger: '#B42318', success: '#067647' },
  dark: { danger: '#FF8A80', success: '#5FD39A' },
}

export function buildTheme(hex: string | undefined | null, scheme: Scheme): Theme {
  const accent = isHex(hex) ? hex : CLASS_PALETTE[0]
  return { scheme, ...NEUTRAL_TOKENS[scheme], ...deriveTheme(accent, scheme), ...STATUS[scheme] }
}

interface Control {
  /** Set from GET /me: tenant.theme.primary. */
  setCampusColor: (hex: string | null) => void
  /** Set while inside a class (or after a handoff); null returns to the campus colour. */
  setClassColor: (hex: string | null) => void
}

const ThemeCtx = createContext<Theme>(buildTheme(null, 'light'))
const ControlCtx = createContext<Control>({ setCampusColor: () => {}, setClassColor: () => {} })

const hexToRgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
const lerpHex = (a: string, b: string, t: number) =>
  '#' + hexToRgb(a).map((v, i) => Math.round(v + (hexToRgb(b)[i] - v) * t).toString(16).padStart(2, '0')).join('')
const COLOR_KEYS: (keyof Theme)[] = ['accent', 'accentInk', 'accentTint', 'accentStrong']

/** ~350ms colour interpolation of the accent family when the target theme changes (instant under Reduce Motion). */
function useTweenedTheme(target: Theme): Theme {
  const [shown, setShown] = useState(target)
  const shownRef = useRef(target)
  const reduce = useRef(false)
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then((v) => { reduce.current = v }).catch(() => {})
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', (v) => { reduce.current = v })
    return () => sub.remove()
  }, [])
  useEffect(() => {
    const from = shownRef.current
    if (reduce.current || from.scheme !== target.scheme) { shownRef.current = target; setShown(target); return }
    let raf = 0
    const start = Date.now()
    const step = () => {
      const p = Math.min(1, (Date.now() - start) / 350)
      const eased = 1 - (1 - p) * (1 - p)
      const next = { ...target } as Theme
      for (const k of COLOR_KEYS) (next as unknown as Record<string, string>)[k] = lerpHex(from[k] as string, target[k] as string, eased)
      shownRef.current = p >= 1 ? target : next
      setShown(shownRef.current)
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target])
  return shown
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme()
  const scheme: Scheme = system === 'dark' ? 'dark' : 'light'
  const [campus, setCampus] = useState<string | null>(null)
  const [cls, setCls] = useState<string | null>(null)

  const target = useMemo(() => buildTheme(cls ?? campus, scheme), [cls, campus, scheme])
  const theme = useTweenedTheme(target)
  const control = useMemo<Control>(() => ({ setCampusColor: setCampus, setClassColor: setCls }), [])
  return (
    <ControlCtx.Provider value={control}>
      <ThemeCtx.Provider value={theme}>{children}</ThemeCtx.Provider>
    </ControlCtx.Provider>
  )
}

export const useTheme = () => useContext(ThemeCtx)
export const useThemeControl = () => useContext(ControlCtx)

/** Wrap a class's card or row so it uses that class's colour regardless of the screen theme. */
export function ClassTheme({ hex, children }: { hex: string; children: ReactNode }) {
  const outer = useTheme()
  const t = useMemo(() => buildTheme(hex, outer.scheme), [hex, outer.scheme])
  return <ThemeCtx.Provider value={t}>{children}</ThemeCtx.Provider>
}
