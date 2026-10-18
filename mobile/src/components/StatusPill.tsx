import { StyleSheet, Text, View } from 'react-native'
import { useTheme } from '../theme/ThemeProvider'

export type AgentStatus = 'ready' | 'building' | 'syncing' | 'error' | 'soon'

const LABEL: Record<AgentStatus, string> = {
  ready: 'Ready', building: 'Building', syncing: 'Syncing', error: 'Needs attention', soon: 'Coming soon',
}

/** Text + dot, never colour alone. */
export function StatusPill({ status, detail }: { status: AgentStatus; detail?: string }) {
  const t = useTheme()
  const dot = status === 'ready' ? t.success : status === 'error' ? t.danger : status === 'soon' ? t.muted : t.accentStrong
  const text = detail ? `${LABEL[status]}, ${detail}` : LABEL[status]
  return (
    <View accessible accessibilityLabel={text} style={[styles.pill, { backgroundColor: t.surface2, borderColor: t.border }]}>
      <View style={[styles.dot, { backgroundColor: dot }]} />
      <Text style={{ color: t.ink, fontSize: 12, fontWeight: '600' }}>{LABEL[status]}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  pill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, borderWidth: StyleSheet.hairlineWidth * 2, alignSelf: 'flex-start' },
  dot: { width: 8, height: 8, borderRadius: 4 },
})
