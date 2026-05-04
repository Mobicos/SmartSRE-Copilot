import { AgentRunDetail } from "@/components/agent/agent-run-detail"

interface Props {
  params: Promise<{ runId: string }>
}

export default async function AgentRunDetailPage({ params }: Props) {
  const { runId } = await params
  return <AgentRunDetail runId={runId} />
}
