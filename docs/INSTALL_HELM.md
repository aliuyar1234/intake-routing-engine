# Install (Kubernetes + Helm)

This repository ships a Helm chart under `deploy/helm/ieim/` for Kubernetes installs.

## Prerequisites

- Kubernetes cluster (for example a local dev cluster or an enterprise cluster)
- `kubectl`
- Helm v3, or Docker (for running a Helm container for template rendering)

## Render manifests (template only)

If Helm is installed:

```bash
helm template ieim deploy/helm/ieim -f deploy/helm/ieim/values.yaml
```

If Helm is not installed, render via a containerized Helm:

```bash
docker run --rm -v "$PWD:/work" -w /work alpine/helm:3.14.0 template ieim deploy/helm/ieim -f deploy/helm/ieim/values.yaml
```

## Install

Starter values:

```bash
helm install ieim deploy/helm/ieim -f deploy/helm/ieim/starter-values.yaml
```

Production values:

```bash
helm install ieim deploy/helm/ieim -f deploy/helm/ieim/production-values.yaml
```

## Security defaults

The chart enforces non-root execution, drops Linux capabilities, and uses a read-only root filesystem with an explicit writable `/tmp` volume.
