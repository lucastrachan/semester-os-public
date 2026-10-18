import Svg, { Circle, Path, Rect } from 'react-native-svg'

// From design/logo/semester-os-mark.svg (Designer owns the original; re-copy if it changes).
const MARK_PATH = 'M83 60 C83 49 74 44 63 44 C52 44 44 50 44 58 C44 68 53 70 64 72 C75 74 84 78 84 88 C84 97 75 103 64 103 C53 103 45 98 43 88'

/** The Semester OS mark: indigo tile with the S and three fading dots. Always the brand indigo (not the campus colour). */
export function Logo({ size = 40, decorative = true }: { size?: number; decorative?: boolean }) {
  return (
    <Svg
      viewBox="0 0 128 128" width={size} height={size}
      accessibilityElementsHidden={decorative} importantForAccessibility={decorative ? 'no-hide-descendants' : 'auto'}
      accessibilityLabel={decorative ? undefined : 'Semester OS'}
    >
      <Rect x="4" y="4" width="120" height="120" rx="30" fill="#4F46E5" />
      <Circle cx="31" cy="29" r="4" fill="#FFFFFF" />
      <Circle cx="43" cy="29" r="4" fill="#FFFFFF" opacity={0.6} />
      <Circle cx="55" cy="29" r="4" fill="#FFFFFF" opacity={0.35} />
      <Path d={MARK_PATH} fill="none" stroke="#FFFFFF" strokeWidth={12} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}
