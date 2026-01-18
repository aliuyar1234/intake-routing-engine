from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from ieim.runtime.config import validate_config_file
from ieim.runtime.health import ok
from ieim.runtime.paths import discover_repo_root


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path not in ("/healthz", "/readyz"):
            self.send_response(404)
            self.end_headers()
            return

        report = ok(component="ieim-api")
        payload = json.dumps({"status": report.status, "details": report.details}, ensure_ascii=False).encode(
            "utf-8"
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ieim-api")
    parser.add_argument("--config", default="configs/dev.yaml", help="Config file (repo-relative unless absolute).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit.")
    args = parser.parse_args(argv)

    repo_root = discover_repo_root(Path(__file__).resolve())
    cfg_path = Path(args.config)
    cfg_path = cfg_path if cfg_path.is_absolute() else (repo_root / cfg_path)
    validate_config_file(path=cfg_path)

    if args.dry_run:
        print("IEIM_API_DRY_RUN_OK")
        return 0

    server = HTTPServer((str(args.host), int(args.port)), _Handler)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
