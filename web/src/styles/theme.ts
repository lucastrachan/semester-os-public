// Runtime theming helpers (Designer). DOM only. Colour maths lives in ./color.ts (pure, shared with native).
// See DESIGN.md "Theming API".
import { deriveTheme, isHex, type Derived } from './color'

export { CLASS_PALETTE, classIndexFromHex, contrast, deriveTheme } from './color'

const block = (d: Derived) =>
  `--accent:${d.accent};--accent-ink:${d.accentInk};--accent-tint:${d.accentTint};--accent-strong:${d.accentStrong};`

/** The campus colour last applied: the base every page returns to when a class colour is dropped (never the default blue by accident). */
let campusBase: string | undefined
let appliedPrimary: string | undefined

/** Campus theme from a tenant's brand colour (the admin form stores #RRGGBB). Falls back to the default accent. */
export function applyCampusTheme(primary?: string): void {
  const root = document.documentElement
  campusBase = isHex(primary) ? primary : undefined
  if (!isHex(primary)) { root.removeAttribute('data-theme'); appliedPrimary = undefined; return }
  // Same colour already showing: do nothing (no restyle, no flash).
  if (appliedPrimary === primary && root.getAttribute('data-theme') === 'campus') return
  appliedPrimary = primary
  const css =
    `:root[data-theme="campus"]{${block(deriveTheme(primary, 'light'))}}` +
    `@media (prefers-color-scheme: dark){:root[data-theme="campus"]{${block(deriveTheme(primary, 'dark'))}}}`
  setCampusSheet(css)
  root.setAttribute('data-theme', 'campus')
}

// CSP-friendly: a constructed stylesheet (CSSOM) is allowed under a strict style-src with no 'unsafe-inline'.
// Fallback for old browsers is a <style> element, which a strict CSP would need a nonce for.
let campusSheet: CSSStyleSheet | null = null
function setCampusSheet(css: string): void {
  if ('adoptedStyleSheets' in document && typeof CSSStyleSheet !== 'undefined' && 'replaceSync' in CSSStyleSheet.prototype) {
    if (!campusSheet) {
      campusSheet = new CSSStyleSheet()
      document.adoptedStyleSheets = [...document.adoptedStyleSheets, campusSheet]
    }
    campusSheet.replaceSync(css)
    return
  }
  let el = document.getElementById('campus-theme') as HTMLStyleElement | null
  if (!el) { el = document.createElement('style'); el.id = 'campus-theme'; document.head.appendChild(el) }
  el.textContent = css
}

/** Study mode / handoff. `index` is course.color's palette position (0..7). Pass null to go back to the campus theme. */
export function applyClassTheme(index: number | null, campusPrimary?: string): void {
  if (index === null || index < 0 || index > 7) {
    const prim = isHex(campusPrimary) ? campusPrimary : campusBase
    if (prim) { applyCampusTheme(prim); return }
    // Campus colour not known yet (still loading): only drop a class colour, never reset a campus theme that is already showing.
    const cur = document.documentElement.getAttribute('data-theme')
    if (cur && /^c\d$/.test(cur)) { document.documentElement.removeAttribute('data-theme'); appliedPrimary = undefined }
    return
  }
  document.documentElement.setAttribute('data-theme', `c${index}`)
}
