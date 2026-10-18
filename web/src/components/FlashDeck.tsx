import { useEffect, useState } from 'react'
import type { Flashcard } from '../lib/tutor'

const key = (courseId: string) => `known:${courseId}`
function loadKnown(courseId: string): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(key(courseId)) ?? '[]')) } catch { return new Set() }
}

/** Flip with click or Space/Enter; arrow keys move; Known/Review buttons. Progress is stored in this browser only. */
export default function FlashDeck({ cards, courseId, onDone }: { cards: Flashcard[]; courseId: string; onDone: () => void }) {
  const [i, setI] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [known, setKnown] = useState<Set<string>>(() => loadKnown(courseId))

  useEffect(() => {
    try { localStorage.setItem(key(courseId), JSON.stringify([...known].slice(-500))) } catch { /* storage unavailable */ }
  }, [known, courseId])

  const card = cards[i]
  const go = (n: number) => { setI(Math.max(0, Math.min(cards.length - 1, n))); setFlipped(false) }
  const mark = (isKnown: boolean) => {
    setKnown(k => { const n = new Set(k); isKnown ? n.add(card.front) : n.delete(card.front); return n })
    if (i < cards.length - 1) go(i + 1)
  }
  const knownCount = cards.filter(c => known.has(c.front)).length

  return (
    <div className="stack" onKeyDown={e => { if (e.key === 'ArrowRight') go(i + 1); if (e.key === 'ArrowLeft') go(i - 1) }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="eyebrow">Card {i + 1} of {cards.length}</span>
        <span className="eyebrow" role="status">{knownCount} known</span>
      </div>
      <div className={`flashcard${flipped ? ' is-flipped' : ''}`}>
        <button type="button" className="flashcard-inner" style={{ width: '100%', textAlign: 'inherit' }} aria-label={flipped ? `Answer: ${card.back}. Press to show the term.` : `Term: ${card.front}. Press to reveal the answer.`} onClick={() => setFlipped(f => !f)}>
          <div className="flashcard-face flashcard-front" aria-hidden={flipped}>{card.front}</div>
          <div className="flashcard-face flashcard-back" aria-hidden={!flipped}>{card.back}</div>
        </button>
      </div>
      <div className="row">
        <button type="button" className="btn-ghost btn-sm" disabled={i === 0} onClick={() => go(i - 1)}>Back</button>
        <button type="button" className="btn-ghost btn-sm" onClick={() => mark(false)}>Review again</button>
        <button type="button" className="btn-primary btn-sm" onClick={() => mark(true)}>Known</button>
        <button type="button" className="btn-ghost btn-sm" disabled={i === cards.length - 1} onClick={() => go(i + 1)}>Next</button>
        <button type="button" className="btn-ghost btn-sm" style={{ marginLeft: 'auto' }} onClick={onDone}>New deck</button>
      </div>
    </div>
  )
}
