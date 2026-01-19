# Configuration

IEIM configuration lives in YAML files under `configs/`.

- `configs/dev.yaml` is the default for local validation and demo flows.
- `configs/prod.yaml` is the default for production-oriented settings (for example retention durations and throughput limits).

Validate any config file:

```bash
python ieimctl.py config validate --config configs/dev.yaml
python ieimctl.py config validate --config configs/prod.yaml
```

## Canonical constants (SSOT)

Canonical labels and IDs are defined only in `spec/00_CANONICAL.md`. Config and rules must use those canonical values.

## Key sections

Common fields you will typically change:

- `auth.oidc`: OIDC issuer and JWT validation (plus optional direct-grant login for starter/dev)
- `incident`: operational toggles (force review, disable LLM, block case creation for selected risk flags)
- `pipeline`: mode selection (`BASELINE` or `LLM_FIRST`)
- `identity`: scoring thresholds and signal weights
- `classification.llm`: LLM enablement and provider settings (disabled by default)
- `classification.llm.thresholds`: confidence gates for LLM-first classification and extraction
- `routing`: routing ruleset path and version
- `retention`: retention durations (raw, normalized, audit)
- `rbac`: role mappings for permissions like `can_view_raw`

## Routing rulesets

Routing rulesets live under `configs/routing_tables/`. Validate and simulate routing behavior using the CLI:

```bash
python ieimctl.py rules lint --ruleset-path configs/routing_tables/routing_rules_v1.4.1.json
python ieimctl.py rules simulate --normalized-dir data/samples/emails --gold-dir data/samples/gold
```

## Demo execution config override

`python ieimctl.py demo run` accepts `--config` and applies that config to all messages in the run. This is useful for evaluating one profile deterministically.
