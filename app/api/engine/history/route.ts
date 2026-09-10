import { NextResponse } from "next/server";
import { fetchEngine, type HistoryPoint } from "../../../../lib/engine";

export const dynamic = "force-dynamic";

export async function GET() {
  const data = await fetchEngine<{ points: HistoryPoint[] }>("/history?max_points=360");
  if (!data) return NextResponse.json({ reachable: false, points: [] });
  return NextResponse.json({ reachable: true, points: data.points });
}
