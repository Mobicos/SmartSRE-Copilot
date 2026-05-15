import { NextResponse } from "next/server"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"
import { backendErrorStatus, backendFetch } from "@/lib/backend"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

interface RouteContext {
  params: Promise<{ sceneId: string }>
}

export async function DELETE(_req: Request, context: RouteContext) {
  const { sceneId } = await context.params
  try {
    const res = await backendFetch(`/api/scenes/${encodeURIComponent(sceneId)}`, {
      method: "DELETE",
    })
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
