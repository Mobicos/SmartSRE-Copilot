"use client"

import type { ElementType } from "react"
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  FileText,
  Loader2,
  PlayCircle,
  Wrench,
} from "lucide-react"
import type { NativeAgentEvent } from "@/lib/native-agent-types"
import { cn } from "@/lib/utils"

const EVENT_ICONS: Record<string, ElementType> = {
  run_started: PlayCircle,
  hypothesis: Bot,
  knowledge_context: FileText,
  tool_call: Wrench,
  tool_result: CheckCircle2,
  final_report: FileText,
  complete: CheckCircle2,
  error: AlertTriangle,
}

const EVENT_COLORS: Record<string, string> = {
  run_started: "text-primary",
  hypothesis: "text-blue-500",
  knowledge_context: "text-purple-500",
  tool_call: "text-orange-500",
  tool_result: "text-green-500",
  final_report: "text-primary",
  complete: "text-success",
  error: "text-destructive",
}

interface AgentEventTimelineProps {
  events: NativeAgentEvent[]
  isRunning: boolean
}

export function AgentEventTimeline({ events, isRunning }: AgentEventTimelineProps) {
  if (events.length === 0 && !isRunning) {
    return null
  }

  return (
    <div className="relative">
      {/* Timeline line */}
      {events.length > 0 && (
        <div className="absolute left-4 top-6 bottom-6 w-px bg-border" />
      )}

      <div className="space-y-3">
        {events.map((event, index) => {
          const eventType = event.type || "unknown"
          const Icon = EVENT_ICONS[eventType] || Bot
          const colorClass = EVENT_COLORS[eventType] || "text-muted-foreground"

          return (
            <div key={`${event.id ?? index}`} className="relative flex items-start gap-3 pl-9">
              {/* Icon dot */}
              <div
                className={cn(
                  "absolute left-2.5 top-1 z-10 flex size-3 items-center justify-center rounded-full",
                  eventType === "complete"
                    ? "bg-success"
                    : eventType === "error"
                      ? "bg-destructive"
                      : "bg-primary",
                )}
              >
                <Icon className="size-2 text-primary-foreground" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0 rounded-md border border-border bg-card p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className={cn("text-xs font-medium", colorClass)}>
                    {formatEventType(eventType)}
                  </span>
                  {event.created_at && (
                    <span className="text-[10px] text-muted-foreground">
                      {formatTime(event.created_at)}
                    </span>
                  )}
                </div>
                {event.message && (
                  <p className="mt-1 text-xs text-muted-foreground line-clamp-3">
                    {event.message}
                  </p>
                )}
              </div>
            </div>
          )
        })}

        {/* Running indicator */}
        {isRunning && (
          <div className="relative flex items-start gap-3 pl-9">
            <div className="absolute left-2.5 top-1 z-10 flex size-3 items-center justify-center rounded-full bg-primary animate-pulse" />
            <div className="flex-1 min-w-0 rounded-md border border-dashed border-primary/30 bg-primary/5 p-3">
              <div className="flex items-center gap-2 text-xs text-primary">
                <Loader2 className="size-3 animate-spin" />
                <span>Agent is working...</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function formatEventType(type: string): string {
  const labels: Record<string, string> = {
    run_started: "Run Started",
    hypothesis: "Hypothesis",
    knowledge_context: "Knowledge Context",
    tool_call: "Tool Call",
    tool_result: "Tool Result",
    final_report: "Final Report",
    complete: "Complete",
    error: "Error",
  }
  return labels[type] || type
}

function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  } catch {
    return timestamp
  }
}
