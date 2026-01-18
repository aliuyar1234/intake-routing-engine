from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


class MetaStore(Protocol):
    def get(self, *, key: str) -> Optional[str]:
        raise NotImplementedError

    def put_if_absent(self, *, key: str, value: str) -> bool:
        raise NotImplementedError


@dataclass
class InMemoryMetaStore:
    _data: dict[str, str]

    def __init__(self) -> None:
        self._data = {}

    def get(self, *, key: str) -> Optional[str]:
        return self._data.get(key)

    def put_if_absent(self, *, key: str, value: str) -> bool:
        if key in self._data:
            return False
        self._data[key] = value
        return True


@dataclass(frozen=True)
class PostgresMetaStoreConfig:
    dsn: str


class PostgresMetaStore:
    def __init__(self, *, config: PostgresMetaStoreConfig, repo_root) -> None:
        self._config = config
        self._repo_root = repo_root

    def _require_psycopg(self):
        try:
            import psycopg  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("psycopg is required for PostgresMetaStore (requirements/runtime.txt)") from e
        return psycopg

    def migrate(self) -> None:
        from ieim.store.migrate import apply_postgres_migrations

        apply_postgres_migrations(dsn=self._config.dsn, repo_root=self._repo_root)

    def get(self, *, key: str) -> Optional[str]:
        psycopg = self._require_psycopg()
        with psycopg.connect(self._config.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM ieim_meta_kv WHERE key = %s", (key,))
                row = cur.fetchone()
                if row is None:
                    return None
                return str(row[0])

    def put_if_absent(self, *, key: str, value: str) -> bool:
        psycopg = self._require_psycopg()
        with psycopg.connect(self._config.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ieim_meta_kv(key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                    (key, value),
                )
                return bool(cur.rowcount == 1)
