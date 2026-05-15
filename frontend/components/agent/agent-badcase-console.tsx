"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  UploadCloud,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { apiClient } from "@/lib/api-client"
import type { NativeAgentBadcase } from "@/lib/native-agent-types"
import { cn } from "@/lib/utils"

const REVIEW_CONFIG: Record<string, { label: string; className: string }> = {
  pending: {
    label: "待确认",
    className: "border-amber-500/20 bg-amber-500/10 text-amber-600",
  },
  confirmed: {
    label: "已确认",
    className: "border-success/20 bg-success/10 text-success",
  },
  rejected: {
    label: "已驳回",
    className: "border-muted bg-muted text-muted-foreground",
  },
}

export function AgentBadcaseConsole() {
  const [badcases, setBadcases] = useState<NativeAgentBadcase[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [submittingId, setSubmittingId] = useState<string | null>(null)
  const [promotingId, setPromotingId] = useState<string | null>(null)

  useEffect(() => {
    void loadBadcases()
  }, [])

  async function loadBadcases() {
    setError("")
    setLoading(true)
    try {
      const data = await apiClient<NativeAgentBadcase[]>("/api/agent/badcases?limit=100", {
        retries: 1,
      })
      setBadcases(Array.isArray(data) ? data : [])
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载 Badcase 失败"
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  async function reviewBadcase(feedbackId: string, reviewStatus: "confirmed" | "rejected") {
    setSubmittingId(feedbackId)
    try {
      const updated = await apiClient<NativeAgentBadcase>(
        `/api/agent/badcases/${feedbackId}/review`,
        {
          method: "POST",
          body: JSON.stringify({
            review_status: reviewStatus,
            review_note: notes[feedbackId] || undefined,
          }),
        },
      )
      setBadcases((current) =>
        current.map((item) => (item.feedback_id === feedbackId ? { ...item, ...updated } : item)),
      )
      toast.success(reviewStatus === "confirmed" ? "Badcase 已确认" : "Badcase 已驳回")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新 Badcase 失败")
    } finally {
      setSubmittingId(null)
    }
  }

  async function promoteBadcase(feedbackId: string) {
    setPromotingId(feedbackId)
    try {
      const result = await apiClient<{
        badcase?: NativeAgentBadcase
        filename?: string
        indexing?: { taskId?: string; status?: string }
      }>(`/api/agent/badcases/${feedbackId}/promote-knowledge`, {
        method: "POST",
        body: "{}",
      })
      if (result.badcase) {
        setBadcases((current) =>
          current.map((item) =>
            item.feedback_id === feedbackId ? { ...item, ...result.badcase } : item,
          ),
        )
      }
      toast.success("知识补充已入队")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "知识补充失败")
    } finally {
      setPromotingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
        <div className="mb-6 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Badcase</h1>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadBadcases()}
            disabled={loading}
          >
            <RefreshCw className="mr-1 size-3" />
            刷新
          </Button>
        </div>

        {error ? (
          <Card className="border-destructive/30">
            <CardContent className="flex items-center gap-3 py-6 text-sm text-destructive">
              <AlertTriangle className="size-5" />
              {error}
            </CardContent>
          </Card>
        ) : badcases.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <CheckCircle2 className="mb-3 size-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无 Badcase</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {badcases.map((badcase) => {
              const reviewStatus = badcase.review_status || "pending"
              const reviewConfig = REVIEW_CONFIG[reviewStatus] || REVIEW_CONFIG.pending
              const isSubmitting = submittingId === badcase.feedback_id
              const isPromoting = promotingId === badcase.feedback_id
              const canPromote =
                reviewStatus === "confirmed" &&
                (!badcase.knowledge_status || badcase.knowledge_status === "not_promoted")

              return (
                <Card key={badcase.feedback_id}>
                  <CardHeader className="pb-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <CardTitle className="line-clamp-1 text-base">
                          {badcase.run?.goal || badcase.run_id}
                        </CardTitle>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <span
                            className={cn(
                              "rounded-full border px-2 py-0.5 font-medium",
                              reviewConfig.className,
                            )}
                          >
                            {reviewConfig.label}
                          </span>
                          <span className="rounded-full bg-muted px-2 py-0.5">
                            {badcase.rating}
                          </span>
                          {badcase.created_at && (
                            <span className="flex items-center gap-1">
                              <Clock className="size-3" />
                              {formatDate(badcase.created_at)}
                            </span>
                          )}
                          {badcase.knowledge_status &&
                            badcase.knowledge_status !== "not_promoted" && (
                              <span className="rounded-full bg-muted px-2 py-0.5">
                                {badcase.knowledge_status}
                              </span>
                            )}
                        </div>
                      </div>
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/agent/${badcase.run_id}`}>查看运行</Link>
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {badcase.comment && (
                      <BadcaseBlock label="反馈备注" value={badcase.comment} />
                    )}
                    {badcase.correction && (
                      <BadcaseBlock label="修正建议" value={badcase.correction} />
                    )}
                    {badcase.original_report && (
                      <BadcaseBlock label="原始报告" value={badcase.original_report} muted />
                    )}
                    {badcase.review_note && (
                      <BadcaseBlock label="审核备注" value={badcase.review_note} />
                    )}
                    <Textarea
                      placeholder="审核备注（可选）"
                      value={notes[badcase.feedback_id] ?? ""}
                      onChange={(event) =>
                        setNotes((current) => ({
                          ...current,
                          [badcase.feedback_id]: event.target.value,
                        }))
                      }
                      disabled={isSubmitting}
                      className="min-h-16"
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        onClick={() => void reviewBadcase(badcase.feedback_id, "confirmed")}
                        disabled={isSubmitting}
                      >
                        {isSubmitting ? (
                          <Loader2 className="mr-1 size-3 animate-spin" />
                        ) : (
                          <CheckCircle2 className="mr-1 size-3" />
                        )}
                        确认
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void reviewBadcase(badcase.feedback_id, "rejected")}
                        disabled={isSubmitting}
                      >
                        <XCircle className="mr-1 size-3" />
                        驳回
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void promoteBadcase(badcase.feedback_id)}
                        disabled={!canPromote || isPromoting}
                      >
                        {isPromoting ? (
                          <Loader2 className="mr-1 size-3 animate-spin" />
                        ) : (
                          <UploadCloud className="mr-1 size-3" />
                        )}
                        补充知识
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function BadcaseBlock({
  label,
  value,
  muted = false,
}: {
  label: string
  value: string
  muted?: boolean
}) {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3">
      <div className="text-[10px] font-medium uppercase text-muted-foreground">{label}</div>
      <p
        className={cn(
          "mt-1 line-clamp-5 whitespace-pre-wrap text-xs",
          muted ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {value}
      </p>
    </div>
  )
}

function formatDate(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleString("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return timestamp
  }
}
