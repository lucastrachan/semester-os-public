// GENERATED from design/robots/robot-chief-of-staff.svg (Designer owns the SVG). Re-run the generator if it changes.
import Svg, { Circle, Path, Polygon, Rect } from 'react-native-svg'
import type { RobotProps } from './types'

export function RobotChiefOfStaff({ color, size = 48, decorative = true }: RobotProps) {
  return (
    <Svg
      viewBox="0 0 96 96" width={size} height={size} fill="none" color={color}
      accessibilityElementsHidden={decorative} importantForAccessibility={decorative ? 'no-hide-descendants' : 'auto'}
      accessibilityLabel={decorative ? undefined : 'Chief of Staff agent'}
    >
      <Path d="M48 26 V17" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <Polygon points="48.0,1.0 50.4,6.7 56.6,7.2 51.9,11.3 53.3,17.3 48.0,14.1 42.7,17.3 44.1,11.3 39.4,7.2 45.6,6.7" fill="currentColor" stroke="#FFFFFF" strokeWidth="2" strokeLinejoin="round" />
      <Rect x="10" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="80" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="16" y="26" width="64" height="46" rx="16" fill="currentColor" />
      <Rect x="23" y="33" width="50" height="32" rx="11" fill="#FFFFFF" />
      <Circle cx="38" cy="49" r="4.5" fill="#10131A" />
      <Circle cx="58" cy="49" r="4.5" fill="#10131A" />
      <Path d="M41 57 Q48 62 55 57" stroke="#10131A" strokeWidth="3" strokeLinecap="round" />
      <Rect x="28" y="76" width="40" height="16" rx="8" fill="currentColor" />
      <Rect x="40" y="79" width="16" height="10" rx="3" fill="#FFFFFF" />
      <Polygon points="48.0,80.4 49.0,82.7 51.4,82.9 49.5,84.5 50.1,86.9 48.0,85.6 45.9,86.9 46.5,84.5 44.6,82.9 47.0,82.7" fill="#10131A" />
    </Svg>
  )
}
