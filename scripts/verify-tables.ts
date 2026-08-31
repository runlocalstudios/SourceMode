/** One-off check: list public tables. Usage: npx tsx scripts/verify-tables.ts */
import { Client, neonConfig } from "@neondatabase/serverless";
import ws from "ws";

neonConfig.webSocketConstructor = ws;
try {
  process.loadEnvFile(".env.local");
} catch {
  /* ambient env */
}

const url = process.env.DATABASE_URL_UNPOOLED || process.env.DATABASE_URL;
if (!url) throw new Error("no DATABASE_URL");

async function main() {
  const client = new Client({ connectionString: url });
  await client.connect();
  const { rows } = await client.query(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name",
  );
  console.log(rows.map((r: { table_name: string }) => r.table_name).join("\n"));
  await client.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
