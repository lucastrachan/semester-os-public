// GENERATED from design/robots/robot-state-error.svg (Designer owns the SVG). Re-run the generator if it changes.
import Svg, { Circle, Path, Rect } from 'react-native-svg'
import type { RobotProps } from './types'

export function RobotStateError({ color, size = 48, decorative = true }: RobotProps) {
  return (
    <Svg
      viewBox="0 0 96 96" width={size} height={size} fill="none" color={color}
      accessibilityElementsHidden={decorative} importantForAccessibility={decorative ? 'no-hide-descendants' : 'auto'}
      accessibilityLabel={decorative ? undefined : 'Agent robot, error'}
    >
      <Path d="M48 26 V15" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <Circle cx="48" cy="11" r="5" fill="currentColor" />
      <Rect x="10" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="80" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="16" y="26" width="64" height="46" rx="16" fill="currentColor" />
      <Rect x="23" y="33" width="50" height="32" rx="11" fill="#FFFFFF" />
      <Circle cx="38" cy="50" r="4.5" fill="#10131A" />
      <Circle cx="58" cy="50" r="4.5" fill="#10131A" />
      <Path d="M32 45 L43 42 M64 45 L53 42" stroke="#10131A" strokeWidth="2.6" strokeLinecap="round" />
      <Path d="M41 60 Q44.5 56 48 59 Q51.5 62 55 58" stroke="#10131A" strokeWidth="3" strokeLinecap="round" />
      <Rect x="28" y="76" width="40" height="16" rx="8" fill="currentColor" />
      <Rect x="40" y="79" width="16" height="10" rx="3" fill="#FFFFFF" />
      <Circle cx="78" cy="78" r="12" fill="#E11D48" stroke="#FFFFFF" strokeWidth="2.5" />
      <Path d="M78 71.5 V79" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" />
      <Circle cx="78" cy="83.5" r="1.8" fill="#FFFFFF" />
    </Svg>
  )
}
