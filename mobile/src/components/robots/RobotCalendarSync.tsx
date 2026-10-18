// GENERATED from design/robots/robot-calendar-sync.svg (Designer owns the SVG). Re-run the generator if it changes.
import Svg, { Circle, Path, Rect } from 'react-native-svg'
import type { RobotProps } from './types'

export function RobotCalendarSync({ color, size = 48, decorative = true }: RobotProps) {
  return (
    <Svg
      viewBox="0 0 96 96" width={size} height={size} fill="none" color={color}
      accessibilityElementsHidden={decorative} importantForAccessibility={decorative ? 'no-hide-descendants' : 'auto'}
      accessibilityLabel={decorative ? undefined : 'Calendar Sync agent'}
    >
      <Rect x="29" y="13" width="7" height="18" rx="3.5" fill="currentColor" stroke="#FFFFFF" strokeWidth="2" strokeLinejoin="round" />
      <Rect x="60" y="13" width="7" height="18" rx="3.5" fill="currentColor" stroke="#FFFFFF" strokeWidth="2" strokeLinejoin="round" />
      <Rect x="10" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="80" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="16" y="26" width="64" height="46" rx="16" fill="currentColor" />
      <Rect x="23" y="33" width="50" height="32" rx="11" fill="#FFFFFF" />
      <Circle cx="38" cy="49" r="4.5" fill="#10131A" />
      <Circle cx="58" cy="49" r="4.5" fill="#10131A" />
      <Path d="M41 57 Q48 62 55 57" stroke="#10131A" strokeWidth="3" strokeLinecap="round" />
      <Rect x="28" y="76" width="40" height="16" rx="8" fill="currentColor" />
      <Rect x="40" y="79" width="16" height="10" rx="3" fill="#FFFFFF" />
      <Path d="M42 82 H54" stroke="#10131A" strokeWidth="1.6" />
      <Circle cx="44.5" cy="85.6" r="1" fill="#10131A" />
      <Circle cx="48" cy="85.6" r="1" fill="#10131A" />
      <Circle cx="51.5" cy="85.6" r="1" fill="#10131A" />
    </Svg>
  )
}
