from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    version: str
    sql: str


def _split_sql(sql: str) -> list[str]:
    # Keep this intentionally simple: migrations in this repo must avoid
    # procedural SQL blocks that include semicolons.
    out: list[str] = []
    for chunk in sql.split(";"):
        stmt = chunk.strip()
        if stmt:
            out.append(stmt)
    return out


def load_migrations(*, repo_root: Path) -> list[Migration]:
    mig_dir = repo_root / "ieim" / "store" / "migrations"
    out: list[Migration] = []
    for path in sorted(mig_dir.glob("*.sql")):
        out.append(Migration(version=path.name, sql=path.read_text(encoding="utf-8")))
    return out


def apply_postgres_migrations(*, dsn: str, repo_root: Path) -> None:
    try:
        import psycopg  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("psycopg is required for Postgres migrations (requirements/runtime.txt)") from e

    migrations = load_migrations(repo_root=repo_root)
    if not migrations:
        return

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Ensure migration table exists (so we can query it before running migrations).
            cur.execute(
                "CREATE TABLE IF NOT EXISTS ieim_schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )

            for mig in migrations:
                cur.execute(
                    "SELECT 1 FROM ieim_schema_migrations WHERE version = %s",
                    (mig.version,),
                )
                if cur.fetchone() is not None:
                    continue

                for stmt in _split_sql(mig.sql):
                    cur.execute(stmt)

                cur.execute(
                    "INSERT INTO ieim_schema_migrations(version) VALUES (%s)",
                    (mig.version,),
                )
