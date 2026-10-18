import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { useToast } from './Toast'

export const AVATARS = Array.from({ length: 12 }, (_, i) => `robot-${String(i + 1).padStart(2, '0')}`)
export const isAvatar = (s: unknown): s is string => typeof s === 'string' && AVATARS.includes(s)

/** Deterministic default robot from a stable id (FNV-1a). Never use an email: anything containing "@" is ignored. */
export function defaultAvatar(key?: string | null): string {
  const k = key && !key.includes('@') ? key : 'semester-os'
  let h = 0x811c9dc5
  for (let i = 0; i < k.length; i++) { h ^= k.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0 }
  return AVATARS[h % AVATARS.length]
}
export const avatarSlug = (avatar?: unknown, key?: string | null) => (isAvatar(avatar) ? avatar : defaultAvatar(key))

/** Round robot avatar. `avatar` is the saved slug (allow-listed); without one, a default robot is picked from `id`. */
export default function Avatar({ avatar, id, size = 32, label }: { avatar?: unknown; id?: string | null; size?: number; label?: string }) {
  const slug = avatarSlug(avatar, id)
  return (
    <img className="avatar" src={`/avatars/${slug}.svg`} width={size} height={size} alt={label ?? ''} aria-hidden={label ? undefined : true}
      loading="lazy" decoding="async" style={{ width: size, height: size }} />
  )
}

/** The signed-in user's own avatar (saved choice, else the default robot for their account id). */
export function MyAvatar({ size = 32, label }: { size?: number; label?: string }) {
  const { profile, user } = useAuth()
  return <Avatar avatar={profile?.avatar} id={user?.sub} size={size} label={label} />
}

/** Settings: pick one of the 12 robots. PATCH /me {avatar}. */
export function AvatarPicker() {
  const { profile, user, authFetch, setProfile, tenant } = useAuth()
  const { push } = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  const current = avatarSlug(profile?.avatar, user?.sub)

  async function choose(slug: string) {
    if (slug === current || busy) return
    setBusy(slug)
    try {
      const r = await authFetch('/me', { method: 'PATCH', body: JSON.stringify({ avatar: slug }) })
      if (!r.ok) { push('error', "Couldn't save your avatar", await errorMessage(r)); return }
      const j = await r.json().catch(() => ({}))
      const next = j?.profile ?? j
      setProfile({ ...profile, ...(next && typeof next === 'object' ? next : {}), avatar: isAvatar(next?.avatar) ? next.avatar : slug }, j?.tenant ?? tenant)
      push('success', 'Avatar updated')
    } catch { push('error', "Couldn't save your avatar", 'Network problem. Try again.') } finally { setBusy(null) }
  }

  return (
    <div className="field">
      <span className="field-label" id="avatar-h">Your avatar</span>
      <div className="avatar-grid" role="radiogroup" aria-labelledby="avatar-h">
        {AVATARS.map((s, i) => (
          <button key={s} type="button" role="radio" aria-checked={s === current} aria-label={`Robot ${i + 1}`} className="avatar-opt" onClick={() => choose(s)} disabled={!!busy && busy !== s} aria-busy={busy === s}>
            <Avatar avatar={s} size={56} />
          </button>
        ))}
      </div>
    </div>
  )
}
