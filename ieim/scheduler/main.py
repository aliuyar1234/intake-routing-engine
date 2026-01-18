from __future__ import annotations

import argparse
import time
from pathlib import Path

from ieim.runtime.config import validate_config_file
from ieim.runtime.paths import discover_repo_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ieim-scheduler")
    parser.add_argument("--config", default="configs/dev.yaml", help="Config file (repo-relative unless absolute).")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit.")
    args = parser.parse_args(argv)

    repo_root = discover_repo_root(Path(__file__).resolve())
    cfg_path = Path(args.config)
    cfg_path = cfg_path if cfg_path.is_absolute() else (repo_root / cfg_path)
    validate_config_file(path=cfg_path)

    if args.dry_run:
        print("IEIM_SCHEDULER_DRY_RUN_OK")
        return 0

    while True:
        time.sleep(15)


if __name__ == "__main__":
    raise SystemExit(main())

