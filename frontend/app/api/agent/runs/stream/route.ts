import { backendFetch } from "@/lib/backend"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function POST(req: Request) {
  const res = await backendFetch("/api/agent/runs/stream", {
    method: "POST",
    body: await req.text(),
    headers: { accept: "text/event-stream" },
  })

  return new Response(res.body, {
    status: res.status,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    },
  })
}
