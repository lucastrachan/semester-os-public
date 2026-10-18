import { ReactNode, useState } from 'react'
import {
  ActivityIndicator, Platform, Pressable, StyleSheet, Text, TextInput, TextInputProps, View, ViewStyle,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../theme/ThemeProvider'

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 }
export const radius = { card: 16, control: 12 }
export const mono = Platform.select({ ios: 'Menlo', default: 'monospace' })

/** Body text that respects Dynamic Type / Android font scale (allowFontScaling stays on). */
export function T({
  children, kind = 'body', color, style, numberOfLines,
}: {
  children: ReactNode
  kind?: 'caption' | 'footnote' | 'body' | 'callout' | 'title' | 'large' | 'label'
  color?: string
  style?: object
  numberOfLines?: number
}) {
  const t = useTheme()
  return (
    <Text
      numberOfLines={numberOfLines}
      maxFontSizeMultiplier={kind === 'large' ? 1.3 : 1.8} // scales with Dynamic Type / font size, capped so layouts hold
      accessibilityRole={kind === 'title' || kind === 'large' || kind === 'label' ? 'header' : undefined}
      style={[{ color: color ?? t.ink }, textStyles[kind], style]}
    >
      {children}
    </Text>
  )
}
const textStyles = StyleSheet.create({
  caption: { fontSize: 12, lineHeight: 16 },
  footnote: { fontSize: 13, lineHeight: 18 },
  body: { fontSize: 16, lineHeight: 22 },
  callout: { fontSize: 17, lineHeight: 24, fontWeight: '600' },
  title: { fontSize: 22, lineHeight: 28, fontWeight: '700' },
  large: { fontSize: 30, lineHeight: 36, fontWeight: '700' },
  label: { fontSize: 12, lineHeight: 16, fontWeight: '600', letterSpacing: 0.6, textTransform: 'uppercase' },
})

export function Button({
  title, onPress, variant = 'primary', loading, disabled, style,
}: {
  title: string
  onPress: () => void
  variant?: 'primary' | 'secondary' | 'plain'
  loading?: boolean
  disabled?: boolean
  style?: ViewStyle
}) {
  const t = useTheme()
  const isPrimary = variant === 'primary'
  const bg = isPrimary ? t.accent : variant === 'secondary' ? t.accentTint : 'transparent'
  const fg = isPrimary ? t.accentInk : t.accentStrong
  const off = disabled || loading
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      onPress={onPress}
      disabled={off}
      android_ripple={Platform.OS === 'android' ? { color: t.border } : undefined}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, opacity: off ? 0.5 : Platform.OS === 'ios' && pressed ? 0.7 : 1 },
        style,
      ]}
    >
      {loading ? <ActivityIndicator color={fg} /> : <Text style={[styles.buttonText, { color: fg }]}>{title}</Text>}
    </Pressable>
  )
}

export function TextField({ label, error, ...props }: TextInputProps & { label: string; error?: string }) {
  const t = useTheme()
  const [focus, setFocus] = useState(false)
  return (
    <View style={{ gap: space.xs }}>
      <T kind="footnote" color={t.muted} style={{ fontWeight: '600' }}>{label}</T>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={t.muted}
        selectionColor={t.accent}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        {...props}
        style={[
          styles.input,
          {
            color: t.ink,
            backgroundColor: t.surface,
            borderColor: error ? t.danger : focus ? t.accentStrong : t.border,
            borderWidth: focus ? 2 : StyleSheet.hairlineWidth * 2,
          },
        ]}
      />
    </View>
  )
}

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const t = useTheme()
  return (
    <View
      style={[
        styles.card,
        { backgroundColor: t.surface, borderColor: t.border },
        Platform.OS === 'android' ? { elevation: 1 } : null,
        style,
      ]}
    >
      {children}
    </View>
  )
}

export function EmptyState({
  icon, title, body, actionLabel, onAction,
}: {
  icon: keyof typeof Ionicons.glyphMap
  title: string
  body: string
  actionLabel?: string
  onAction?: () => void
}) {
  const t = useTheme()
  return (
    <View style={styles.empty} accessible accessibilityLabel={`${title}. ${body}`}>
      <View style={[styles.iconTile, { backgroundColor: t.accentTint }]}>
        <Ionicons name={icon} size={30} color={t.accentStrong} />
      </View>
      <T kind="title" style={{ textAlign: 'center' }}>{title}</T>
      <T kind="body" color={t.muted} style={{ textAlign: 'center', maxWidth: 320 }}>{body}</T>
      {actionLabel && onAction ? <Button title={actionLabel} onPress={onAction} style={{ alignSelf: 'stretch', marginTop: space.sm }} /> : null}
    </View>
  )
}

export function ErrorNote({ message }: { message: string }) {
  const t = useTheme()
  return (
    <View accessibilityRole="alert" style={[styles.errorNote, { borderColor: t.danger, backgroundColor: t.surface }]}>
      <Ionicons name="alert-circle" size={18} color={t.danger} />
      <Text style={{ color: t.ink, flex: 1, fontSize: 14, lineHeight: 20 }}>{message}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  button: { minHeight: 50, borderRadius: radius.control, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.lg },
  buttonText: { fontSize: 17, fontWeight: '600' },
  input: { minHeight: 50, borderRadius: radius.control, paddingHorizontal: space.md, fontSize: 17 },
  card: { borderRadius: radius.card, borderWidth: StyleSheet.hairlineWidth * 2, padding: space.lg },
  empty: { alignItems: 'center', gap: space.md, paddingHorizontal: space.xl, paddingVertical: space.xxl },
  iconTile: { width: 64, height: 64, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  errorNote: { flexDirection: 'row', gap: space.sm, alignItems: 'flex-start', padding: space.md, borderRadius: radius.control, borderWidth: 1 },
})
