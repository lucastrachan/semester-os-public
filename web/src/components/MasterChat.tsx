import { useEffect, useRef, useState } from 'react'
import { Link, useMatch, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { askMaster, type MasterReply } from '../lib/master'
import { EMPTY_REPLY, failText, loadTurns, saveTurns, TutorError } from '../lib/tutor'
import { fetchHistory } from '../lib/history'
import { classIndexFromHex } from '../styles/color'
import { applyClassTheme } from '../styles/theme'
import type { Course } from '../lib/api'
import { useToast } from './Toast'
import Robot from './Robot'
import { SourcesLine } from './BbSources'
import { FetchStatus, useFetchFlow } from './FetchFlow'

/** The server's one-line "Getting X from Blackboard, one moment." bubble: the progress card takes its place while the fetch runs, and it is never left behind as the last thing. */
const GETTING_RE = /^Getting ["“].*["”] from Blackboard, one moment\.?$/
interface Msg {
  role: 'user' | 'assistant'
  content: string
  from?: string                       // label for handoff answers, e.g. "MIS 405 tutor"
  handoff?: MasterReply['handoff']
  clarify?: MasterReply['clarify']
  undone?: boolean
  sources?: { materialId?: string; title: string; url?: string; path?: string }[]
}
const KEY = 'chat:master'

/** Chief of Staff chat with routing. A handoff shows a banner with Undo and re-themes the whole UI to the class colour. */
export default function MasterChat({ courses, onNavigate, autoFocus }: { courses: Course[]; onNavigate?: () => void; autoFocus?: boolean }) {
  const { authFetch, tenant } = useAuth()
  const { push } = useToast()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const campus = tenant?.theme?.primary
  const navigate = useNavigate()
  const here = useMatch('/study/:id')?.params.id // the class agent page we are already on, if any
  const navTimer = useRef<number | undefined>(undefined)
  const onNavRef = useRef(onNavigate)
  onNavRef.current = onNavigate
  const [msgs, setMsgs] = useState<Msg[]>(() => loadTurns<Msg>(KEY))
  const [text, setText] = useState('')
  const [pending, setPending] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [reconnecting, setReconnecting] = useState(false)
  useEffect(() => { const f = () => setReconnecting(true); window.addEventListener('sos:reconnecting', f); return () => window.removeEventListener('sos:reconnecting', f) }, [])
  useEffect(() => { if (!pending) setReconnecting(false) }, [pending])
  const inflight = useRef(false) // guards double submits; never persisted, so a fresh mount always starts clear
  const [problem, setProblem] = useState<null | { message: string; text: string; target?: string; base: Msg[] }>(null)
  const logEnd = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  const [serverHistory, setServerHistory] = useState(false)
  // Server history replaces the sessionStorage fallback once the route answers.
  useEffect(() => {
    let alive = true
    ;(async () => {
      const h = await fetchHistory(fetchRef.current, '/chat/master/history')
      if (!alive || !h) return
      setServerHistory(true)
      setMsgs(h.messages.map(m => ({
        role: m.role, content: m.content, sources: m.sources,
        handoff: m.handoff ? { ...m.handoff, confidence: 1 } : null,
        from: m.handoff ? `${m.handoff.courseCode || 'Class'} agent` : undefined,
      })))
    })()
    return () => { alive = false }
  }, [])
  useEffect(() => { if (!serverHistory) saveTurns(KEY, msgs) }, [msgs, serverHistory])
  useEffect(() => { logEnd.current?.scrollIntoView?.({ block: 'end' }) }, [msgs, pending])
  useEffect(() => { if (autoFocus) input.current?.focus() }, [autoFocus])
  useEffect(() => {
    if (cooldown <= 0) return
    const t = window.setTimeout(() => setCooldown(c => c - 1), 1000)
    return () => window.clearTimeout(t)
  }, [cooldown])
  // Leaving the chat always returns to the campus theme.
  useEffect(() => () => applyClassTheme(null, campus), [campus])
  const themeTimer = useRef<number | undefined>(undefined)
  useEffect(() => () => { window.clearTimeout(navTimer.current); window.clearTimeout(themeTimer.current) }, [])

  const themeIdx = (courseId: string) => { const i = themeFor(courseId); return i >= 0 ? `c${i}` : undefined }
  const themeFor = (courseId: string) => {
    const c = courses.find(x => x.id === courseId)
    return c ? classIndexFromHex(c.color) : -1
  }

  // On-demand fetch from Blackboard (same flow as the class chat): the server's fetchSuggestion starts it, the card shows at once, then the question is asked once more.
  const reasking = useRef(false)
  const flow = useFetchFlow({
    reask: (q, base) => { reasking.current = true; void send(q, undefined, base as Msg[]) },
    resend: (q, base) => { void send(q, undefined, base as Msg[]) },
  })

  function applyReply(base: Msg[], res: MasterReply) {
    // Already inside that class agent: just answer, no "switch" banner or button.
    const sameClass = !!res.handoff && res.handoff.courseId === here
    const m: Msg = { role: 'assistant', content: res.reply, handoff: sameClass ? null : res.handoff, clarify: res.clarify, sources: res.sources }
    if (res.handoff && !sameClass) {
      m.from = `${res.handoff.courseCode || 'Class'} agent`
      const idx = themeFor(res.handoff.courseId)
      window.clearTimeout(themeTimer.current)
      if (idx >= 0) themeTimer.current = window.setTimeout(() => applyClassTheme(idx, campus), 1200) // let the banner land, then re-theme (cancelled if we leave)
      // Then open that class in Study so the nav shows where we are. Undo cancels this.
      const to = res.handoff.courseId
      window.clearTimeout(navTimer.current)
      navTimer.current = window.setTimeout(() => { navigate(`/study/${to}`); onNavRef.current?.() }, 2600)
    }
    setMsgs([...base, m])
    if (res.actions.length) push('success', 'Your tutor updated something', res.actions.map(a => a.summary).join('; '))
  }

  async function send(content: string, target?: string, baseMsgs?: Msg[]) {
    const clean = content.trim()
    if (!clean || inflight.current || cooldown > 0) return
    inflight.current = true
    setProblem(null)
    const base = baseMsgs ?? [...msgs, { role: 'user' as const, content: clean }]
    setMsgs(base)
    setText('')
    setPending(true)
    try {
      const res = await askMaster(fetchRef.current, base.map(m => ({ role: m.role, content: m.content })), target)
      if (!(res.reply ?? '').trim()) throw new TutorError(EMPTY_REPLY)
      applyReply(base, res)
      if (reasking.current) flow.finish() // the real answer arrived: the status card goes away
      else if (flow.suggest(res.fetchSuggestion, clean, base, res.handoff?.courseId ?? res.courseId ?? here)) window.clearTimeout(navTimer.current) // stay here and show the progress instead of leaving the page
      reasking.current = false
    } catch (e) {
      if (reasking.current) { reasking.current = false; setMsgs(base); flow.noAnswer(); return } // the re-ask failed: one red row, never silence
      const err = e instanceof TutorError ? e : new TutorError('something went wrong')
      setProblem({ message: failText(err), text: clean, target, base })
      if (err.retryAfter) setCooldown(Math.min(err.retryAfter, 120))
      setMsgs(base.slice(0, -1)); setText(clean)
    } finally { inflight.current = false; setPending(false) }
  }

  async function undoHandoff(index: number) {
    // Client-side undo: back to the campus theme, re-ask the same question with the master as target.
    window.clearTimeout(navTimer.current); window.clearTimeout(themeTimer.current)
    applyClassTheme(null, campus)
    const question = msgs.slice(0, index).reverse().find(m => m.role === 'user')
    const before = msgs.slice(0, index)
    if (question) await send(question.content, 'master', before)
  }

  const last = msgs[msgs.length - 1]

  return (
    <div className="window chat">
      <div className="chat-log" role="log" aria-live="polite" aria-label="Chief of Staff conversation">
        {/* UI-only greeting: always the first bubble, never stored and never sent to the model */}
        <div className="msg msg-agent">Hi, I'm your Chief of Staff. How can I help?</div>
        {msgs.map((m, i) => (m.role === 'assistant' && i === msgs.length - 1 && GETTING_RE.test(m.content.trim())) ? null : (
          <div key={i} className="stack" style={{ gap: 'var(--s-2)', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            {m.handoff && !m.undone && m.handoff.courseId !== here && (
              <div className="handoff-banner" role="status" data-theme={themeIdx(m.handoff.courseId)}>
                <Robot name="class-tutor" size={40} />
                <div className="grow">
                  <div>Switched to your <strong>{m.handoff.courseCode} agent</strong>. Opening it in Study…</div>
                  <div className="muted" style={{ fontSize: 'var(--text-sm)' }}>{m.handoff.reason}</div>
                  {(m.handoff.materials ?? []).length > 0 && (
                    <div className="chip-row" style={{ marginTop: 'var(--s-2)' }} aria-label="Material it will use">
                      {m.handoff.materials!.slice(0, 4).map(x => <span key={x.id} className="chip">Using: {x.title}</span>)}
                    </div>
                  )}
                </div>
                {i === msgs.length - 1 && <button type="button" className="btn-ghost-sm" onClick={() => undoHandoff(i)}>Undo</button>}
              </div>
            )}
            <div className={`msg ${m.role === 'user' ? 'msg-user' : 'msg-agent'}`}>
              {m.from && <div className="msg-meta">{m.from}</div>}
              {m.content /* plain text only */}
              <SourcesLine sources={m.sources} />
              {m.handoff && m.handoff.courseId !== here && (
                <div className="msg-actions">
                  <Link to={`/study/${m.handoff.courseId}`} className="btn-ghost btn-sm" onClick={onNavigate}>Open {m.handoff.courseCode} agent</Link>
                </div>
              )}
            </div>
            {m.clarify && i === msgs.length - 1 && (
              <div className="chip-row" role="group" aria-label="Choose one">
                {m.clarify.options.map(o => {
                  const q = msgs.slice(0, i).reverse().find(x => x.role === 'user')
                  return <button key={o.target} type="button" className="btn-ghost btn-sm" disabled={pending || !q} onClick={() => q && send(q.content, o.target, msgs.slice(0, i))}>{o.label}</button>
                })}
              </div>
            )}
          </div>
        ))}
        {pending && <div className="msg msg-agent" aria-label="Typing"><span className="typing"><i /><i /><i /></span>{reconnecting && <span className="muted"> Reconnecting…</span>}</div>}
        <FetchStatus flow={flow} />
        {problem && !pending && <div className="fail-row" role="alert"><span>{problem.message}</span><button type="button" className="btn-ghost-sm" onClick={() => send(problem.text, problem.target, problem.base)}>Retry</button></div>}
        <div ref={logEnd} />
      </div>
      <form className="chat-composer" onSubmit={e => { e.preventDefault(); send(text) }}>
        <input ref={input} aria-label="Message the Chief of Staff" value={text} maxLength={4000} onChange={e => setText(e.target.value)}
          placeholder={cooldown > 0 ? `Try again in ${cooldown}s` : last?.clarify ? 'Or type your answer…' : 'Ask your Chief of Staff…'} />
        <button type="submit" className="btn-primary" disabled={pending || cooldown > 0 || !text.trim()} aria-busy={pending}>Send</button>
      </form>
    </div>
  )
}
