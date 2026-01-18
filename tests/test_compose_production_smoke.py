import json
import os
import socket
import ssl
import subprocess
import time
import unittest
import urllib.request
import uuid
from pathlib import Path


def _docker_available() -> bool:
    try:
        cp = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return False
    return cp.returncode == 0


def _wait_https_ok(url: str, *, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    last_err: str | None = None
    ctx = ssl._create_unverified_context()
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3, context=ctx) as resp:
                if int(resp.status) == 200:
                    return
                last_err = f"unexpected status: {resp.status}"
        except Exception as e:
            last_err = str(e)
        time.sleep(1)
    raise TimeoutError(last_err or "timeout")


@unittest.skipUnless(_docker_available(), "docker engine not available")
class TestComposeProductionSmoke(unittest.TestCase):
    def test_compose_production_starts_and_is_least_exposed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        compose_file = root / "deploy" / "compose" / "production" / "docker-compose.yml"
        project = f"ieim-prod-{uuid.uuid4().hex[:8]}"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            https_port = int(s.getsockname()[1])

        env = dict(os.environ)
        env["IEIM_HTTPS_PORT"] = str(https_port)

        def compose(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["docker", "compose", "-p", project, "-f", str(compose_file), *args],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                check=False,
            )

        try:
            up = compose("up", "-d", "--build")
            if up.returncode != 0:
                raise AssertionError(f"compose up failed\n{up.stdout}\n{up.stderr}")

            _wait_https_ok(f"https://localhost:{https_port}/healthz", timeout_s=90)

            ps = compose("ps", "-q")
            if ps.returncode != 0:
                raise AssertionError(f"compose ps failed\n{ps.stdout}\n{ps.stderr}")
            container_ids = [ln.strip() for ln in ps.stdout.splitlines() if ln.strip()]
            self.assertGreaterEqual(len(container_ids), 1)

            for cid in container_ids:
                top = subprocess.run(
                    ["docker", "top", cid],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if top.returncode != 0:
                    raise AssertionError(f"docker top failed for {cid}\n{top.stdout}\n{top.stderr}")
                for line in top.stdout.splitlines()[1:]:
                    if not line.strip():
                        continue
                    uid = line.split()[0].strip()
                    if uid in {"0", "root"}:
                        raise AssertionError(f"root process detected in container {cid}\n{top.stdout}")

            proxy_container = compose("ps", "-q", "proxy")
            if proxy_container.returncode != 0 or not proxy_container.stdout.strip():
                raise AssertionError("expected proxy container id")
            proxy_id = proxy_container.stdout.strip()

            for cid in container_ids:
                inspect = subprocess.run(
                    ["docker", "inspect", cid],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if inspect.returncode != 0:
                    raise AssertionError(f"docker inspect failed for {cid}\n{inspect.stdout}\n{inspect.stderr}")
                obj = json.loads(inspect.stdout)[0]
                ports = obj.get("NetworkSettings", {}).get("Ports", {}) or {}
                host_bindings = [k for k, v in ports.items() if v]
                if cid == proxy_id:
                    self.assertTrue(host_bindings, "proxy must publish a port")
                else:
                    self.assertEqual(host_bindings, [], f"unexpected published ports for container {cid}")
        finally:
            compose("down", "-v", "--remove-orphans")


if __name__ == "__main__":
    unittest.main()
