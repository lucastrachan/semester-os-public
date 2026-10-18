import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { bbUrl, isHelperSeen, KIND_LABEL, linkKind, triedUrls } from './BbSources'

type Phase = 'fetching' | 'asking' | 'noanswer' | 'failed' | 'nohelper'
export interface FetchState { phase: Phase; title: string; href: string; courseId: string; question: string; base: unknown[]; message?: string }
export interface FetchFlow {
  auto: FetchState | null
  step: { line: string; pct: number | null }
  suggest: (fs: { title: string; url: string } | null | undefined, question: string, base: unknown[], courseId: string | null | undefined) => boolean
  finish: () => void
  noAnswer: () => void
  retry: () => void
  dismiss: () => void
}

/** Map the helper's step text to a rough percent. Unknown text keeps the previous value (or an indeterminate bar). */
function stepPct(line: string, prev: number | null): number | null {
  const l = line.toLowerCase()
  if (/think|answering/.test(l)) return 95
  if (/what it says|ready/.test(l)) return 90
  if (/sav|upload/.test(l)) return 75
  if (/read/.test(l)) return 55
  if (/open/.test(l)) return 35
  if (/find/.test(l)) return 15
  return prev
}

/**
 * The on-demand fetch from the page's side, shared by the class chat and the Ask / Today chat.
 * The server's `fetchSuggestion` is the ONLY trigger. Whatever happens, the status ends as the real answer or a red row; it never just stops.
 */
export function useFetchFlow(opts: { reask: (question: string, base: unknown[]) => void; resend: (question: string, base: unknown[]) => void }): FetchFlow {
  const [auto, setAuto] = useState<FetchState | null>(null)
  const [step, setStep] = useState<{ line: string; pct: number | null }>({ line: '', pct: null })
  const autoRef = useRef(auto)
  autoRef.current = auto
  const optsRef = useRef(opts)
  optsRef.current = opts
  const timer = useRef<number | undefined>(undefined)
  const started = useRef(0)
  const gotProgress = useRef(false)

  /** Give up after 20 s of silence or 75 s in total, whichever comes first. */
  const armTimer = useCallback(() => {
    window.clearTimeout(timer.current)
    const left = Math.max(1000, 75000 - (Date.now() - started.current))
    timer.current = window.setTimeout(() => setAuto(a => (a && a.phase === 'fetching' ? { ...a, phase: 'failed', message: gotProgress.current ? 'The helper stopped responding. Try again.' : "The helper didn't respond. Try again." } : a)), Math.min(20000, left))
  }, [])

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.source !== window || e.origin !== window.location.origin) return
      const d = e.data as { source?: unknown; type?: unknown; courseId?: unknown; ok?: unknown; ready?: unknown; phase?: unknown; line?: unknown; percent?: unknown } | null
      const cur = autoRef.current
      if (!cur || cur.phase !== 'fetching' || !d || d.source !== 'blackboard') return
      gotProgress.current = true
      // The fetch can take about a minute: every 'fetch' progress message keeps the wait alive and moves the step line.
      if (d.type === 'progress') {
        if (d.phase === 'fetch') {
          armTimer()
          const line = typeof d.line === 'string' ? d.line.slice(0, 80) : ''
          if (line) setStep(prev => ({ line, pct: stepPct(line, typeof d.percent === 'number' ? d.percent : prev.pct) }))
        }
        return
      }
      if (d.type !== 'fetched' || d.courseId !== cur.courseId) return
      window.clearTimeout(timer.current)
      if (d.ok === true) {
        // The helper has the file. A short moment (none needed when it says ready), then re-ask the same question once.
        setStep({ line: 'Thinking…', pct: 95 })
        setAuto({ ...cur, phase: 'asking' })
        window.setTimeout(() => optsRef.current.reask(cur.question, cur.base), d.ready === true ? 300 : 1500)
      } else {
        // Always a specific reason sentence first: the helper's own line when it is a real sentence, else a plain default.
        const line = typeof d.line === 'string' ? d.line.trim().slice(0, 200) : ''
        setAuto({ ...cur, phase: 'failed', message: line.length >= 8 && !/^open it( in blackboard)?\.?$/i.test(line) ? line : 'The helper could not read this page.' })
      }
    }
    window.addEventListener('message', onMsg)
    return () => { window.removeEventListener('message', onMsg); window.clearTimeout(timer.current) }
  }, [armTimer])

  function startFetch(title: string, href: string, question: string, base: unknown[], courseId: string) {
    triedUrls.add(href)
    // The card shows IMMEDIATELY, before any helper message: an indeterminate-looking start at 15%.
    setAuto({ phase: 'fetching', title, href, courseId, question, base })
    setStep({ line: 'Finding it in your course…', pct: 15 })
    started.current = Date.now()
    gotProgress.current = false
    try { window.postMessage({ source: 'sos-site', type: 'fetch', courseId, url: href }, window.location.origin) }
    catch { setAuto({ phase: 'failed', title, href, courseId, question, base, message: "I couldn't reach the helper. Try again." }); return }
    armTimer()
  }

  const suggest: FetchFlow['suggest'] = (fs, question, base, courseId) => {
    if (!fs || !courseId) return false
    const cur = autoRef.current
    if (cur && (cur.phase === 'fetching' || cur.phase === 'asking')) return true // already working on it
    const href = bbUrl(fs.url)
    if (!href) { setAuto({ phase: 'failed', title: fs.title, href: '', courseId, question, base, message: 'That link is not allowed.' }); return true }
    if (!isHelperSeen()) { setAuto({ phase: 'nohelper', title: fs.title, href, courseId, question, base }); return true }
    startFetch(fs.title, href, question, base, courseId)
    return true
  }

  return {
    auto, step, suggest,
    finish: () => { window.clearTimeout(timer.current); setAuto(null) },
    noAnswer: () => setAuto(a => (a ? { ...a, phase: 'noanswer' } : a)),
    retry: () => { const cur = autoRef.current; if (!cur) return; triedUrls.delete(cur.href); setAuto(null); optsRef.current.resend(cur.question, cur.base) },
    dismiss: () => setAuto(null),
  }
}

