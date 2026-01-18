# Retention jobs

Retention is enforced by scheduled jobs that delete or anonymize data according to configuration.

## Stores

- Raw store: delete after raw retention days
- Normalized store: delete after normalized retention days
- Audit store: retain for audit retention years

## File-backed reference implementation

This pack includes a file-backed retention runner for local demos and for validating retention logic in CI-like environments.

It derives retention eligibility from `NormalizedMessage.ingested_at` and from `AttachmentArtifact` references, and deletes only **unreferenced** raw-store artifacts (content-addressed by SHA-256).

Command (dry-run by default):

```bash
python ieimctl.py retention run --base-dir <RUNTIME_BASE_DIR> --normalized-dir <NORMALIZED_DIR> --attachments-dir <ATTACHMENTS_DIR> --report-path reports/retention_report.json
```

To apply deletions, pass `--apply`.

## Job safety

- Jobs must run with least-privilege credentials.
- Jobs must emit audit events for each deletion batch (counts, time range, and hashes of selection queries).
- Jobs must support dry-run mode.
