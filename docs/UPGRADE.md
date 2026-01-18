# Upgrade

## Helm chart upgrades

Upgrading the Helm release is done using standard Helm workflows:

```bash
helm upgrade ieim deploy/helm/ieim -f deploy/helm/ieim/production-values.yaml
```

## Compatibility

- Configuration is treated as a versioned contract. Validate config changes using `python ieimctl.py config validate`.
- Schema changes are governed by the SSOT rules in `spec/` and the binding quality gates in `QUALITY_GATES.md`.