/** Renders the fetch card (progress) or the red row (failure). Nothing when idle. */
export function FetchStatus({ flow }: { flow: FetchFlow }) {
  const { tenant } = useAuth()
  const { auto, step } = flow
  if (!auto) return null
  const open = auto.href ? <a className="btn-ghost btn-sm" href={auto.href} target="_blank" rel="noopener noreferrer">{KIND_LABEL[linkKind(auto.href, tenant?.lms?.baseUrl)]}</a> : null
  const actions = <span className="row">{open}<button type="button" className="btn-ghost-sm" onClick={flow.retry}>Retry</button><button type="button" className="btn-ghost-sm" onClick={flow.dismiss}>Dismiss</button></span>
  if (auto.phase === 'fetching' || auto.phase === 'asking') {
    return (
      <div className="fetch-card" role="status" aria-live="polite">
        <strong>Getting {auto.title}</strong>
        <div className={`bar-track${step.pct === null ? ' bar-indet' : ''}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={step.pct ?? undefined} aria-label="Progress"><i style={step.pct === null ? undefined : { width: `${step.pct}%` }} /></div>
        <span className="muted">{step.line || 'Working on it…'}</span>
      </div>
    )
  }
  const text = auto.phase === 'nohelper' ? "I couldn't reach the Semester OS helper. Reload the extension at chrome://extensions, then press F5 on this page and ask again."
    : auto.phase === 'noanswer' ? 'I read it, but could not answer yet. Ask me again in a moment.'
    : auto.message || 'The helper could not read this page.'
  return <div className="fail-row" role="alert"><span>{text}</span>{actions}</div>
}
