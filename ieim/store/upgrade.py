from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ieim.store.migrate import load_migrations


@dataclass(frozen=True)
class UpgradeCheckResult:
    status: str
    ok: bool
    db_checked: bool
    repo_migrations: Sequence[str]
    db_migrations: Sequence[str]
    pending_migrations: Sequence[str]
    unknown_migrations: Sequence[str]
    error: str | None


def check_upgrade(*, repo_root: Path, pg_dsn: str | None) -> UpgradeCheckResult:
    repo_migs = load_migrations(repo_root=repo_root)
    repo_versions = tuple(m.version for m in repo_migs)
    if not repo_versions:
        return UpgradeCheckResult(
            status="REPO_MIGRATIONS_MISSING",
            ok=False,
            db_checked=False,
            repo_migrations=(),
            db_migrations=(),
            pending_migrations=(),
            unknown_migrations=(),
            error="no migrations found in ieim/store/migrations",
        )

    if pg_dsn is None:
        return UpgradeCheckResult(
            status="OFFLINE_OK",
            ok=True,
            db_checked=False,
            repo_migrations=repo_versions,
            db_migrations=(),
            pending_migrations=(),
            unknown_migrations=(),
            error=None,
        )

    try:
        import psycopg  # type: ignore
    except Exception as e:  # pragma: no cover
        return UpgradeCheckResult(
            status="PSYCOPG_MISSING",
            ok=False,
            db_checked=True,
            repo_migrations=repo_versions,
            db_migrations=(),
            pending_migrations=repo_versions,
            unknown_migrations=(),
            error=f"psycopg is required for Postgres upgrade checks: {e}",
        )

    try:
        with psycopg.connect(pg_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.ieim_schema_migrations')")
                row = cur.fetchone()
                if row is None or row[0] is None:
                    return UpgradeCheckResult(
                        status="DB_UNINITIALIZED",
                        ok=False,
                        db_checked=True,
                        repo_migrations=repo_versions,
                        db_migrations=(),
                        pending_migrations=repo_versions,
                        unknown_migrations=(),
                        error="database is not initialized (ieim_schema_migrations table missing)",
                    )

                cur.execute("SELECT version FROM ieim_schema_migrations ORDER BY version")
                db_versions = [str(r[0]) for r in (cur.fetchall() or [])]
    except Exception as e:
        return UpgradeCheckResult(
            status="DB_UNAVAILABLE",
            ok=False,
            db_checked=True,
            repo_migrations=repo_versions,
            db_migrations=(),
            pending_migrations=repo_versions,
            unknown_migrations=(),
            error=f"failed to query database migration state: {e}",
        )

    repo_set = set(repo_versions)
    db_set = set(db_versions)

    unknown = tuple(v for v in db_versions if v not in repo_set)
    pending = tuple(v for v in repo_versions if v not in db_set)

    ok = (len(unknown) == 0) and (len(pending) == 0)
    status = "OK"
    if not ok:
        if unknown:
            status = "DB_NEWER_THAN_CODE"
        elif pending:
            status = "DB_PENDING_MIGRATIONS"
        else:
            status = "DB_MIGRATION_MISMATCH"
    return UpgradeCheckResult(
        status=status,
        ok=ok,
        db_checked=True,
        repo_migrations=repo_versions,
        db_migrations=tuple(db_versions),
        pending_migrations=pending,
        unknown_migrations=unknown,
        error=None if ok else "database migration state is not compatible with this release",
    )
