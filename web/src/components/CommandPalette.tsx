import { useEffect, useRef } from 'react'
import MasterChat from './MasterChat'
import type { Course } from '../lib/api'

/** Ctrl/Cmd+K opens the Chief of Staff from any page. Esc closes, focus is trapped, focus returns to where it was. */
export default function CommandPalette({ open, onClose, courses }: { open: boolean; onClose: () => void; courses: Course[] }) {
  const box = useRef<HTMLDivElement>(null)
  const returnTo = useRef<Element | null>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    if (!open) return
    returnTo.current = document.activeElement
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); closeRef.current(); return }
      if (e.key !== 'Tab' || !box.current) return
      const f = box.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled])')
      if (!f.length) return
      const first = f[0], last = f[f.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); (returnTo.current as HTMLElement | null)?.focus?.() }
  }, [open])

  if (!open) return null
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'var(--overlay)', display: 'grid', placeItems: 'start center', padding: '8vh var(--s-4) var(--s-4)' }}
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={box} role="dialog" aria-modal="true" aria-label="Chief of Staff" style={{ width: 'min(40rem, 100%)', maxHeight: '80vh', display: 'flex', flexDirection: 'column', boxShadow: 'var(--shadow-3)', borderRadius: 'var(--radius-lg)' }}>
        <div className="window-bar" style={{ borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0', border: '1px solid var(--border)', borderBottom: 0, background: 'var(--surface-2)' }}>
          <span className="window-dots" aria-hidden="true"><i /><i /><i /></span>
          <span className="window-title">chief-of-staff</span>
          <span className="eyebrow">Esc to close</span>
          <button type="button" className="btn-ghost-sm" onClick={onClose}>Close</button>
        </div>
        <MasterChat courses={courses} onNavigate={onClose} autoFocus />
      </div>
    </div>
  )
}
