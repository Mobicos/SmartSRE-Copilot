import { Loader2 } from "lucide-react"

export default function AgentBadcasesLoading() {
  return (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="size-6 animate-spin text-muted-foreground" />
    </div>
  )
}
