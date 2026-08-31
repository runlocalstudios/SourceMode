import { getSql } from "../lib/db";

export const dynamic = "force-dynamic";

type CharacterRow = {
  id: string;
  slug: string;
  name: string;
  source_version: string | null;
  created_at: string;
};

async function loadCharacters(): Promise<{ rows: CharacterRow[]; dbOk: boolean }> {
  const sql = getSql();
  if (!sql) return { rows: [], dbOk: false };
  try {
    const rows = (await sql`
      select id, slug, name, source_version, created_at
      from characters
      order by created_at desc
    `) as CharacterRow[];
    return { rows, dbOk: true };
  } catch {
    return { rows: [], dbOk: false };
  }
}

export default async function Dashboard() {
  const { rows, dbOk } = await loadCharacters();

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 720, margin: "3rem auto", padding: "0 1rem" }}>
      <h1>SourceMode</h1>
      <p style={{ color: "#666" }}>Consistent-character video pipeline — control panel</p>

      <h2 style={{ marginTop: "2rem" }}>Characters</h2>
      {!dbOk && <p style={{ color: "#b00" }}>Database unavailable (DATABASE_URL not set or unreachable).</p>}
      {dbOk && rows.length === 0 && <p>No characters yet. Add one via the engine: <code>sourcemode source show gwen</code>.</p>}
      {rows.length > 0 && (
        <table cellPadding={8} style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #ccc" }}>
              <th>Slug</th>
              <th>Name</th>
              <th>Source version</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} style={{ borderBottom: "1px solid #eee" }}>
                <td><code>{c.slug}</code></td>
                <td>{c.name}</td>
                <td>{c.source_version ?? "—"}</td>
                <td>{new Date(c.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
