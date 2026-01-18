# Ops monitoring

## Key metrics

- emails_ingested_total
- emails_processed_total
- stage_latency_ms (p50/p95/p99)
- hitl_rate_percent
- mis_association_rate (manual corrections / total)
- misroute_rate (manual routing corrections / total)
- ocr_error_rate (documents requiring re-OCR)
- llm_cost_per_email

## Alert thresholds

- Ingestion failure > 0.5% for 10 minutes
- Audit event gap (missing stage events) for any message_id
- Malware flagged attachment events > baseline
- Spike in identity needs_review over rolling 1h

## Dashboards

- Pipeline overview by stage
- Queues and SLA compliance
- Cost dashboard
