import { View } from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useAuth } from '../../../src/auth/AuthContext'
import { SkeletonCards } from '../../../src/components/Skeleton'
import { TabScreen } from '../../../src/components/TabScreen'
import { Card, mono, radius, space, T } from '../../../src/components/ui'
import { useTheme } from '../../../src/theme/ThemeProvider'

function SetupRow({ label, value, action }: { label: string; value?: string; action: string }) {
  const t = useTheme()
  const set = !!value
  return (
    <View style={{ minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: space.md }} accessible accessibilityLabel={`${label}: ${set ? value : action}`}>
      <View style={{ flex: 1 }}>
        <T kind="body" color={set ? t.ink : t.muted}>{label}</T>
        <T kind="footnote" color={t.muted} numberOfLines={2}>{set ? value : action}</T>
      </View>
      <Ionicons name={set ? 'checkmark-circle' : 'chevron-forward'} size={set ? 22 : 18} color={set ? t.success : t.muted} />
    </View>
  )
}

export default function School() {
  const t = useTheme()
  const { me } = useAuth()
  const tenant = me?.tenant
  if (!tenant) return <TabScreen><SkeletonCards count={2} /></TabScreen>
  const tutoring = tenant.tutoringResources?.length ? `${tenant.tutoringResources.length} resources` : undefined
  const pickups = tenant.pickupSpots?.length ? tenant.pickupSpots.join(', ') : undefined
  const lms = tenant.lms && tenant.lms.type !== 'other' ? tenant.lms.type : undefined

  return (
    <TabScreen>
      <Card style={{ gap: space.sm, backgroundColor: t.accentTint, borderLeftColor: t.accent, borderLeftWidth: 4 }}>
        <T kind="title">{tenant.name}</T>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.xs }}>
          {tenant.domains.map((d) => (
            <View key={d} style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.control, backgroundColor: t.surface, borderColor: t.border, borderWidth: 1 }}>
              <T kind="caption" style={{ fontFamily: mono }}>{d}</T>
            </View>
          ))}
          {tenant.autoCreated ? (
            <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: t.accent }}>
              <T kind="caption" color={t.accentInk} style={{ fontWeight: '600' }}>Auto-created</T>
            </View>
          ) : null}
        </View>
        {tenant.colorStatus === 'placeholder' || tenant.colorStatus === 'needs_review' || (!tenant.colorStatus && tenant.autoCreated) ? (
          <T kind="footnote" color={t.muted}>
            {tenant.colorStatus === 'needs_review' ? "We detected this colour from your school's website. It is being reviewed." : "Placeholder colour, not the school's official brand. We're finding the real one."}
          </T>
        ) : null}
      </Card>

      <T kind="label" color={t.muted}>{"What's set up"}</T>
      <Card style={{ gap: space.xs }}>
        <SetupRow label="Time zone" value={tenant.timezone} action="Not set" />
        <SetupRow label="Learning system" value={lms} action="Not connected yet" />
        <SetupRow label="Tutoring" value={tutoring} action="No tutoring resources yet" />
        <SetupRow label="Pickup spots" value={pickups} action="No pickup spots yet" />
        <SetupRow label="Marketplace" value={tenant.openToNetwork ? 'Open to other campuses' : undefined} action="Campus only" />
      </Card>

      <T kind="label" color={t.muted}>Next steps</T>
      <Card style={{ gap: space.xs }}>
        <SetupRow label="1. Add your classes" action="Agents tab, then Add a syllabus" />
        <SetupRow label="2. Check your calendar" action="Deadlines appear on the Calendar tab" />
      </Card>
    </TabScreen>
  )
}
