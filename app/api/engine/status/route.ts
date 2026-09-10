import { NextResponse } from "next/server";
import { fetchEngine, type EngineStatus } from "../../../../lib/engine";

export const dynamic = "force-dynamic";

/** Proxy to the local engine monitor. Unreachable is a 200 with reachable:false — the page renders it. */
export async function GET() {
  const status = await fetchEngine<EngineStatus>("/status");
  if (!status) return NextResponse.json({ reachable: false, status: null });
  return NextResponse.json({ reachable: true, status });
}
