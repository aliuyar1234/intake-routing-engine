# Upgrade

This document covers upgrades of the IEIM system (application + Helm chart) and the database schema used by the runtime meta store.

## Pre-flight checks

Validate the config and (optionally) the Postgres migration state:

```bash
python ieimctl.py upgrade check --config configs/prod.yaml
python ieimctl.py upgrade check --config configs/prod.yaml --pg-dsn "$IEIM_PG_DSN"
```

If `--pg-dsn` (or `IEIM_PG_DSN`) is not provided, the command performs an offline check and skips the database state validation.

## Database migrations

Migrations in this repo are forward-only SQL files under `ieim/store/migrations/`.

Apply migrations:

```bash
python ieimctl.py upgrade migrate --config configs/prod.yaml --pg-dsn "$IEIM_PG_DSN"
```

Re-run the check:

```bash
python ieimctl.py upgrade check --config configs/prod.yaml --pg-dsn "$IEIM_PG_DSN"
```

If you need to revert a migration, use backup/restore procedures (see `docs/BACKUP_RESTORE.md`).

## Helm chart upgrades

Upgrading the Helm release is done using standard Helm workflows:

```bash
helm upgrade ieim deploy/helm/ieim -f deploy/helm/ieim/production-values.yaml
```

## Compatibility

- Configuration is treated as a versioned contract. Validate config changes using `python ieimctl.py config validate`.
- Schema changes are governed by the SSOT rules in `spec/` and the binding quality gates in `QUALITY_GATES.md`.
