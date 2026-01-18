CREATE TABLE IF NOT EXISTS ieim_schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ieim_meta_kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
