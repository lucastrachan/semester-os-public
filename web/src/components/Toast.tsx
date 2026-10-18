import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

type Kind = 'error' | 'success' | 'info'
interface ToastItem { id: number; kind: Kind; title: string; body?: string }
interface ToastApi { push: (kind: Kind, title: string, body?: string) => void }

const ToastContext = createContext<ToastApi>({ push: () => {} })
export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const next = useRef(1)
  const dismiss = useCallback((id: number) => setItems(xs => xs.filter(x => x.id !== id)), [])
  const push = useCallback((kind: Kind, title: string, body?: string) => {
    const id = next.current++
    setItems(xs => [...xs.slice(-3), { id, kind, title, body }])
    window.setTimeout(() => dismiss(id), kind === 'error' ? 9000 : 5000)
  }, [dismiss])
  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="toast-region" aria-live="polite">
        {items.map(t => (
          <div key={t.id} className="toast" data-kind={t.kind} role={t.kind === 'error' ? 'alert' : 'status'}>
            <div>
              <div className="toast-title">{t.title}</div>
              {t.body && <div className="toast-body">{t.body}</div>}
            </div>
            <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)}>✕</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
