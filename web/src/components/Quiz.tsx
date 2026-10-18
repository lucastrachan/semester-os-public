import { useState } from 'react'
import type { QuizQuestion } from '../lib/tutor'

/** One question at a time. Multiple choice is auto-graded; short answers are self-graded against the model answer. */
export default function Quiz({ questions, onDone }: { questions: QuizQuestion[]; onDone: () => void }) {
  const [i, setI] = useState(0)
  const [picked, setPicked] = useState<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [typed, setTyped] = useState('')
  const [correct, setCorrect] = useState(0)
  const [finished, setFinished] = useState(false)

  const q = questions[i]
  const total = questions.length

  function grade(ok: boolean) {
    if (ok) setCorrect(c => c + 1)
  }
  function pick(n: number) {
    if (revealed || q.type !== 'mc') return
    setPicked(n)
    setRevealed(true)
    grade(n === q.answerIndex)
  }
  function next() {
    if (i + 1 >= total) { setFinished(true); return }
    setI(i + 1); setPicked(null); setRevealed(false); setTyped('')
  }

  if (finished) {
    return (
      <div className="card stack" style={{ alignItems: 'center', textAlign: 'center' }}>
        <span className="eyebrow">Quiz complete</span>
        <div className="score" aria-label={`Score ${correct} of ${total}`}>{correct}/{total}</div>
        <p className="muted">{correct === total ? 'Perfect. Ready for something harder?' : 'Review the ones you missed, then try a fresh set.'}</p>
        <button type="button" className="btn-primary" onClick={onDone}>New quiz</button>
      </div>
    )
  }

  return (
    <div className="card stack">
      <div className="quiz-progress" style={{ ['--value' as string]: `${(i / total) * 100}%` }} role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={i} aria-label="Quiz progress"><i /></div>
      <span className="eyebrow">Question {i + 1} of {total}</span>
      <strong id="q-text">{q.question}</strong>

      {q.type === 'mc' ? (
        <div className="quiz-options" role="group" aria-labelledby="q-text">
          {(q.choices ?? []).map((c, n) => {
            const state = revealed ? (n === q.answerIndex ? 'correct' : n === picked ? 'wrong' : undefined) : undefined
            return (
              <button key={n} type="button" className="quiz-option" data-state={state} aria-pressed={picked === n} disabled={revealed && state === undefined} onClick={() => pick(n)}>
                <span className="mono">{String.fromCharCode(65 + n)}</span>
                <span>{c}</span>
                {state === 'correct' && <span className="sr-only"> (correct)</span>}
                {state === 'wrong' && <span className="sr-only"> (your answer, incorrect)</span>}
              </button>
            )
          })}
        </div>
      ) : (
        <div className="stack">
          <div className="field">
            <label htmlFor="short-answer" className="sr-only">Your answer</label>
            <textarea id="short-answer" rows={3} value={typed} disabled={revealed} onChange={e => setTyped(e.target.value)} placeholder="Type your answer, then check it." />
          </div>
          {!revealed && <button type="button" className="btn-ghost" onClick={() => setRevealed(true)}>Show model answer</button>}
          {revealed && (
            <>
              <div className="quiz-explain"><strong>Model answer:</strong> {q.answer}</div>
              {picked === null && (
                <div className="row">
                  <span className="muted">How did you do?</span>
                  <button type="button" className="btn-primary btn-sm" onClick={() => { setPicked(1); grade(true) }}>Got it</button>
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setPicked(0)}>Missed it</button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {revealed && q.explanation && <div className="quiz-explain" role="status">{q.explanation}</div>}
      {revealed && (q.type === 'mc' || picked !== null) && (
        <button type="button" className="btn-primary" style={{ alignSelf: 'flex-start' }} onClick={next}>{i + 1 >= total ? 'See my score' : 'Next question'}</button>
      )}
    </div>
  )
}
