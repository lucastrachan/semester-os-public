// Write deadlines to the phone's own calendar. Never silent: the caller asks the student first, and the OS
// permission prompt appears here. Uses the legacy expo-calendar API, because the new one is stubbed in Expo Go.
import { Platform } from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import * as Calendar from 'expo-calendar/legacy'
import type { Assignment } from 'shared/types'

const MAP_KEY = 'semesteros.phoneEvents.v1' // assignmentId -> device event id, so re-adding never duplicates
const CAL_TITLE = 'Semester OS'

async function readMap(): Promise<Record<string, string>> {
  try { return JSON.parse((await AsyncStorage.getItem(MAP_KEY)) ?? '{}') } catch { return {} }
}

export const addable = (a: Assignment) => !!a.dueDate && !a.done

export async function countNew(list: Assignment[]): Promise<number> {
  const m = await readMap()
  return list.filter((a) => addable(a) && !m[a.id]).length
}

async function targetCalendarId(calendarColor: string): Promise<string> {
  if (Platform.OS === 'ios') {
    const def = await Calendar.getDefaultCalendarAsync()
    if (def.allowsModifications) return def.id
  }
  const cals = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT)
  const ours = cals.find((c) => c.title === CAL_TITLE && c.allowsModifications)
  if (ours) return ours.id
  const writable = cals.find((c) => c.allowsModifications)
  if (Platform.OS === 'ios' && writable) return writable.id
  const source = Platform.OS === 'ios'
    ? writable?.source ?? cals[0]?.source
    : { isLocalAccount: true, name: CAL_TITLE, type: Calendar.SourceType.LOCAL } as Calendar.Source
  return Calendar.createCalendarAsync({
    title: CAL_TITLE, color: calendarColor, entityType: Calendar.EntityTypes.EVENT,
    sourceId: (source as Calendar.Source | undefined)?.id, source: source as Calendar.Source,
    name: CAL_TITLE, ownerAccount: 'personal', accessLevel: Calendar.CalendarAccessLevel.OWNER,
  })
}

/** Returns { added, denied }. Requests permission (OS prompt) only when called. */
export async function addToPhoneCalendar(list: Assignment[], calendarColor = '#4F46E5'): Promise<{ added: number; denied: boolean }> {
  const perm = await Calendar.requestCalendarPermissionsAsync()
  if (perm.status !== 'granted') return { added: 0, denied: true }
  const calId = await targetCalendarId(calendarColor)
  const map = await readMap()
  let added = 0
  for (const a of list.filter((x) => addable(x) && !map[x.id])) {
    const [y, mo, d] = a.dueDate!.split('-').map(Number)
    const title = `${a.courseCode ? `[${a.courseCode}] ` : ''}${a.title}`
    const notes = [a.type, a.dateSource === 'resolved' ? 'Date estimated from the syllabus; check it.' : '', a.notes].filter(Boolean).join('\n')
    let start: Date, end: Date, allDay = false
    if (a.dueTime) {
      const [hh, mm] = a.dueTime.split(':').map(Number)
      end = new Date(y, mo - 1, d, hh, mm)
      start = new Date(end.getTime() - 30 * 60000) // 30 minutes ending at the due time, like the feed
    } else {
      start = new Date(y, mo - 1, d)
      end = new Date(y, mo - 1, d + 1)
      allDay = true
    }
    try {
      map[a.id] = await Calendar.createEventAsync(calId, { title, notes, startDate: start, endDate: end, allDay })
      added++
    } catch { /* skip an item that fails; the rest still go in */ }
  }
  await AsyncStorage.setItem(MAP_KEY, JSON.stringify(map))
  return { added, denied: false }
}
