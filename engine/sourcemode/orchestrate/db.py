"""Optional Neon sync: upsert scene/shots/renders via psycopg (extra `db`).

Reads DATABASE_URL_UNPOOLED (falls back to DATABASE_URL) from the environment;
`vercel env pull .env.local` at the repo root provides it — load it yourself or
set the var. Idempotent: characters upsert on slug, scenes/shots/renders insert
with stable natural keys where available.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..source import CharacterSource


def _load_repo_env() -> None:
    """Best-effort read of the repo-root .env.local (no external deps)."""
    env_file = Path(__file__).resolve().parents[3] / ".env.local"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _connect(log):
    """Return an open psycopg connection, or None (with the reason logged)."""
    try:
        import psycopg  # noqa: PLC0415
    except ImportError:
        log("psycopg not installed — uv sync --extra db (skipping db sync)")
        return None

    _load_repo_env()
    url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL")
    if not url:
        log("DATABASE_URL_UNPOOLED not set (vercel env pull .env.local) — skipping db sync")
        return None
    return psycopg.connect(url)


def _upsert_character(cur, source: CharacterSource) -> int:
    cur.execute(
        """
        INSERT INTO characters (slug, name, source_version, source)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (slug) DO UPDATE
          SET name = EXCLUDED.name, source_version = EXCLUDED.source_version, source = EXCLUDED.source
        RETURNING id
        """,
        (source.character_id, source.name, source.version, source.model_dump_json()),
    )
    return cur.fetchone()[0]


def sync_character(source: CharacterSource, *, log=print) -> bool:
    """Upsert just the character + source JSON (dashboard listing)."""
    conn = _connect(log)
    if conn is None:
        return False
    with conn, conn.cursor() as cur:
        character_id = _upsert_character(cur, source)
        conn.commit()
    log(f"synced character to Neon (slug={source.character_id}, id={character_id}, version={source.version})")
    return True


def sync_results(source: CharacterSource, brief: str, results: dict, *, log=print) -> bool:
    conn = _connect(log)
    if conn is None:
        return False

    with conn, conn.cursor() as cur:
        character_id = _upsert_character(cur, source)

        cur.execute(
            "INSERT INTO scenes (character_id, title, brief, shot_list) VALUES (%s, %s, %s, %s::jsonb) RETURNING id",
            (character_id, brief[:80], brief, json.dumps(results.get("shots", []))),
        )
        scene_id = cur.fetchone()[0]

        for shot in results.get("shots", []):
            cur.execute(
                "INSERT INTO shots (scene_id, idx, spec, prompt_hash) VALUES (%s, %s, %s::jsonb, %s) RETURNING id",
                (scene_id, shot["idx"], json.dumps(shot), shot.get("prompt_hash")),
            )
            shot_id = cur.fetchone()[0]
            gate = shot.get("gate") or {}
            cur.execute(
                """
                INSERT INTO renders (shot_id, pass, status, identity_score, settings, artifact_path)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    shot_id,
                    results.get("pass", "draft"),
                    "dry_run" if results.get("dry_run") else ("done" if shot.get("video") else "failed"),
                    gate.get("score"),
                    json.dumps({"gate": gate}),
                    shot.get("video"),
                ),
            )
        conn.commit()
    log(f"synced scene to Neon (character={source.character_id}, shots={len(results.get('shots', []))})")
    return True
