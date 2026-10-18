import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import { useCourses } from '../lib/useCourses'
import { SubscribePanel } from './CalendarPage'
import { useToast } from '../components/Toast'
import FeedCard from '../components/FeedCard'
import { NameField } from '../components/NameCard'
import { AvatarPicker, MyAvatar } from '../components/Avatar'
import { useLmsChoice } from '../lib/lms'
import { HelperBadge } from '../components/BbSources'
import ArchivedClasses from '../components/ArchivedClasses'
import NicknameCard from '../components/rooms/NicknameCard'

const hour = (h: number) => `${((h + 11) % 12) + 1}:00 ${h < 12 ? 'AM' : 'PM'}`

export default function SettingsPage() {
  const { profile, tenant, signOut, authFetch } = useAuth()
  const { push } = useToast()
  const { courses, reload } = useCourses()
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const prefs = profile?.prefs
  const { lms, setLms } = useLmsChoice()

  async function deleteCourse(id: string) {
    try {
      const r = await authFetch(`/courses/${id}`, { method: 'DELETE' })
      if (!r.ok) { push('error', "Couldn't delete the class", await errorMessage(r)); return }
      push('success', 'Class deleted', 'Its deadlines were removed too.')
      setConfirmId(null); reload()
    } catch { push('error', "Couldn't delete the class", 'Network problem. Try again.') }
  }

  return (
    <div className="page">
      <div className="page-head"><span className="eyebrow">Settings</span><h1>Your account</h1></div>

      <section className="window" aria-label="Profile">
        <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">profile</span></div>
        <div className="window-body stack">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <div className="row" style={{ flexWrap: 'nowrap' }}><MyAvatar size={52} /><div><span className="eyebrow">Signed in as</span><div><strong>{profile ? (profile.displayName && !String(profile.displayName).includes('@') ? profile.displayName : 'Add your name below') : '…'}</strong></div></div></div>
            <span className="row"><Link to="/orders" className="btn-ghost">Orders</Link><button type="button" className="btn-ghost" onClick={signOut}>Sign out</button></span>
          </div>
          <AvatarPicker />
          <NameField />
          <div className="config-grid">
            <div className="config-item"><h3>Campus</h3><p className="config-value">{tenant?.name ?? '…'}</p><div className="row"><Link to="/campus" className="btn-ghost btn-sm">Your campus</Link></div></div>
            <div className="config-item"><h3>Learning system</h3>
              <div className="segmented" role="radiogroup" aria-label="Learning system">
                {([['blackboard', 'Blackboard'], ['canvas', 'Canvas'], ['other', 'Other']] as const).map(([id, label]) => <button key={id} type="button" role="radio" aria-checked={lms === id} aria-pressed={lms === id} onClick={() => setLms(id)}>{label}</button>)}
              </div>
              <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>Changes the steps on the connect screen.</p></div>
            <div className="config-item"><h3>Time zone</h3><p className="config-value mono">{tenant?.timezone ?? '…'}</p></div>
            {prefs && <div className="config-item"><h3>Study hours</h3><p className="config-value">{hour(prefs.wakeHour)} to {hour(prefs.sleepHour)}, {prefs.studyBlockMinutes}-minute blocks</p><p className="muted" style={{ fontSize: 'var(--text-sm)' }}>Editing study hours is coming soon.</p></div>}
          </div>
        </div>
      </section>

      <FeedCard />

      <NicknameCard />

      <SubscribePanel />

      <ArchivedClasses onRestored={reload} />

      <p className="muted about-line" style={{ fontSize: 'var(--text-xs)' }}>About: <HelperBadge /></p>

      <section className="window" aria-label="Your classes">
        <div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title">your-data</span></div>
        <div className="window-body stack">
          <p className="muted">Deleting a class removes the class, its tutor and all of its deadlines. This can't be undone.</p>
          {courses.length === 0 ? <p className="muted">No classes yet.</p> : (
            <ul className="stack" style={{ gap: 'var(--s-2)' }}>
              {courses.map(c => (
                <li key={c.id} className="listing" style={{ gridTemplateColumns: '1fr auto' }}>
                  <span><strong>{c.courseCode || 'New class'}</strong> <span className="muted">{c.title}</span></span>
                  {confirmId === c.id
                    ? <span className="row"><button type="button" className="btn-danger btn-sm" onClick={() => deleteCourse(c.id)}>Yes, delete</button><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirmId(null)}>Keep</button></span>
                    : <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirmId(c.id)} aria-label={`Delete ${c.courseCode || 'class'}`}>Delete</button>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  )
}
