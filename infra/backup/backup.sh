#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
IEIM backup (filesystem + optional Postgres/S3)

Required:
  --out <dir>          Backup output directory (created if missing)
  --config <path>      Runtime config YAML to snapshot

Optional (filesystem reference runtime):
  --runtime-dir <dir>  Directory containing IEIM runtime files (e.g. /var/lib/ieim)

Optional (enterprise runtime):
  --pg-dsn <dsn>       Postgres DSN for pg_dump (requires pg_dump)
  --s3-bucket <name>   S3 bucket to mirror (requires aws CLI)
  --s3-prefix <pref>   Optional key prefix within the bucket
  --s3-endpoint <url>  Optional endpoint URL (MinIO / S3-compatible)
  --s3-region <region> Optional region name

Examples:
  infra/backup/backup.sh --out /backups/ieim_001 --config configs/prod.yaml --runtime-dir /var/lib/ieim
  infra/backup/backup.sh --out /backups/ieim_001 --config /app/configs/runtime.yaml --pg-dsn "$IEIM_PG_DSN"
  infra/backup/backup.sh --out /backups/ieim_001 --config /app/configs/runtime.yaml --s3-bucket ieim-artifacts --s3-prefix raw_store/
EOF
}

OUT=""
CONFIG=""
RUNTIME_DIR=""
PG_DSN=""
S3_BUCKET=""
S3_PREFIX=""
S3_ENDPOINT=""
S3_REGION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="${2:-}"; shift 2 ;;
    --config) CONFIG="${2:-}"; shift 2 ;;
    --runtime-dir) RUNTIME_DIR="${2:-}"; shift 2 ;;
    --pg-dsn) PG_DSN="${2:-}"; shift 2 ;;
    --s3-bucket) S3_BUCKET="${2:-}"; shift 2 ;;
    --s3-prefix) S3_PREFIX="${2:-}"; shift 2 ;;
    --s3-endpoint) S3_ENDPOINT="${2:-}"; shift 2 ;;
    --s3-region) S3_REGION="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 10 ;;
  esac
done

if [[ -z "$OUT" || -z "$CONFIG" ]]; then
  usage
  exit 10
fi

mkdir -p "$OUT"

mkdir -p "$OUT/config"
cp -f "$CONFIG" "$OUT/config/$(basename "$CONFIG")"

if [[ -n "$RUNTIME_DIR" ]]; then
  if [[ ! -d "$RUNTIME_DIR" ]]; then
    echo "RUNTIME_DIR does not exist: $RUNTIME_DIR" >&2
    exit 10
  fi
  tar -C "$RUNTIME_DIR" -czf "$OUT/runtime_fs.tgz" .
fi

if [[ -n "$PG_DSN" ]]; then
  if ! command -v pg_dump >/dev/null 2>&1; then
    echo "pg_dump not found in PATH (required for --pg-dsn)" >&2
    exit 40
  fi
  pg_dump --dbname="$PG_DSN" --format=custom --file="$OUT/postgres.dump"
fi

if [[ -n "$S3_BUCKET" ]]; then
  if ! command -v aws >/dev/null 2>&1; then
    echo "aws CLI not found in PATH (required for --s3-bucket)" >&2
    exit 40
  fi

  mkdir -p "$OUT/object_store"

  AWS_ARGS=()
  if [[ -n "$S3_ENDPOINT" ]]; then
    AWS_ARGS+=(--endpoint-url "$S3_ENDPOINT")
  fi
  if [[ -n "$S3_REGION" ]]; then
    AWS_ARGS+=(--region "$S3_REGION")
  fi

  PREFIX="${S3_PREFIX#/}"
  SRC="s3://${S3_BUCKET}"
  if [[ -n "$PREFIX" ]]; then
    SRC="${SRC}/${PREFIX}"
  fi

  aws "${AWS_ARGS[@]}" s3 sync "$SRC" "$OUT/object_store"
fi

echo "BACKUP_OK: $OUT"

