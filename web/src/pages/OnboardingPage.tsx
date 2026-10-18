import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { canvasScan, CANVAS_SCAN_LIVE, lmsFromTenant, useLmsChoice, type Lms } from '../lib/lms'
import { useCourses } from '../lib/useCourses'
import { useEndpoint } from '../lib/useEndpoint'
import { classIndexFromHex } from '../styles/color'
import AddClass from '../components/AddClass'
import Robot from '../components/Robot'
import UnassignedInbox from '../components/UnassignedInbox'
import { useToast } from '../components/Toast'
import { NamePrompt } from '../components/NameCard'
import { HelperBadge } from '../components/BbSources'
import { Link as RouterLink } from 'react-router-dom'

interface FeedStatus { connected: boolean; urlMasked?: string; lastCheckedAt?: string | null; counts?: { events: number; matched: number; unassigned: number } }

const OPTIONS: { id: Lms; title: string; blurb: string }[] = [
  { id: 'blackboard', title: 'Blackboard', blurb: 'Use your calendar link for deadlines, plus your syllabi.' },
  { id: 'canvas', title: 'Canvas', blurb: 'Create a personal access token and we find your classes.' },
  { id: 'other', title: 'Something else / not sure', blurb: 'Upload your syllabus PDFs. That works everywhere.' },
]

const NO_PASSWORD = "Semester OS never sees your school password. We only use a calendar link or a token you create yourself, and you can remove them any time in Settings."

