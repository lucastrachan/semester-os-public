import { EmptyState } from '../components/ui'

export function ComingSoon({ icon, title, body }: { icon: React.ComponentProps<typeof EmptyState>['icon']; title: string; body: string }) {
  return <EmptyState icon={icon} title={title} body={body} />
}
