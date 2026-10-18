// Resolve an email domain to a school while the user types (AUTO_CAMPUS.md). Until Builder documents
// GET /public/resolve in API.md the response shape is a guess, so parsing is defensive and ANY failure means "unknown".
import type { Api } from 'shared/api'
import type { ResolvedSchool } from 'shared/types'
import { autoThemeFromName, isHex } from 'shared/tokens'

type Obj = Record<string, unknown>
const asObj = (v: unknown): Obj | null => (v && typeof v === 'object' ? (v as Obj) : null)

function parse(raw: unknown): ResolvedSchool | null {
  const top = asObj(raw)
  if (!top || top.found === false) return null
  const o = asObj(top.tenant) ?? asObj(top.campus) ?? asObj(top.school) ?? top
  const name = typeof o.name === 'string' ? o.name : typeof o.schoolName === 'string' ? o.schoolName : ''
  if (!name) return null
  const theme = asObj(o.theme)
  const color = [theme?.primary, o.primary, o.themeColor, o.color].find(isHex)
  return { name, primary: color ?? autoThemeFromName(name), autoCreated: o.autoCreated === true, colorStatus: typeof o.colorStatus === 'string' ? o.colorStatus : typeof top.colorStatus === 'string' ? top.colorStatus : undefined }
}

export const domainOf = (email: string): string | null => {
  const m = email.trim().toLowerCase().match(/^[^@\s]+@([a-z0-9.-]+\.[a-z]{2,})$/)
  return m ? m[1] : null
}

export async function resolveSchool(api: Api, domain: string): Promise<ResolvedSchool | null> {
  try { return parse(await api.resolveDomainRaw(domain)) } catch { return null }
}
