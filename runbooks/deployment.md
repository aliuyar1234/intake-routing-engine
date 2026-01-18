# Deployment runbook

IEIM can be deployed on-prem, in the cloud, or hybrid. The recommended default is hybrid with raw data remaining in the customer’s environment and optional LLM calls routed through a controlled gateway.

## Preconditions

- Secrets and keys provisioned
- Network egress rules established for allowed services only
- RBAC configured and access review completed
- Pack verification and unit tests are green

Verification commands:

```bash
python ieimctl.py pack verify
python -B -m unittest discover -s tests -p "test_*.py"
```

Optional load test (file-backed sample corpus):

```bash
python ieimctl.py loadtest run --config configs/dev.yaml --report-path reports/load_test_report.json
```

## Components to deploy

- Ingestion service
- Raw store
- Normalization/attachment services
- Identity/classification/extraction services
- Routing engine
- Case adapter
- HITL UI
- Observability stack

## Deployment order

1. Datastores (raw store, normalized DB, audit event store)
2. Message queue
3. Core services
4. Adapters
5. HITL UI
6. Dashboards and alerts

## Rollback

- Services are stateless and can be rolled back by redeploying the previous image.
- Data stores are append-only; rollback does not delete data.
