from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from ieim.observability.config import load_observability_config
from ieim.observability import tracing
from ieim.runtime.config import validate_config_file
from ieim.runtime.paths import discover_repo_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ieim-worker")
    parser.add_argument("--config", default="configs/dev.yaml", help="Config file (repo-relative unless absolute).")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit.")
    args = parser.parse_args(argv)

    repo_root = discover_repo_root(Path(__file__).resolve())
    cfg_path = Path(args.config)
    cfg_path = cfg_path if cfg_path.is_absolute() else (repo_root / cfg_path)
    validate_config_file(path=cfg_path)

    if args.dry_run:
        print("IEIM_WORKER_DRY_RUN_OK")
        return 0

    obs = load_observability_config(path=cfg_path)
    tracing.init_tracing(enabled=obs.tracing_enabled, service_name="ieim-worker")
    if obs.metrics_enabled:
        try:
            from prometheus_client import start_http_server

            host = os.environ.get("IEIM_METRICS_HOST", "0.0.0.0")
            port = int(os.environ.get("IEIM_WORKER_METRICS_PORT", "9100"))
            start_http_server(port, addr=host)
            print(f"IEIM_WORKER_METRICS_OK: http://{host}:{port}/metrics")
        except Exception as e:
            print(f"IEIM_WORKER_METRICS_FAILED: {e}")
            return 60

    while True:
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
