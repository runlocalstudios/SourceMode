-- 001_init: core tables. Forward-only, idempotent (IF NOT EXISTS everywhere).

CREATE TABLE IF NOT EXISTS characters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text UNIQUE NOT NULL,
  name text NOT NULL,
  source_version text,
  source jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scenes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  character_id uuid REFERENCES characters(id),
  title text,
  brief text,
  shot_list jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scene_id uuid REFERENCES scenes(id),
  idx int,
  spec jsonb,
  prompt_hash text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS renders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  shot_id uuid REFERENCES shots(id),
  pass text CHECK (pass IN ('draft', 'final')),
  status text,
  identity_score numeric,
  settings jsonb,
  artifact_path text,
  created_at timestamptz NOT NULL DEFAULT now()
);
