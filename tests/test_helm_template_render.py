import subprocess
import unittest
from pathlib import Path

import yaml


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
class TestHelmTemplateRender(unittest.TestCase):
    def test_helm_template_renders_and_is_hardened(self) -> None:
        root = Path(__file__).resolve().parents[1]
        chart_rel = "deploy/helm/ieim"
        values_rel = "deploy/helm/ieim/values.yaml"

        cp = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{root.resolve()}:/work",
                "-w",
                "/work",
                "alpine/helm:3.14.0",
                "template",
                "ieim",
                chart_rel,
                "-f",
                values_rel,
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if cp.returncode != 0:
            raise AssertionError(f"helm template failed\n{cp.stdout}\n{cp.stderr}")

        docs = [d for d in yaml.safe_load_all(cp.stdout) if d]
        kinds = {(d.get("kind"), d.get("metadata", {}).get("name")) for d in docs}
        self.assertIn(("ConfigMap", "ieim-ieim-config"), kinds)
        self.assertIn(("Service", "ieim-ieim-api"), kinds)
        self.assertIn(("Deployment", "ieim-ieim-api"), kinds)
        self.assertIn(("Deployment", "ieim-ieim-worker"), kinds)
        self.assertIn(("Deployment", "ieim-ieim-scheduler"), kinds)

        deployments = [d for d in docs if d.get("kind") == "Deployment"]
        self.assertGreaterEqual(len(deployments), 3)

        for dep in deployments:
            pod_spec = dep["spec"]["template"]["spec"]
            pod_sc = pod_spec.get("securityContext") or {}
            self.assertTrue(pod_sc.get("runAsNonRoot"))
            self.assertEqual(int(pod_sc.get("runAsUser")), 10001)
            self.assertEqual(int(pod_sc.get("runAsGroup")), 10001)

            containers = pod_spec.get("containers") or []
            self.assertEqual(len(containers), 1)
            c = containers[0]
            csc = c.get("securityContext") or {}
            self.assertFalse(csc.get("allowPrivilegeEscalation", True))
            self.assertTrue(csc.get("readOnlyRootFilesystem"))
            caps = (csc.get("capabilities") or {}).get("drop") or []
            self.assertIn("ALL", caps)

            mounts = c.get("volumeMounts") or []
            self.assertTrue(any(m.get("mountPath") == "/tmp" for m in mounts))


if __name__ == "__main__":
    unittest.main()