export default function OnboardingPage() {
  const { tenant } = useAuth()
  const navigate = useNavigate()
  const preselect = lmsFromTenant(tenant)
  const [lms, setLms] = useState<Lms | null>('blackboard') // Blackboard is the default path
  const chosen = useRef(false)
  // Preselect from the campus once it loads, unless the student already picked.
  useEffect(() => { if (!chosen.current && preselect) setLms(preselect) }, [preselect])
  const pick = (v: Lms) => { chosen.current = true; setLms(v) }
  const [stage, setStage] = useState<'connect' | 'classes' | 'sort'>('connect')
  const [found, setFound] = useState<number | null>(null)

  const step = stage === 'connect' ? 1 : stage === 'classes' ? 2 : 3
  return (
    <div className="page">
      <div className="page-head">
        <span className="eyebrow">Welcome{tenant?.shortName ? ` · ${tenant.shortName}` : ''}</span>
        <h1>{stage === 'connect' ? 'Connect your classes' : stage === 'classes' ? 'Which classes are you taking?' : 'Sort your deadlines into classes'}</h1>
        <p>{stage === 'connect' ? 'The Semester OS browser helper reads your course list and deadlines while you watch, and builds a class agent for each class in one click.' : stage === 'classes' ? 'Add your class codes so your deadlines have somewhere to go. You can add each syllabus later for books, grading and policies.' : 'Blackboard does not say which class each deadline is for. Tap a class for each group.'}</p>
      </div>

      <NamePrompt />

      {stage === 'connect' && (
        <>
          <SystemPicker />
          <HelperPanel tenant={tenant} />

          <details className="mk-safety">
            <summary>Advanced: use a calendar link instead</summary>
            <div className="stack" style={{ marginTop: 'var(--s-3)' }}>
              <p className="muted">The calendar link brings in your deadlines but cannot tell which class each one belongs to, so you sort them yourself afterwards.</p>
              <div className="config-grid" role="radiogroup" aria-label="Which learning system does your school use?">
                {OPTIONS.map(o => (
                  <button key={o.id} type="button" role="radio" aria-checked={lms === o.id} className="config-item" data-state={lms === o.id ? 'set' : 'empty'}
                    style={{ textAlign: 'left', cursor: 'pointer', borderColor: lms === o.id ? 'var(--accent-strong)' : undefined, background: lms === o.id ? 'var(--accent-tint)' : undefined }}
                    onClick={() => pick(o.id)}>
                    <h3>{o.title}{preselect === o.id && <span className="badge">Your school</span>}</h3>
                    <p className="config-value">{o.blurb}</p>
                  </button>
                ))}
              </div>
              {lms === 'blackboard' && <BlackboardPanel onConnected={n => { setFound(n); setStage('classes') }} />}
              {lms === 'canvas' && <CanvasPanel />}
              {lms === 'other' && <p className="muted">No problem. Use "Other ways to add classes" below: each class's agent builds in about a minute.</p>}
            </div>
          </details>

          <details className="mk-safety">
            <summary>Other ways to add classes</summary>
            <div className="stack" style={{ marginTop: 'var(--s-3)' }}>
              <ClassesStep onDone={() => navigate('/study')} />
            </div>
          </details>
          <p className="campus-note" role="note">{NO_PASSWORD}</p>
        </>
      )}

      {found !== null && stage !== 'connect' && <div className="card" role="status"><strong>Found {found} upcoming deadline{found === 1 ? '' : 's'}.</strong> <span className="muted">They are in your calendar now.</span></div>}
      {stage === 'classes' && <ClassesStep onDone={() => setStage('sort')} />}
      {stage === 'sort' && <SortStep />}
    </div>
  )
}

/* ---------------- Blackboard via the browser helper: the main path ---------------- */
const HELPER_PATH = 'C:\\Users\\lucas\\semesteros\\extension'
/** Which learning system do you use? Preselected from your saved choice or your campus; changes the steps below. */
function SystemPicker() {
  const { lms, setLms } = useLmsChoice()
  return (
    <section className="stack" style={{ gap: 'var(--s-2)' }} aria-label="Your learning system">
      <span className="field-label" id="lms-pick">Which system does your school use?</span>
      <div className="segmented lms-pick" role="radiogroup" aria-labelledby="lms-pick">
        {(['blackboard', 'canvas'] as const).map(id => (
          <button key={id} type="button" role="radio" aria-checked={lms === id} aria-pressed={lms === id} onClick={() => setLms(id)}>{id === 'blackboard' ? 'Blackboard' : 'Canvas'}</button>
        ))}
      </div>
      <button type="button" className={`link-btn${lms === 'other' ? ' is-on' : ''}`} style={{ alignSelf: 'flex-start' }} onClick={() => setLms('other')}>Other / I'll add classes by hand</button>
    </section>
  )
}

function HelperPanel({ tenant }: { tenant: { lms?: { baseUrl?: string; type?: string } } | null }) {
  const { lms: system } = useLmsChoice()
  const sysName = system === 'canvas' ? 'Canvas' : 'Blackboard'
  const navigate = useNavigate()
  const { push } = useToast()
  const { courses, reload } = useCourses()
  const [copied, setCopied] = useState(false)
  // Live scan status posted by the helper (site.js) on this origin: progress, classes, sending, done, failed.
  const [scan, setScan] = useState<null | { kind: 'running' | 'done' | 'failed'; percent: number; line: string; count?: number }>(null)
  const [found, setFound] = useState<{ id: string; code: string; title: string }[]>([])
  const [seen, setSeen] = useState(false)          // any message from the helper: it is installed and talking to this page
  const [now, setNow] = useState(() => Date.now())
  const opened = useRef(Date.now())
  const lastMsg = useRef(0)
  const finished = useRef(false)             // latched once a run reports 100% / done, until a new run starts
  const sig = useRef({ s: '', at: Date.now() }) // repeated identical progress for 90 s hides the card
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.source !== window || e.origin !== window.location.origin) return
      const d = e.data as { source?: unknown; type?: unknown; percent?: unknown; line?: unknown; count?: unknown; items?: unknown } | null
      if (!d || d.source !== 'blackboard') return
      lastMsg.current = Date.now(); setSeen(true)
      // Cancelled scan, or an idle phase at 0%: clear the card at once (no green "finished"), reset the latch and the 90 s rule.
      const ph = typeof (d as { phase?: unknown }).phase === 'string' ? (d as { phase: string }).phase : ''
      const pc = typeof d.percent === 'number' ? d.percent : undefined
      if (d.type === 'cancelled' || (d.type === 'progress' && ph === 'idle' && !(pc !== undefined && pc >= 100))) {
        finished.current = false; sig.current = { s: '', at: Date.now() }; setScan(null); setFound([])
        return
      }
      const text = (v: unknown) => (typeof v === 'string' ? v.slice(0, 160) : '')
      if (d.type === 'progress' || d.type === 'sending') {
        const p = typeof d.percent === 'number' && Number.isFinite(d.percent) ? Math.max(0, Math.min(100, Math.round(d.percent))) : 0
        const phase = typeof (d as { phase?: unknown }).phase === 'string' ? (d as { phase: string }).phase : ''
        if (phase === 'fetch') return // chat fetch progress is not a scan
        const isDone = (typeof d.percent === 'number' && p >= 100) || phase === 'done'
        if (finished.current) { if (isDone || p >= 100) return; finished.current = false } // later progress of a finished run is ignored; a drop below 100 starts a new run
        if (isDone) { finished.current = true; setScan(s => ({ kind: 'done', percent: 100, line: '', count: s?.count ?? (typeof d.count === 'number' ? d.count : undefined) })); return }
        const key = `${p}|${text(d.line)}`
        if (sig.current.s !== key) sig.current = { s: key, at: Date.now() }
        setScan(s => ({ kind: 'running', percent: d.type === 'sending' && !(typeof d.percent === 'number') ? Math.max(s?.percent ?? 0, 90) : p, line: text(d.line) || (d.type === 'sending' ? 'Sending to Semester OS' : 'Scanning'), count: s?.count }))
      } else if (d.type === 'done') {
        finished.current = true
        const n = typeof d.count === 'number' && d.count >= 0 && d.count < 1000 ? Math.floor(d.count) : undefined
        setScan({ kind: 'done', percent: 100, line: '', count: n })
      } else if (d.type === 'failed') {
        setScan({ kind: 'failed', percent: 0, line: text(d.line) })
      } else if (d.type === 'classes' && Array.isArray(d.items)) {
        setFound((d.items as { id?: unknown; code?: unknown; title?: unknown }[]).slice(0, 40).filter(i => i && typeof i.code === 'string').map((i, k) => ({ id: typeof i.id === 'string' ? i.id : String(k), code: text(i.code), title: text(i.title) })))
      }
    }
    window.addEventListener('message', onMsg)
    const t = window.setInterval(() => { setNow(Date.now()); if (Date.now() - sig.current.at > 90000) setScan(s => (s && s.kind === 'running' ? null : s)) }, 5000)
    return () => { window.removeEventListener('message', onMsg); window.clearInterval(t) }
  }, [])
  const tType = String(tenant?.lms?.type ?? '').toLowerCase()
  const base = (() => { if (system === 'other' || (tType && system && tType !== system)) return null; try { const u = new URL(tenant?.lms?.baseUrl ?? ''); return u.protocol === 'https:' ? u.href : null } catch { return null } })()

  // While this page is open, check for classes every 2 seconds so they appear as the helper sends them.
  useEffect(() => {
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') reload() }, 2000)
    return () => window.clearInterval(t)
  }, [reload])

  async function copy() {
    try { await navigator.clipboard.writeText(HELPER_PATH); setCopied(true); window.setTimeout(() => setCopied(false), 2000) }
    catch { push('info', 'Copy it manually', 'Your browser blocked copying: select the path and copy it.') }
  }
  const building = courses.some(c => c.status === 'BUILDING')
  if (system === 'other') return <div className="campus-note" role="note">No problem. Use "Other ways to add classes" below: add class codes or a syllabus, and each class's agent builds in about a minute.</div>

  return (
    <section className="window" aria-label="Connect your classes with the browser helper">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">connect-blackboard</span><HelperBadge /></div>
      <div className="window-body stack">
        <ol className="steps-big">
          <li>
            <strong>Install the Semester OS browser helper</strong>
            <details className="mk-safety" id="helper-steps"><summary>Show me how (about a minute)</summary>
              <ol className="stack" style={{ gap: 'var(--s-2)', listStyle: 'decimal inside', marginTop: 'var(--s-2)' }}>
                <li>In Chrome, open <code>chrome://extensions</code> and turn on <strong>Developer mode</strong> (top right).</li>
                <li>Click <strong>Load unpacked</strong> and choose the extension folder:</li>
              </ol>
              <div className="copy-field" style={{ marginTop: 'var(--s-2)' }}>
                <input readOnly aria-label="Extension folder path" value={HELPER_PATH} onFocus={e => e.currentTarget.select()} />
                <button type="button" className="btn-ghost btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
              </div>
              <p className="muted" style={{ fontSize: 'var(--text-sm)', marginTop: 'var(--s-2)' }}>Honest note: this helper is a prototype loaded in developer mode, not yet in the Chrome Web Store. It only runs on your school's Blackboard and on this site.</p>
            </details>
          </li>
          <li>
            <strong>{system ? `Open your school's ${sysName} and click the helper` : 'Open your school\'s Blackboard or Canvas and click the helper'}</strong>
            <p className="muted">Sign in like you always do, then click the Semester OS icon in your browser toolbar (or use the panel that appears in the corner of the page). The helper detects Blackboard or Canvas by itself.</p>
            {base && <a className="btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} href={base} target="_blank" rel="noopener noreferrer">{`Open ${sysName}`}</a>}
          </li>
          <li>
            <strong>Press "Scan my classes"</strong>
            <p className="muted">The helper reads your course list and deadlines while you watch, never your password, and sends them only to your Semester OS account.</p>
          </li>
        </ol>

        <div className="stack" role="status" aria-live="polite" style={{ gap: 'var(--s-2)' }}>
          {scan && scan.kind === 'running' && now - lastMsg.current > 60000 && (
            <div className="warning" role="alert"><span>The scan seems stuck. Open the helper panel on your school site and press Cancel scan, then press Scan my classes again.</span><button type="button" className="btn-ghost-sm" onClick={() => setScan(null)}>Dismiss</button></div>
          )}
          {scan && (
            <div className="card stack scan-card" data-state={scan.kind} style={{ gap: 'var(--s-2)' }}>
              {scan.kind === 'running' && (
                <>
                  <div className="row" style={{ justifyContent: 'space-between' }}><strong>Scanning your classes</strong><span className="mono">{scan.percent}%</span></div>
                  <div className="bar-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={scan.percent} aria-label="Scan progress"><i style={{ width: `${scan.percent}%` }} /></div>
                  <span className="muted">{scan.line}</span>
                </>
              )}
              {scan.kind === 'done' && <div className="row"><span className="scan-ok" aria-hidden="true">✓</span><strong>{scan.count != null ? `${scan.count} class${scan.count === 1 ? '' : 'es'} added` : 'Your classes were added'}</strong></div>}
              {scan.kind === 'failed' && (
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <span className="field-error" role="alert">{scan.line || "The scan didn't finish."}</span>
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setScan(null)}>Try again</button>
                </div>
              )}
              {found.length > 0 && scan.kind === 'running' && <div className="chip-row" aria-label="Classes found so far">{found.map(f => <span key={f.id} className="chip" title={f.title}>{f.code}</span>)}</div>}
            </div>
          )}
          {courses.length === 0 && !scan ? (
            !seen && now - opened.current > 5000
              ? <div className="warning" role="alert"><span>Helper not detected. Install or reload the Semester OS helper, then press Scan my classes. <a href="#helper-steps" onClick={() => { const d = document.getElementById('helper-steps') as HTMLDetailsElement | null; if (d) d.open = true }}>Show the setup steps</a></span></div>
              : <div className="campus-note" role="note"><strong>Ready when you are.</strong> Open {sysName} and press Scan my classes in the helper (steps above). Your classes show up here once a scan starts.</div>
          ) : courses.length === 0 ? null : (
            <>
              <span className="eyebrow">{building ? 'Your classes are arriving…' : 'Your classes'}</span>
              <div className="agent-grid">
                {courses.map(c => {
                  const i = classIndexFromHex(c.color)
                  const n = c.knows?.assignmentsCount ?? 0
                  return (
                    <article key={c.id} className="window agent-card" data-theme={i >= 0 ? `c${i}` : undefined}>
                      <RouterLink to={`/study/${c.id}`} className="stretch sr-only-link" aria-label={`Open ${c.courseCode || 'class'} agent`}>Open agent</RouterLink>
                      <div className="agent-swatch" />
                      <div className="window-body">
                        <div className="row" style={{ flexWrap: 'nowrap' }}>
                          <Robot name={c.status === 'BUILDING' ? 'state-building' : c.status === 'ERROR' ? 'state-error' : 'class-tutor'} size={44} />
                          <div className="grow"><div className="agent-name truncate">{c.courseCode || 'New class'}{c.status === 'READY' ? ` · ${n} deadline${n === 1 ? '' : 's'}` : ''}</div><div className="agent-role">{c.title || (c.status === 'BUILDING' ? 'Setting up…' : '')}</div></div>
                        </div>
                      </div>
                    </article>
                  )
                })}
              </div>
              <div className="card row" style={{ justifyContent: 'space-between' }}>
                <span>{building ? <span className="muted">More classes may still be arriving. Tap a class to open its agent.</span> : <><strong>All set.</strong> <span className="muted">Tap a class to open its agent.</span></>}</span>
                <button type="button" className="btn-primary" onClick={() => navigate('/study')}>Go to Study</button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}

/* ---------------- Blackboard: guided calendar link ---------------- */
function BlackboardPanel({ onConnected }: { onConnected: (n: number) => void }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const { data, state, reload } = useEndpoint<FeedStatus>('/me/feed')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [stage, setStage] = useState<'idle' | 'saving' | 'reading' | 'done'>('idle')
  const [summary, setSummary] = useState('')

  async function scan(e?: React.FormEvent) {
    e?.preventDefault(); setBusy(true); setErr(''); setSummary('')
    let upcoming: number | undefined = data?.counts?.events
    try {
      if (!data?.connected) {
        setStage('saving')
        const r = await authFetch('/me/feed', { method: 'PUT', body: JSON.stringify({ url: url.trim() }) })
        if (!r.ok) { setErr(await errorMessage(r, "That link didn't work. Check it and try again.")); setStage('idle'); return }
        try { const pj = await r.json(); if (typeof pj.upcomingCount === 'number') upcoming = pj.upcomingCount } catch { /* no body */ }
        setUrl('')
      }
      setStage('reading')
      const s = await authFetch('/me/feed/sync', { method: 'POST', body: '{}' })
      if (!s.ok) { setErr(await errorMessage(s, "We couldn't read your calendar yet. Try again in a moment.")); setStage('idle'); reload(); return }
      const j = await s.json()
      setSummary(j.status === 'unchanged' ? 'Your calendar is up to date.' : `Found ${(j.added ?? 0) + (j.updated ?? 0)} deadlines${j.unassigned ? `, ${j.unassigned} waiting for a class` : ''}.`)
      setStage('done'); reload()
      const n = upcoming ?? ((j.added ?? 0) + (j.updated ?? 0) + (j.unassigned ?? 0) + (j.unchanged ?? 0))
      push('success', 'Blackboard connected', `Found ${n} upcoming deadline${n === 1 ? '' : 's'}.`)
      window.setTimeout(() => onConnected(n), 1200) // let the result show, then move to the next step
    } catch { setErr('Network problem. Try again.'); setStage('idle') } finally { setBusy(false) }
  }

  return (
    <section className="window" aria-label="Connect Blackboard">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">connect-blackboard</span></div>
      <div className="window-body stack">
        <h2 style={{ fontSize: 'var(--text-md)' }}>Share your Blackboard calendar</h2>
        <ol className="stack" style={{ gap: 'var(--s-2)', listStyle: 'decimal inside' }}>
          <li>Open Blackboard and go to <strong>Calendar</strong>.</li>
          <li>Click the <strong>gear icon</strong> (Calendar Settings), top right of the Calendar page.</li>
          <li>In the panel that opens, click the <strong>three dots</strong> (More options), then choose <strong>Share calendar</strong>.</li>
          <li><strong>Copy the link</strong> and paste it below.</li>
        </ol>
        <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>Menu names can differ a little at your school. The link is read-only and carries dates and events only (not files, announcements or grades). Treat it like a password: we store it encrypted and only show a masked version.</p>

        {state === 'ok' && data?.connected ? (
          <div className="stack">
            <div className="row"><span className="badge badge-ok">Connected</span><span className="mono muted">{data.urlMasked}</span></div>
            <button type="button" className="btn-primary btn-lg" onClick={() => scan()} disabled={busy} aria-busy={busy}>{busy ? 'Scanning…' : 'Scan for classes'}</button>
          </div>
        ) : (
          <form className="stack" onSubmit={scan}>
            <div className="field">
              <label htmlFor="bb-link">Calendar link</label>
              <input id="bb-link" type="password" autoComplete="off" spellCheck={false} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…" />
            </div>
            <button type="submit" className="btn-primary btn-lg" disabled={busy || !url.trim()} aria-busy={busy}>{busy ? 'Scanning…' : 'Scan for classes'}</button>
          </form>
        )}

        {stage !== 'idle' && (
          <ol className="stepper" aria-label="Scan progress" aria-live="polite">
            <li className="step" data-state={stage === 'saving' ? 'running' : 'done'}><span className="step-dot" />Checking your link</li>
            <li className="step" data-state={stage === 'saving' ? 'pending' : stage === 'reading' ? 'running' : 'done'}><span className="step-dot" />Reading your calendar</li>
            <li className="step" data-state={stage === 'done' ? 'done' : 'pending'}><span className="step-dot" />Pulling in your deadlines{summary ? <span className="step-detail">{summary}</span> : null}</li>
          </ol>
        )}
        {err && <p className="field-error" role="alert">{err}</p>}
        {state === 'unavailable' && <p className="muted">Blackboard connection isn't available yet. You can still add each class with its syllabus below.</p>}
        <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>Your calendar gives us every deadline. Next, add each class with its syllabus below, then sort the deadlines into your classes.</p>
      </div>
    </section>
  )
}

/* ---------------- Canvas: guided token (backend coming) ---------------- */
function CanvasPanel() {
  const { authFetch } = useAuth()
  const [token, setToken] = useState('')
  const [msg, setMsg] = useState('')
  async function scan(e: React.FormEvent) {
    e.preventDefault()
    const r = await canvasScan(authFetch, token)
    setMsg(r.message ?? '')
  }
  return (
    <section className="window" aria-label="Connect Canvas">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">connect-canvas</span><span className="badge">Coming soon</span></div>
      <div className="window-body stack">
        <h2 style={{ fontSize: 'var(--text-md)' }}>Create a Canvas access token</h2>
        <ol className="stack" style={{ gap: 'var(--s-2)', listStyle: 'decimal inside' }}>
          <li>Sign in to Canvas as you normally do.</li>
          <li>Open <strong>Account</strong>, then <strong>Settings</strong>.</li>
          <li>Under Approved Integrations, choose <strong>New access token</strong>, name it "Semester OS" and create it.</li>
          <li>Copy the token and paste it here. You'll only see it once in Canvas.</li>
        </ol>
        <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>Some schools turn tokens off. If you don't see the button, use your syllabi below instead. You can delete the token in Canvas any time.</p>
        <form className="stack" onSubmit={scan}>
          <div className="field">
            <label htmlFor="canvas-token">Access token</label>
            <input id="canvas-token" type="password" autoComplete="off" spellCheck={false} value={token} disabled={!CANVAS_SCAN_LIVE} onChange={e => setToken(e.target.value)} placeholder={CANVAS_SCAN_LIVE ? '' : 'Available soon'} />
          </div>
          <button type="submit" className="btn-primary btn-lg" disabled={!CANVAS_SCAN_LIVE || !token.trim()}>Scan for classes</button>
        </form>
        {!CANVAS_SCAN_LIVE && <p className="campus-note" role="status">Canvas scanning is coming soon, so we're not asking for a token yet. For now, add your classes from syllabus PDFs below.</p>}
        {msg && CANVAS_SCAN_LIVE && <p className="muted" role="status">{msg}</p>}
      </div>
    </section>
  )
}

/* ---------------- syllabus upload (all paths) ---------------- */
function SyllabusPanel({ intro }: { intro: string }) {
  return (
    <section className="stack" aria-label="Add classes from syllabi">
      <p>{intro}</p>
      <AddClass onAdded={() => {}} onClose={() => {}} />
    </section>
  )
}

/* ---------------- what we found ---------------- */
function ClassesFound({ offerAdd }: { offerAdd: boolean }) {
  const { courses, reload } = useCourses()
  const [adding, setAdding] = useState(false)
  return (
    <section aria-labelledby="found-h" className="stack">
      <div className="section-head"><h2 id="found-h">Your classes</h2>{courses.length > 0 && <Link to="/study" className="btn-primary btn-sm">Go to Study</Link>}</div>
      {courses.length === 0 ? (
        <div className="empty"><Robot name="base" size={72} /><div className="empty-title">No classes yet</div><p className="empty-body">Classes appear here as they're found or built. Add a syllabus to start your first agent.</p></div>
      ) : (
        <div className="agent-grid" aria-live="polite">
          {courses.map(c => {
            const i = classIndexFromHex(c.color)
            return (
              <article key={c.id} className="window agent-card" data-theme={i >= 0 ? `c${i}` : undefined}>
                <div className="agent-swatch" />
                <div className="window-body">
                  <div className="row" style={{ flexWrap: 'nowrap' }}>
                    <Robot name={c.status === 'BUILDING' ? 'state-building' : c.status === 'ERROR' ? 'state-error' : 'class-tutor'} size={48} />
                    <div className="grow"><div className="agent-name truncate">{c.courseCode || 'New class'}</div><div className="agent-role">{c.title || (c.status === 'BUILDING' ? 'Reading your syllabus…' : '')}</div></div>
                    <span className="badge" data-status={c.status.toLowerCase()}>{c.status === 'READY' ? 'Ready' : c.status === 'BUILDING' ? 'Building' : 'Error'}</span>
                  </div>
                  {c.status !== 'READY' && c.pipeline?.length > 0 && (
                    <ol className="stepper" aria-label="Build progress">{c.pipeline.map(s => <li key={s.key} className="step" data-state={s.state}><span className="step-dot" />{s.label}</li>)}</ol>
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}
      {offerAdd && (adding
        ? <AddClass onAdded={reload} onClose={() => setAdding(false)} />
        : <button type="button" className="btn-ghost" style={{ alignSelf: 'flex-start' }} onClick={() => setAdding(true)}>Add a class from its syllabus</button>)}
    </section>
  )
}


/* ---------------- step 2: which classes are you taking? ---------------- */
const CODE_RE = /^[A-Za-z]{2,5}\s?-?\d{2,4}[A-Za-z]?$/
const tidyCode = (c: string) => c.trim().toUpperCase().replace(/^([A-Z]{2,5})\s?-?(\d)/, '$1 $2')

function ClassesStep({ onDone }: { onDone: () => void }) {
  const { authFetch } = useAuth()
  const { push } = useToast()
  const { data } = useEndpoint<{ suggested?: (string | { code?: string })[] }>('/me/feed/classes')
  const suggested = (data?.suggested ?? []).map(x => (typeof x === 'string' ? x : x?.code ?? '')).map(tidyCode).filter(Boolean)
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const chosen = picked ?? new Set(suggested)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [fallback, setFallback] = useState(false)

  const toggle = (c: string) => { const n = new Set(chosen); n.has(c) ? n.delete(c) : n.add(c); setPicked(n) }
  const typedCodes = typed.split(',').map(tidyCode).filter(Boolean)
  const bad = typedCodes.filter(c => !CODE_RE.test(c))
  const codes = [...new Set([...chosen, ...typedCodes.filter(c => CODE_RE.test(c))])].slice(0, 12)

  async function create() {
    setBusy(true); setErr('')
    try {
      const r = await authFetch('/courses/quick', { method: 'POST', body: JSON.stringify({ courses: codes.map(code => ({ code })) }) })
      if ([401, 403, 404, 405, 501].includes(r.status)) { setFallback(true); return }
      if (!r.ok) { setErr(await errorMessage(r, "We couldn't create your classes. Try again.")); return }
      const j = await r.json()
      const n = (j.created ?? []).length
      const placed = typeof j.placed === 'number' && j.placed > 0 ? `, ${j.placed} deadline${j.placed === 1 ? '' : 's'} placed` : ''
      push('success', n ? `Created ${n} class${n === 1 ? '' : 'es'}${placed}` : 'Your classes are already set up')
      onDone()
    } catch { setErr('Network problem. Try again.') } finally { setBusy(false) }
  }

  return (
    <section className="window" aria-label="Your classes">
      <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">your-classes</span></div>
      <div className="window-body stack">
        {suggested.length > 0 && (
          <div className="field"><span className="field-label" id="sug-l">We spotted these in your calendar. Tap to keep or remove.</span>
            <div className="chip-row" role="group" aria-labelledby="sug-l">
              {suggested.map(c => <button key={c} type="button" className={chosen.has(c) ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'} aria-pressed={chosen.has(c)} onClick={() => toggle(c)}>{c}</button>)}
            </div></div>
        )}
        <div className="field">
          <label htmlFor="codes">Add classes by code (comma separated)</label>
          <input id="codes" value={typed} onChange={e => setTyped(e.target.value)} placeholder="MIS 405, MIS 430" />
          {bad.length > 0 && <span className="field-error" role="status">These don't look like class codes: {bad.join(', ')} (try letters then numbers, like MIS 405).</span>}
        </div>
        {err && <p className="field-error" role="alert">{err}</p>}
        <div className="row">
          <button type="button" className="btn-primary btn-lg" style={{ width: 'auto' }} disabled={busy || codes.length === 0 || bad.length > 0} aria-busy={busy} onClick={create}>{busy ? 'Creating…' : `Create my class${codes.length === 1 ? '' : 'es'}`}</button>
          <button type="button" className="link-btn" onClick={onDone}>Skip for now</button>
        </div>
        {fallback && <p className="campus-note" role="status">Quick class setup isn't available yet. Add each class with its syllabus below instead (paste, upload, or try the sample).</p>}
        <details className="mk-safety" open={fallback}>
          <summary>Add a class with its syllabus instead</summary>
          <div className="stack" style={{ marginTop: 'var(--s-3)' }}>
            <p className="muted">Paste it, upload the PDF, or try the sample. The syllabus also gives the class its books, grading and policies.</p>
            <AddClass onAdded={() => {}} onClose={() => {}} startTab="text" embedded />
          </div>
        </details>
      </div>
    </section>
  )
}

/* ---------------- step 3: sort deadlines, then finish at the Calendar ---------------- */
function SortStep() {
  const navigate = useNavigate()
  return (
    <div className="stack">
      <UnassignedInbox hero onChanged={() => {}} />
      <p className="muted">If nothing appears above, every deadline already has a class.</p>
      <div className="row">
        <button type="button" className="btn-primary btn-lg" style={{ width: 'auto' }} onClick={() => navigate('/calendar', { state: { allSet: true } })}>Finish and see my calendar</button>
        <Link to="/study" className="btn-ghost">Open Study</Link>
      </div>
    </div>
  )
}
