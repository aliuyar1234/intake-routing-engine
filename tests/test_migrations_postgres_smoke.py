from __future__ import annotations

import os
import uuid
import unittest
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from ieim.store.migrate import apply_postgres_migrations
from ieim.store.upgrade import check_upgrade


def _dsn_with_db(dsn: str, *, db_name: str) -> str:
    if "://" in dsn:
        u = urlparse(dsn)
        return urlunparse(u._replace(path=f"/{db_name}"))
    return dsn + f" dbname={db_name}"


class TestMigrationsPostgresSmoke(unittest.TestCase):
    def test_migrations_apply_and_upgrade_check(self) -> None:
        base_dsn = os.getenv("IEIM_TEST_PG_DSN")
        if not base_dsn:
            self.skipTest("IEIM_TEST_PG_DSN not set")

        try:
            import psycopg  # type: ignore
        except Exception as e:
            self.skipTest(f"psycopg not available: {e}")

        repo_root = Path(__file__).resolve().parents[1]
        db_name = f"ieim_test_{uuid.uuid4().hex[:12]}"
        test_dsn = _dsn_with_db(base_dsn, db_name=db_name)

        with psycopg.connect(base_dsn) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{db_name}"')

        try:
            apply_postgres_migrations(dsn=test_dsn, repo_root=repo_root)
            ok = check_upgrade(repo_root=repo_root, pg_dsn=test_dsn)
            self.assertTrue(ok.ok)
            self.assertEqual(ok.status, "OK")

            with psycopg.connect(test_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO ieim_schema_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING",
                        ("9999_future.sql",),
                    )

            mismatch = check_upgrade(repo_root=repo_root, pg_dsn=test_dsn)
            self.assertFalse(mismatch.ok)
            self.assertEqual(mismatch.status, "DB_NEWER_THAN_CODE")
        finally:
            with psycopg.connect(base_dsn) as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (db_name,))
                    cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')


if __name__ == "__main__":
    unittest.main()

