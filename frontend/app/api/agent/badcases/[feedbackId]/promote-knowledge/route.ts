import { NextResponse } from "next/server"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"
import { backendErrorStatus, backendFetch } from "@/lib/backend"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function POST(
  req: Request,
  { params }: { params: Promise<{ feedbackId: string }> },
) {
  const { feedbackId } = await params
  try {
    const res = await backendFetch(
      `/api/agent/badcases/${encodeURIComponent(feedbackId)}/promote-knowledge`,
      {
        method: "POST",
        body: await req.text(),
      },
    )
    const payload = await readPayload(res)
    return NextResponse.json(unwrapBackendEnvelope(payload), { status: res.status })
  } catch (err) {
    return NextResponse.json(
      { error: (err as Error).message ?? "backend unreachable" },
      { status: backendErrorStatus(err) },
    )
  }
}

async function readPayload(res: Response): Promise<unknown> {
  const text = await res.text()
  try {
    return JSON.parse(text)
  } catch {
    return { raw: text }
  }
}
