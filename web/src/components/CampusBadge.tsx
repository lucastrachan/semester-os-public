import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { deriveTheme, isHex } from '../styles/color'

/** Two or three letters for the monogram: the short name if it has one, else the initials of the full name. */
function monogram(shortName?: string, name?: string): string {
  const s = (shortName ?? '').replace(/[^A-Za-z0-9]/g, '').slice(0, 3)
  if (s) return s.toUpperCase()
  const words = (name ?? '').split(/\s+/).filter(w => w && !/^(the|of|at|and|university|college|institute)$/i.test(w))
  return (words.map(w => w[0]).join('').slice(0, 3) || '?').toUpperCase()
}

/**
 * The school badge in the header: monogram tile in the CAMPUS colour (not the class colour), short name, full name.
 * No school logos (trademark): a logo may be supported later via an admin-set https `logoUrl`.
 */
export default function CampusBadge() {
  const { tenant } = useAuth()
  if (!tenant?.name) return null
  const primary = isHex(tenant.theme?.primary) ? (tenant.theme.primary as string) : '#4F46E5'
  const ink = deriveTheme(primary, 'light').accentInk
  const short = tenant.shortName || monogram(undefined, tenant.name)
  return (
    <Link to="/campus" className="campus-badge" aria-label={`Your campus: ${tenant.name}`} title={tenant.name}>
      <span className="campus-tile" aria-hidden="true" style={{ background: primary, color: ink }}>{monogram(tenant.shortName, tenant.name)}</span>
      <span className="campus-text">
        <strong>{short}</strong>
        <span>{tenant.name}</span>
      </span>
    </Link>
  )
}
