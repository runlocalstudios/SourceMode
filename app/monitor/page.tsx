import type { Metadata } from "next";
import MonitorClient from "./monitor-client";

export const metadata: Metadata = { title: "GPU box — SourceMode" };
export const dynamic = "force-dynamic";

export default function MonitorPage() {
  return <MonitorClient />;
}
