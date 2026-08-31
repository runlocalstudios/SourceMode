import { NextResponse } from "next/server";
import { getSql } from "../../../lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  let db = false;
  const sql = getSql();
  if (sql) {
    try {
      await sql`select 1`;
      db = true;
    } catch {
      db = false;
    }
  }
  return NextResponse.json({ ok: true, db });
}
