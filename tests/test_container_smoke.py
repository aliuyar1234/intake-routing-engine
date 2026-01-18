import subprocess
import sys
import unittest
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


@unittest.skipUnless(_docker_available(), "docker engine not available")
class TestContainerSmoke(unittest.TestCase):
    def test_build_and_dry_run(self) -> None:
        root = Path(__file__).resolve().parents[1]

        cases = [
            (
                "ieim-api:smoke",
                "deploy/compose/Dockerfile.api",
                ["--dry-run", "--config", "configs/dev.yaml"],
                "IEIM_API_DRY_RUN_OK",
            ),
            (
                "ieim-worker:smoke",
                "deploy/compose/Dockerfile.worker",
                ["--dry-run", "--config", "configs/dev.yaml"],
                "IEIM_WORKER_DRY_RUN_OK",
            ),
            (
                "ieim-scheduler:smoke",
                "deploy/compose/Dockerfile.scheduler",
                ["--dry-run", "--config", "configs/dev.yaml"],
                "IEIM_SCHEDULER_DRY_RUN_OK",
            ),
        ]

        for tag, dockerfile, args, expected in cases:
            build = subprocess.run(
                ["docker", "build", "-f", dockerfile, "-t", tag, "."],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if build.returncode != 0:
                raise AssertionError(f"docker build failed for {tag}\n{build.stdout}\n{build.stderr}")

            user = subprocess.run(
                ["docker", "image", "inspect", tag, "--format", "{{.Config.User}}"],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if user.returncode != 0:
                raise AssertionError(f"docker inspect failed for {tag}\n{user.stdout}\n{user.stderr}")
            user_value = user.stdout.strip()
            self.assertNotEqual(user_value, "")
            uid = user_value.split(":", 1)[0]
            self.assertNotIn(uid, {"0", "root"})

            run = subprocess.run(
                ["docker", "run", "--rm", tag, *args],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if run.returncode != 0:
                raise AssertionError(f"docker run failed for {tag}\n{run.stdout}\n{run.stderr}")
            self.assertIn(expected, run.stdout)


if __name__ == "__main__":
    unittest.main()
