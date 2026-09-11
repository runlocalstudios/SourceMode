import type { Metadata } from "next";
import Link from "next/link";
import { fetchEngine } from "../../lib/engine";

export const metadata: Metadata = { title: "Asset review — SourceMode" };
export const dynamic = "force-dynamic";

type Row = { character: string; candidates: number; plan: string | null; placed: number };

export default async function AssetsIndex() {
  const data = await fetchEngine<{ root: string; characters: Row[] }>("/assets");
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 720, margin: "2rem auto", padding: "0 1rem" }}>
      <p style={{ margin: "0 0 .5rem" }}>
        <Link href="/">← SourceMode</Link>
      </p>
      <h1 style={{ marginTop: 0 }}>Asset review</h1>
      <p style={{ color: "#666" }}>Pick the cutout that ships for each look. Reads and writes the engine&apos;s staging folder only — never the game repo.</p>
      {!data && <p style={{ color: "#b00" }}>Engine unreachable — start <code>sourcemode monitor serve</code> on the GPU box.</p>}
      {data && data.characters.length === 0 && (
        <p>
          Nothing staged yet in <code>{data.root}</code>. Run <code>assets render</code> then <code>assets cutout --game</code> for a character.
        </p>
      )}
      {data && data.characters.length > 0 && (
        <table cellPadding={8} style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #ccc" }}>
              <th>Character</th>
              <th>Candidates</th>
              <th>Plan</th>
              <th>Placed</th>
            </tr>
          </thead>
          <tbody>
            {data.characters.map((c) => (
              <tr key={c.character} style={{ borderBottom: "1px solid #eee" }}>
                <td>
                  <Link href={`/assets/${encodeURIComponent(c.character)}`}>
                    <strong>{c.character}</strong>
                  </Link>
                </td>
                <td>{c.candidates}</td>
                <td>{c.plan ?? <span style={{ color: "#999" }}>none</span>}</td>
                <td>{c.placed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
