"use client"

import type { ElementType } from "react"
import { useEffect, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Markdown } from "@/components/markdown"
import { AgentEventTimeline } from "./agent-event-timeline"
import { cn } from "@/lib/utils"
import type { NativeAgentEvent } from "@/lib/native-agent-types"

interface AgentRun {
  run_id: string
  status: string
  goal: string
  final_report?: string | null
  error_message?: string | null
  created_at?: string
  updated_at?: string
}

interface AgentRunDetailProps {
  runId: string
}

export function AgentRunDetail({ runId }: AgentRunDetailProps) {
  const [run, setRun] = useState<AgentRun | null>(null)
  const [events, setEvents] = useState<NativeAgentEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [feedbackRating, setFeedbackRating] = useState<string | null>(null)
  const [feedbackComment, setFeedbackComment] = useState("")
  const [submittingFeedback, setSubmittingFeedback] = useState(false)

  useEffect(() => {
    async function loadRun() {
      try {
        const res = await fetch(`/api/agent/runs/${runId}`)
        const data = (await res.json()) as { data?: AgentRun } | AgentRun
        setRun(data && typeof data === "object" && "data" in data ? data.data || null : (data as AgentRun))
      } catch (err) {
        toast.error("Failed to load run")
      }
    }

    async function loadEvents() {
      try {
        const res = await fetch(`/api/agent/runs/${runId}/events`)
        const data = (await res.json()) as { data?: NativeAgentEvent[] } | NativeAgentEvent[]
        setEvents(Array.isArray(data) ? data : data.data || [])
      } catch (err) {
        toast.error("Failed to load events")
      } finally {
        setLoading(false)
      }
    }

    void loadRun()
    void loadEvents()
  }, [runId])

  async function submitFeedback(rating: string) {
    setFeedbackRating(rating)
    setSubmittingFeedback(true)
    try {
      const res = await fetch(`/api/agent/runs/${runId}/feedback`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ rating, comment: feedbackComment || undefined }),
      })
      if (res.ok) {
        toast.success("Feedback submitted")
      } else {
        toast.error("Failed to submit feedback")
      }
    } catch (err) {
      toast.error("Failed to submit feedback")
    } finally {
      setSubmittingFeedback(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <XCircle className="size-12 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Run not found</p>
        <Button asChild variant="outline" size="sm">
          <Link href="/agent/history">Back to History</Link>
        </Button>
      </div>
    )
  }

  const statusConfig: Record<string, { icon: ElementType; label: string; className: string }> = {
    completed: {
      icon: CheckCircle2,
      label: "Done",
      className: "text-success bg-success/10 border-success/20",
    },
    running: {
      icon: Loader2,
      label: "Running",
      className: "text-primary bg-primary/10 border-primary/20",
    },
    failed: {
      icon: XCircle,
      label: "Failed",
      className: "text-destructive bg-destructive/10 border-destructive/20",
    },
  }

  const status = statusConfig[run.status] || statusConfig.completed
  const StatusIcon = status.icon

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-4xl px-4 py-6 md:px-6">
        {/* Header */}
        <div className="mb-4">
          <Button asChild variant="ghost" size="sm" className="mb-3 -ml-2">
            <Link href="/agent/history">
              <ArrowLeft className="mr-1 size-4" />
              Back
            </Link>
          </Button>

          <div className="flex items-center gap-2">
            <StatusIcon
              className={cn("size-4", run.status === "running" && "animate-spin")}
            />
            <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", status.className)}>
              {status.label}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {run.run_id.slice(0, 8)}
            </span>
          </div>

          <p className="mt-2 text-base font-medium">{run.goal}</p>

          {run.error_message && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>{run.error_message}</span>
            </div>
          )}
        </div>

        {/* Events */}
        {events.length > 0 && (
          <div className="mb-4">
            <AgentEventTimeline events={events} isRunning={run.status === "running"} />
          </div>
        )}

        {/* Report */}
        {run.final_report && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Report</CardTitle>
            </CardHeader>
            <CardContent>
              <Markdown content={run.final_report} />
            </CardContent>
          </Card>
        )}

        {/* Feedback */}
        {run.status === "completed" && (
          <Card>
            <CardContent className="pt-4">
              {feedbackRating ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="size-4 text-success" />
                  <span>Thanks!</span>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("helpful")} disabled={submittingFeedback}>
                      <ThumbsUp className="mr-1 size-3" />
                      Helpful
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("not_helpful")} disabled={submittingFeedback}>
                      <ThumbsDown className="mr-1 size-3" />
                      Not Helpful
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("wrong")} disabled={submittingFeedback}>
                      <XCircle className="mr-1 size-3" />
                      Wrong
                    </Button>
                  </div>
                  <Textarea
                    placeholder="Comment (optional)"
                    value={feedbackComment}
                    onChange={(e) => setFeedbackComment(e.target.value)}
                    disabled={submittingFeedback}
                    className="min-h-16"
                  />
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
