export interface RobotProps {
  /** Body colour (use theme.accent). The face plate and eyes stay fixed for contrast. */
  color: string
  size?: number
  /** true when the robot sits next to the agent's name, so screen readers do not read it twice. */
  decorative?: boolean
}
