#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
IEIM restore (filesystem + optional Postgres/S3)

Required:
  --in <dir>           Backup directory produced by infra/backup/backup.sh

Optional:
  --config-dest <path> Restore the config snapshot to this path
  --runtime-dir <dir>  Restore runtime filesystem tarball into this directory
  --force              Allow restoring into non-empty runtime dir

Optional (enterprise runtime):
  --pg-dsn <dsn>       Postgres DSN for pg_restore (requires pg_restore)
  --s3-bucket <name>   S3 bucket to restore into (requires aws CLI)
  --s3-prefix <pref>   Optional key prefix within the bucket
  --s3-endpoint <url>  Optional endpoint URL (MinIO / S3-compatible)
  --s3-region <region> Optional region name

Examples:
  infra/backup/restore.sh --in /backups/ieim_001 --runtime-dir /var/lib/ieim --config-dest /etc/ieim/runtime.yaml
  infra/backup/restore.sh --in /backups/ieim_001 --pg-dsn "$IEIM_PG_DSN"
  infra/backup/restore.sh --in /backups/ieim_001 --s3-bucket ieim-artifacts --s3-prefix raw_store/
EOF
}

IN_DIR=""
CONFIG_DEST=""
RUNTIME_DIR=""
FORCE="0"
PG_DSN=""
S3_BUCKET=""
S3_PREFIX=""
S3_ENDPOINT=""
S3_REGION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --in) IN_DIR="${2:-}"; shift 2 ;;
    --config-dest) CONFIG_DEST="${2:-}"; shift 2 ;;
    --runtime-dir) RUNTIME_DIR="${2:-}"; shift 2 ;;
    --force) FORCE="1"; shift 1 ;;
    --pg-dsn) PG_DSN="${2:-}"; shift 2 ;;
    --s3-bucket) S3_BUCKET="${2:-}"; shift 2 ;;
    --s3-prefix) S3_PREFIX="${2:-}"; shift 2 ;;
    --s3-endpoint) S3_ENDPOINT="${2:-}"; shift 2 ;;
    --s3-region) S3_REGION="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 10 ;;
  esac
done

if [[ -z "$IN_DIR" ]]; then
  usage
  exit 10
fi

if [[ ! -d "$IN_DIR" ]]; then
  echo "backup dir not found: $IN_DIR" >&2
  exit 10
fi

if [[ -n "$CONFIG_DEST" ]]; then
  SNAP_DIR="$IN_DIR/config"
  if [[ ! -d "$SNAP_DIR" ]]; then
    echo "missing config snapshot dir: $SNAP_DIR" >&2
    exit 60
  fi
  SNAP_FILE="$(ls -1 "$SNAP_DIR"/*.yml "$SNAP_DIR"/*.yaml 2>/dev/null | head -n 1 || true)"
  if [[ -z "$SNAP_FILE" ]]; then
    SNAP_FILE="$(ls -1 "$SNAP_DIR"/* 2>/dev/null | head -n 1 || true)"
  fi
  if [[ -z "$SNAP_FILE" ]]; then
    echo "no config snapshot found in $SNAP_DIR" >&2
    exit 60
  fi
  mkdir -p "$(dirname "$CONFIG_DEST")"
  cp -f "$SNAP_FILE" "$CONFIG_DEST"
fi

if [[ -n "$RUNTIME_DIR" ]]; then
  if [[ ! -f "$IN_DIR/runtime_fs.tgz" ]]; then
    echo "missing runtime filesystem tarball: $IN_DIR/runtime_fs.tgz" >&2
    exit 60
  fi
  mkdir -p "$RUNTIME_DIR"
  if [[ "$FORCE" != "1" ]]; then
    if [[ -n "$(ls -A "$RUNTIME_DIR" 2>/dev/null || true)" ]]; then
      echo "runtime dir is not empty (use --force to overwrite): $RUNTIME_DIR" >&2
      exit 10
    fi
  fi
  tar -C "$RUNTIME_DIR" -xzf "$IN_DIR/runtime_fs.tgz"
fi

if [[ -n "$PG_DSN" ]]; then
  if [[ ! -f "$IN_DIR/postgres.dump" ]]; then
    echo "missing postgres dump: $IN_DIR/postgres.dump" >&2
    exit 60
  fi
  if ! command -v pg_restore >/dev/null 2>&1; then
    echo "pg_restore not found in PATH (required for --pg-dsn)" >&2
    exit 40
  fi
  pg_restore --dbname="$PG_DSN" "$IN_DIR/postgres.dump"
fi

if [[ -n "$S3_BUCKET" ]]; then
  if [[ ! -d "$IN_DIR/object_store" ]]; then
    echo "missing object store mirror: $IN_DIR/object_store" >&2
    exit 60
  fi
  if ! command -v aws >/dev/null 2>&1; then
    echo "aws CLI not found in PATH (required for --s3-bucket)" >&2
    exit 40
  fi

  AWS_ARGS=()
  if [[ -n "$S3_ENDPOINT" ]]; then
    AWS_ARGS+=(--endpoint-url "$S3_ENDPOINT")
  fi
  if [[ -n "$S3_REGION" ]]; then
    AWS_ARGS+=(--region "$S3_REGION")
  fi

  PREFIX="${S3_PREFIX#/}"
  DST="s3://${S3_BUCKET}"
  if [[ -n "$PREFIX" ]]; then
    DST="${DST}/${PREFIX}"
  fi

  aws "${AWS_ARGS[@]}" s3 sync "$IN_DIR/object_store" "$DST"
fi

echo "RESTORE_OK: $IN_DIR"

