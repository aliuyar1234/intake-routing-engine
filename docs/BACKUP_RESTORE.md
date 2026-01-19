# Backup and restore

IEIM ships **operator scripts** for backing up and restoring state in a way that matches the enterprise defaults:

- **Postgres** for metadata
- **S3-compatible object storage** for raw + derived artifacts
- **Config snapshots** so restores are reproducible and auditable

The scripts also support the **file-backed reference runtime** used for local demos and CI-like environments.

## Scripts

- `infra/backup/backup.sh`
- `infra/backup/restore.sh`

Both scripts are **fail-closed**: if you request a Postgres or S3 backup/restore but the required tools are missing, they exit non-zero.

## File-backed reference runtime (local demos)

Backup:

```bash
infra/backup/backup.sh \
  --out /backups/ieim_001 \
  --config configs/dev.yaml \
  --runtime-dir /var/lib/ieim
```

Restore:

```bash
infra/backup/restore.sh \
  --in /backups/ieim_001 \
  --runtime-dir /var/lib/ieim \
  --config-dest /etc/ieim/runtime.yaml
```

## Postgres (enterprise default)

Requires `pg_dump` and `pg_restore` in `PATH`.

Backup:

```bash
infra/backup/backup.sh --out /backups/ieim_001 --config /app/configs/runtime.yaml --pg-dsn "$IEIM_PG_DSN"
```

Restore:

```bash
infra/backup/restore.sh --in /backups/ieim_001 --pg-dsn "$IEIM_PG_DSN"
```

## S3-compatible object storage (enterprise default)

Requires `aws` CLI in `PATH`. For MinIO or other S3-compatible services, pass `--s3-endpoint`.

Backup:

```bash
infra/backup/backup.sh \
  --out /backups/ieim_001 \
  --config /app/configs/runtime.yaml \
  --s3-bucket ieim-artifacts \
  --s3-prefix raw_store/ \
  --s3-endpoint http://minio:9000
```

Restore:

```bash
infra/backup/restore.sh \
  --in /backups/ieim_001 \
  --s3-bucket ieim-artifacts \
  --s3-prefix raw_store/ \
  --s3-endpoint http://minio:9000
```

