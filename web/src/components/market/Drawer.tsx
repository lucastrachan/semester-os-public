import { useEffect, useRef, type ReactNode } from 'react'

/** Side sheet on desktop, bottom sheet on phones. Esc and the backdrop close it, focus is trapped and restored. */
export default function Drawer({ open, title, onClose, children, footer, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const returnTo = useRef<Element | null>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose // keep the effect below tied to `open` only, or it would steal focus on every re-render

  useEffect(() => {
    if (!open) return
    returnTo.current = document.activeElement
    const first = box.current?.querySelector<HTMLElement>('button, a[href], input, select, textarea')
    first?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); closeRef.current(); return }
      if (e.key !== 'Tab' || !box.current) return
      const f = box.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select, textarea')
      if (!f.length) return
      const a = f[0], z = f[f.length - 1]
      if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus() }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); (returnTo.current as HTMLElement | null)?.focus?.() }
  }, [open])

  if (!open) return null
  return (
    <div className="drawer-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={box} className={`drawer${wide ? ' drawer--wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="drawer-head">
          <h2>{title}</h2>
          <button type="button" className="btn-ghost-sm" onClick={onClose} aria-label={`Close ${title}`}>Close</button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </div>
    </div>
  )
}
