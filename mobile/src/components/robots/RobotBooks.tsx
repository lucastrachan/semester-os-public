// GENERATED from design/robots/robot-books.svg (Designer owns the SVG). Re-run the generator if it changes.
import Svg, { Circle, Path, Rect } from 'react-native-svg'
import type { RobotProps } from './types'

export function RobotBooks({ color, size = 48, decorative = true }: RobotProps) {
  return (
    <Svg
      viewBox="0 0 96 96" width={size} height={size} fill="none" color={color}
      accessibilityElementsHidden={decorative} importantForAccessibility={decorative ? 'no-hide-descendants' : 'auto'}
      accessibilityLabel={decorative ? undefined : 'Books agent'}
    >
      <Path d="M48 26 C42 20 32 19 22 21 V8 C32 6 42 8 48 13 C54 8 64 6 74 8 V21 C64 19 54 20 48 26 Z" fill="currentColor" stroke="#FFFFFF" strokeWidth="2" strokeLinejoin="round" />
      <Path d="M48 13 V25" stroke="#FFFFFF" strokeWidth="1.8" />
      <Rect x="10" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="80" y="42" width="6" height="14" rx="3" fill="currentColor" />
      <Rect x="16" y="26" width="64" height="46" rx="16" fill="currentColor" />
      <Rect x="23" y="33" width="50" height="32" rx="11" fill="#FFFFFF" />
      <Circle cx="38" cy="49" r="4.5" fill="#10131A" />
      <Circle cx="58" cy="49" r="4.5" fill="#10131A" />
      <Path d="M41 57 Q48 62 55 57" stroke="#10131A" strokeWidth="3" strokeLinecap="round" />
      <Rect x="28" y="76" width="40" height="16" rx="8" fill="currentColor" />
      <Rect x="40" y="79" width="16" height="10" rx="3" fill="#FFFFFF" />
      <Path d="M44 81.5 H52 M44 84 H52 M44 86.5 H49" stroke="#10131A" strokeWidth="1.5" strokeLinecap="round" />
    </Svg>
  )
}
