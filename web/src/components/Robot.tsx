import { ROBOT_PARTS, type RobotName } from './robots.generated'

export type { RobotName }

/** Agent robot. Body takes the current text colour (set `color` or put it inside a data-theme element). Decorative by default. */
export default function Robot({ name, size = 48, label, className }: { name: RobotName; size?: number; label?: string; className?: string }) {
  const Parts = ROBOT_PARTS[name]
  return (
    <svg
      viewBox="0 0 96 96" width={size} height={size} fill="none"
      role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}
      className={className} style={{ color: 'var(--accent)', flex: 'none' }}
    >
      <Parts />
    </svg>
  )
}
