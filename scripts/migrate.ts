/**
 * Applies migrations/NNN_*.sql in order against DATABASE_URL_UNPOOLED.
 * Tracks applied migrations in schema_migrations; safe to re-run (idempotent).
 *
 * Usage: npm run migrate
 */
import { Client, neonConfig } from "@neondatabase/serverless";
import ws from "ws";
import { readdirSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

neonConfig.webSocketConstructor = ws;

// Load .env.local if present (Node 21+ builtin); ignore if missing.
try {
  process.loadEnvFile(".env.local");
} catch {
  /* no .env.local — rely on ambient env */
}

const url = process.env.DATABASE_URL_UNPOOLED || process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL_UNPOOLED (or DATABASE_URL) is not set. Run `vercel env pull .env.local` first.");
  process.exit(1);
}

const migrationsDir = join(dirname(fileURLToPath(import.meta.url)), "..", "migrations");

async function main() {
  const client = new Client({ connectionString: url });
  await client.connect();
  try {
    await client.query(`
      CREATE TABLE IF NOT EXISTS schema_migrations (
        filename text PRIMARY KEY,
        applied_at timestamptz NOT NULL DEFAULT now()
      )
    `);

    const files = readdirSync(migrationsDir)
      .filter((f) => /^\d+_.*\.sql$/.test(f))
      .sort();

    const { rows: appliedRows } = await client.query("SELECT filename FROM schema_migrations");
    const applied = new Set(appliedRows.map((r: { filename: string }) => r.filename));

    for (const file of files) {
      if (applied.has(file)) {
        console.log(`skip  ${file} (already applied)`);
        continue;
      }
      const sqlText = readFileSync(join(migrationsDir, file), "utf8");
      console.log(`apply ${file} ...`);
      await client.query("BEGIN");
      try {
        await client.query(sqlText);
        await client.query("INSERT INTO schema_migrations (filename) VALUES ($1)", [file]);
        await client.query("COMMIT");
        console.log(`ok    ${file}`);
      } catch (err) {
        await client.query("ROLLBACK");
        throw err;
      }
    }
    console.log("migrations up to date");
  } finally {
    await client.end();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
