// GENERATED from design/robots/robot-class-tutor.svg (Designer owns the SVG). Re-run the generator if it changes.
import Svg, { Circle, Path, Polygon, Rect } from 'react-native-svg'
import type { RobotProps } from './types'

export function RobotClassTutor({ color, size = 48, decorative = true }: RobotProps) {
  return (
    <Svg
      viewBox="0 0 96 96" width={size} height={size} fill="none" color={color}
      accessibilityElementsHidden={decorative} importantForAccessibility={decorative ? 'no-hide-descendants' : 'auto'}
      accessibilityLabel={decorative ? undefined : 'Class tutor agent'}
    >
      <Path d="M32 19 V26 Q48 33 64 26 V19" fill="currentColor" stroke="#FFFFFF" strokeWidth="2" strokeLinejoin="round" />
      <Polygon points="48,4 78,15 48,26 18,15" fill="currentColor" stroke="#FFFFFF" strokeWidth="2" strokeLinejoin="round" />
      <Path d="M74 16.5 V28" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <Circle cx="74" cy="30" r="3" fill="currentColor" />
      <Rect x="10" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="80" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="16" y="26" width="64" height="46" rx="16" fill="currentColor" />
      <Rect x="23" y="33" width="50" height="32" rx="11" fill="#FFFFFF" />
      <Circle cx="38" cy="49" r="4.5" fill="#10131A" />
      <Circle cx="58" cy="49" r="4.5" fill="#10131A" />
      <Path d="M41 57 Q48 62 55 57" stroke="#10131A" strokeWidth="3" strokeLinecap="round" />
      <Rect x="28" y="76" width="40" height="16" rx="8" fill="currentColor" />
      <Rect x="40" y="79" width="16" height="10" rx="3" fill="#FFFFFF" />
      <Path d="M43 84 H53 M48 81.5 V86.5" stroke="#10131A" strokeWidth="1.8" strokeLinecap="round" />
    </Svg>
  )
}
