import { NextResponse } from "next/server";
import { engineUrl } from "../../../../../lib/engine";

export const dynamic = "force-dynamic";

/**
 * Proxy for the engine's /assets review API. The browser never talks to the
 * engine directly; on Vercel there is no engine and this answers 503.
 * GET passes the query string through (candidate lists, images, thumbnails);
 * POST forwards a JSON body (picks, place).
 */
async function forward(request: Request, path: string[] | undefined, method: "GET" | "POST") {
  const url = new URL(request.url);
  const target = `${engineUrl()}/assets${path?.length ? "/" + path.map(encodeURIComponent).join("/") : ""}${url.search}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), method === "POST" ? 120_000 : 15_000);
  try {
    const res = await fetch(target, {
      method,
      signal: ctrl.signal,
      cache: "no-store",
      headers: method === "POST" ? { "content-type": "application/json" } : undefined,
      body: method === "POST" ? await request.text() : undefined,
    });
    const type = res.headers.get("content-type") ?? "application/octet-stream";
    if (type.startsWith("image/")) {
      return new Response(await res.arrayBuffer(), {
        status: res.status,
        headers: { "content-type": type, "cache-control": "private, max-age=300" },
      });
    }
    return new Response(await res.text(), { status: res.status, headers: { "content-type": type } });
  } catch {
    return NextResponse.json({ reachable: false, error: "engine unreachable" }, { status: 503 });
  } finally {
    clearTimeout(timer);
  }
}

export async function GET(request: Request, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path } = await params;
  return forward(request, path, "GET");
}

export async function POST(request: Request, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path } = await params;
  return forward(request, path, "POST");
}
