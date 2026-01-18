from __future__ import annotations

from contextlib import contextmanager
from http.server import HTTPServer
from threading import Thread
from typing import Iterator

from ieim.api.app import ApiContext, _make_handler


@contextmanager
def run_api_server(*, ctx: ApiContext) -> Iterator[str]:
    srv = HTTPServer(("127.0.0.1", 0), _make_handler(ctx))
    host, port = srv.server_address
    base_url = f"http://{host}:{port}"
    t = Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    try:
        yield base_url
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)
