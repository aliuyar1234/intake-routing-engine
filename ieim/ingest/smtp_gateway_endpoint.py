from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional


IngestProcessor = Callable[[bytes, dict[str, str]], str]


def make_smtp_gateway_handler(processor: IngestProcessor):
    class SmtpGatewayHandler(BaseHTTPRequestHandler):
        server_version = "IEIM-SMTP-Gateway/1.0"

        def do_POST(self):  # noqa: N802
            if self.path != "/ingest":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return

            if length <= 0:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return

            raw = self.rfile.read(length)
            headers = {k: v for (k, v) in self.headers.items()}

            try:
                message_id = processor(raw, headers)
            except Exception:
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            body = json.dumps({"status": "accepted", "source_message_id": message_id}).encode(
                "utf-8"
            )
            self.send_response(HTTPStatus.ACCEPTED)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args) -> None:
            # Keep default server quiet; production should use structured logging.
            return

    return SmtpGatewayHandler


def run_smtp_gateway_http_server(
    *,
    host: str,
    port: int,
    processor: IngestProcessor,
    ready_callback: Optional[Callable[[], None]] = None,
) -> None:
    handler = make_smtp_gateway_handler(processor)
    httpd = ThreadingHTTPServer((host, port), handler)
    if ready_callback:
        ready_callback()
    httpd.serve_forever()

