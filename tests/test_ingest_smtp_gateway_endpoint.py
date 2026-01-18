import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from ieim.ingest.smtp_gateway_endpoint import make_smtp_gateway_handler


class TestSmtpGatewayEndpoint(unittest.TestCase):
    def test_accepts_post_and_invokes_processor(self) -> None:
        received: dict[str, object] = {"raw": None, "headers": None}

        def processor(raw: bytes, headers: dict[str, str]) -> str:
            received["raw"] = raw
            received["headers"] = headers
            return "smtp-1"

        handler = make_smtp_gateway_handler(processor)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]

        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            req = Request(
                f"http://127.0.0.1:{port}/ingest",
                data=b"raw-mime-bytes",
                method="POST",
                headers={"Content-Type": "message/rfc822"},
            )
            with urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 202)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body["status"], "accepted")
                self.assertEqual(body["source_message_id"], "smtp-1")
        finally:
            httpd.shutdown()
            httpd.server_close()

        self.assertEqual(received["raw"], b"raw-mime-bytes")
        self.assertIsInstance(received["headers"], dict)

    def test_unknown_path_returns_not_found(self) -> None:
        def processor(_raw: bytes, _headers: dict[str, str]) -> str:
            return "smtp-1"

        handler = make_smtp_gateway_handler(processor)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]

        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            req = Request(
                f"http://127.0.0.1:{port}/nope",
                data=b"x",
                method="POST",
            )
            with self.assertRaises(Exception):
                urlopen(req, timeout=5)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()

