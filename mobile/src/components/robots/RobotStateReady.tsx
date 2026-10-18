// GENERATED from design/robots/robot-state-ready.svg (Designer owns the SVG). Re-run the generator if it changes.
import Svg, { Circle, Path, Rect } from 'react-native-svg'
import type { RobotProps } from './types'

export function RobotStateReady({ color, size = 48, decorative = true }: RobotProps) {
  return (
    <Svg
      viewBox="0 0 96 96" width={size} height={size} fill="none" color={color}
      accessibilityElementsHidden={decorative} importantForAccessibility={decorative ? 'no-hide-descendants' : 'auto'}
      accessibilityLabel={decorative ? undefined : 'Agent robot, ready'}
    >
      <Path d="M48 26 V15" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <Circle cx="48" cy="11" r="5" fill="currentColor" />
      <Rect x="10" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="80" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="16" y="26" width="64" height="46" rx="16" fill="currentColor" />
      <Rect x="23" y="33" width="50" height="32" rx="11" fill="#FFFFFF" />
      <Path d="M33 51 Q38 44 43 51 M53 51 Q58 44 63 51" stroke="#10131A" strokeWidth="3" strokeLinecap="round" />
      <Path d="M40 56 Q48 64 56 56" stroke="#10131A" strokeWidth="3" strokeLinecap="round" />
      <Rect x="28" y="76" width="40" height="16" rx="8" fill="currentColor" />
      <Rect x="40" y="79" width="16" height="10" rx="3" fill="#FFFFFF" />
      <Circle cx="78" cy="78" r="12" fill="#059669" stroke="#FFFFFF" strokeWidth="2.5" />
      <Path d="M72 78.5 L76.3 82.5 L84 74.5" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}
