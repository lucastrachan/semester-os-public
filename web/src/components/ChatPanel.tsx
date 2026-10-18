import { SourcesLine } from './BbSources'
import { FetchStatus, useFetchFlow } from './FetchFlow'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { fetchHistory } from '../lib/history'
import { callTutor, EMPTY_REPLY, failText, loadTurns, saveTurns, TutorError, undoAction, type TutorAction, type TutorMode } from '../lib/tutor'
import { useToast } from './Toast'

type Source = { materialId?: string; title: string; url?: string; path?: string }
/** The server's one-line "Getting X from Blackboard, one moment." bubble: the progress card takes its place while the fetch runs, and it is never left behind as the last thing. */
const GETTING_RE = /^Getting ["“].*["”] from Blackboard, one moment\.?$/
interface Msg { role: 'user' | 'assistant'; content: string; actions?: TutorAction[]; undone?: string[]; sources?: Source[] }

const CONFIRM_TEXT = 'yes, put those in my calendar'

export default function ChatPanel({ courseId, mode, storageKey, placeholder, intro, onChanged, confirmLabel, agentName, autoSend }: {
  courseId: string; mode: Extract<TutorMode, 'explain' | 'cram'>; storageKey: string
  placeholder: string; intro: string; onChanged: () => void; confirmLabel?: string
  agentName?: string; autoSend?: { id: number; text: string } | null
}) {
  const { authFetch, tenant } = useAuth()
  const { push } = useToast()
  const msgsRef = useRef<Msg[]>([])
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  // sessionStorage is only the fallback while the history route isn't available.
  const [msgs, setMsgs] = useState<Msg[]>(() => loadTurns<Msg>(storageKey))
  const [serverHistory, setServerHistory] = useState(false)
  const [older, setOlder] = useState<string | null>(null)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [text, setText] = useState('')
  const [pending, setPending] = useState(false)
  const inflight = useRef(false)
  const [reconnecting, setReconnecting] = useState(false)
  useEffect(() => { const f = () => setReconnecting(true); window.addEventListener('sos:reconnecting', f); return () => window.removeEventListener('sos:reconnecting', f) }, [])
  useEffect(() => { if (!pending) setReconnecting(false) }, [pending])
  const [problem, setProblem] = useState<null | { message: string; text: string }>(null)
  const [cooldown, setCooldown] = useState(0)
  const logEnd = useRef<HTMLDivElement>(null)

  const fromHistory = (h: Awaited<ReturnType<typeof fetchHistory>>): Msg[] =>
    (h?.messages ?? []).filter(m => m.mode === mode).map(m => ({ role: m.role, content: m.content, actions: m.actions?.filter(a => a.undoable), sources: m.sources }))

  useEffect(() => {
    let alive = true
    ;(async () => {
      const h = await fetchHistory(fetchRef.current, `/courses/${courseId}/chat/history`)
      if (!alive || !h) return
      setServerHistory(true); setOlder(h.nextBefore); setMsgs(fromHistory(h))
    })()
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, mode])

  async function loadOlder() {
    if (!older) return
    setLoadingOlder(true)
    const h = await fetchHistory(fetchRef.current, `/courses/${courseId}/chat/history`, older)
    if (h) { setMsgs(m => [...fromHistory(h), ...m]); setOlder(h.nextBefore) }
    setLoadingOlder(false)
  }

  useEffect(() => { if (!serverHistory) saveTurns(storageKey, msgs) }, [msgs, storageKey, serverHistory])
  useEffect(() => { logEnd.current?.scrollIntoView?.({ block: 'end' }) }, [msgs, pending])
  useEffect(() => {
    if (cooldown <= 0) return
    const t = window.setTimeout(() => setCooldown(c => c - 1), 1000)
    return () => window.clearTimeout(t)
  }, [cooldown])

  // Quick-action chips can ask the chat to send a prompt for the student (once per chip tap).
  const sentAuto = useRef(0)
  useEffect(() => {
    if (autoSend && autoSend.id !== sentAuto.current) { sentAuto.current = autoSend.id; void send(autoSend.text) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSend?.id])

  msgsRef.current = msgs
  // On-demand fetch from Blackboard: the server's fetchSuggestion is the only trigger (shared with the Ask chat).
  const flow = useFetchFlow({
    reask: (q, base) => { void send(q, { auto: true, base: base as Msg[] }) },
    resend: (q, base) => { void send(q, { base: base as Msg[] }) },
  })

  async function send(content: string, opts?: { auto?: boolean; base?: Msg[] }) {
    const clean = content.trim()
    if (!clean || inflight.current || cooldown > 0) return
    inflight.current = true
    setProblem(null)
    const next: Msg[] = opts?.base ?? [...msgsRef.current, { role: 'user', content: clean }]
    setMsgs(next)
    setText('')
    setPending(true)
    try {
      const res = await callTutor(fetchRef.current, courseId, {
        mode, messages: next.map(m => ({ role: m.role, content: m.content })).slice(-20),
      })
      if (!(res.reply ?? '').trim()) {
        if (opts?.auto) { setMsgs(opts.base ?? msgsRef.current); flow.noAnswer(); return }
        throw new TutorError(EMPTY_REPLY)
      }
      setMsgs(m => [...(opts?.base ?? m), { role: 'assistant', content: res.reply, actions: res.actions, sources: res.sources }])
      if (opts?.auto) flow.finish() // the real answer arrived: the status card goes away
      // The server decides: a fetchSuggestion starts the on-demand fetch (card first, then the re-ask). The re-ask itself never starts another.
      if (!opts?.auto) flow.suggest((res as { fetchSuggestion?: { title: string; url: string } | null }).fetchSuggestion, clean, next, courseId)
      if (res.actions.length) onChanged()
    } catch (e) {
      if (opts?.auto) { // the re-ask after a fetch failed: one line, never just a dangling "Getting…"
        setMsgs(opts.base ?? msgsRef.current)
        flow.noAnswer()
        return
      }
      const err = e instanceof TutorError ? e : new TutorError('the tutor ran into a problem')
      setProblem({ message: failText(err), text: clean })
      if (err.retryAfter) setCooldown(Math.min(err.retryAfter, 120))
      setMsgs(next.slice(0, -1)) // drop the unanswered question so it can be re-sent
      setText(clean)
    } finally {
      inflight.current = false
      setPending(false)
    }
  }

  async function undo(index: number, action: TutorAction) {
    try {
      await undoAction(fetchRef.current, courseId, action.id)
      setMsgs(ms => ms.map((m, i) => (i === index ? { ...m, undone: [...(m.undone ?? []), action.id] } : m)))
      push('success', 'Change undone', action.summary)
      onChanged()
    } catch (e) {
      push('error', "Couldn't undo", e instanceof Error ? e.message : 'Try again.')
    }
  }

  const last = msgs[msgs.length - 1]
  const canConfirm = mode === 'cram' && !!confirmLabel && last?.role === 'assistant' && !last.actions?.some(a => a.kind === 'study_blocks_created')

  return (
    <div className="window chat">
      <div className="chat-log" role="log" aria-live="polite" aria-label="Conversation">
        {older && <button type="button" className="btn-ghost btn-sm" style={{ alignSelf: 'center' }} disabled={loadingOlder} aria-busy={loadingOlder} onClick={loadOlder}>Load earlier messages</button>}
        {/* UI-only greeting: always the first bubble, never stored and never sent to the model */}
        {!older && (
          <div className="msg msg-agent">
            {agentName && <div className="msg-meta">{agentName}</div>}
            {intro}
          </div>
        )}
        {msgs.map((m, i) => (m.role === 'assistant' && i === msgs.length - 1 && GETTING_RE.test(m.content.trim())) ? null : (
          <div key={i} className={`msg ${m.role === 'user' ? 'msg-user' : 'msg-agent'}`}>
            {m.content /* plain text only, never HTML */}
            <SourcesLine sources={m.sources} />
            {m.actions && m.actions.length > 0 && (
              <div className="msg-actions chip-row">
                {m.actions.map(a => {
                  const done = m.undone?.includes(a.id)
                  return (
                    <span key={a.id} className="chip chip-action" style={{ whiteSpace: 'normal' }}>
                      {done ? `Undone: ${a.summary}` : a.summary}
                      {a.undoable && !done && (
                        <button type="button" className="btn-ghost-sm" style={{ minHeight: '1.75rem', padding: '0 var(--s-2)' }} onClick={() => undo(i, a)}>Undo</button>
                      )}
                    </span>
                  )
                })}
              </div>
            )}
          </div>
        ))}
        {pending && <div className="msg msg-agent" aria-label="The agent is typing"><span className="typing"><i /><i /><i /></span>{reconnecting && <span className="muted"> Reconnecting…</span>}</div>}
        <FetchStatus flow={flow} />
        {problem && !pending && <div className="fail-row" role="alert"><span>{problem.message}</span><button type="button" className="btn-ghost-sm" onClick={() => send(problem.text)}>Retry</button></div>}
        <div ref={logEnd} />
      </div>
      {canConfirm && (
        <div className="row" style={{ padding: '0 var(--s-4) var(--s-3)' }}>
          <button type="button" className="btn-primary btn-sm" disabled={pending || cooldown > 0} onClick={() => send(CONFIRM_TEXT)}>{confirmLabel}</button>
        </div>
      )}
      <form className="chat-composer" onSubmit={e => { e.preventDefault(); send(text) }}>
        <input aria-label="Message" value={text} maxLength={4000} placeholder={cooldown > 0 ? `Try again in ${cooldown}s` : placeholder} onChange={e => setText(e.target.value)} />
        <button type="submit" className="btn-primary" disabled={pending || cooldown > 0 || !text.trim()} aria-busy={pending}>Send</button>
      </form>
    </div>
  )
}
