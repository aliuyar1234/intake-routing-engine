# Scaling and performance guidance

This document describes practical scaling levers for IEIM and how to validate performance against the targets in `spec/14_ENTERPRISE_DEFAULTS.md`.

## What scales and why

- **API**: serves the Review UI/API and operational endpoints. Scale for concurrent reviewers and API clients.
- **Worker**: the throughput driver for message processing. Scale for ingest volume, attachment workloads, and any optional OCR/AV workloads.
- **Scheduler**: runs periodic jobs (audit verify, retention). Scale for job concurrency (usually 1 replica is enough).
- **Postgres**: metadata store. Scale for write rates and concurrent workers (connections + IOPS).
- **Object store (S3/MinIO)**: raw/derived artifacts. Scale for throughput and latency; prefer SSD-backed storage for MinIO in production.
- **RabbitMQ**: queueing/backpressure. Scale for durable ingest volume and peak bursts.

## Load testing

Use the built-in load test profiles:

```bash
python ieimctl.py loadtest run --profile enterprise_smoke --config configs/dev.yaml
```

For custom runs:

```bash
python ieimctl.py loadtest run --normalized-dir data/samples/emails --attachments-dir data/samples/attachments --iterations 5 --config configs/dev.yaml
```

## Docker Compose scaling

Compose can scale worker containers horizontally:

```bash
docker compose -f deploy/compose/production/docker-compose.yml up -d --scale worker=3
```

## Kubernetes scaling (Helm)

### Replica scaling

Set replicas via Helm values:

- `replicas.worker` to scale throughput
- `replicas.api` to scale concurrent reviewers

### HPA (optional)

The chart includes an optional worker HPA:

- enable with `autoscaling.worker.enabled=true`
- tune `autoscaling.worker.minReplicas/maxReplicas`

CPU-based HPA is a safe baseline. For queue-depth-driven scaling, use a metrics adapter (for example, KEDA) and scale on RabbitMQ queue length.

## Separation of heavy workloads (AV / OCR)

Attachment workloads (AV scanning, text extraction, OCR) can dominate CPU and I/O.

Operational guidance:

- Keep **worker replicas** high enough to absorb bursts and attachment-heavy periods.
- If you introduce separate worker roles (for example `worker-ocr`), isolate them by queue and set separate resource limits.
- Use object storage for raw and derived artifacts to avoid saturating node disks.

## Practical sizing starting points

These are conservative starting points and must be validated in your environment:

- **API**: 1–2 replicas; 0.5–1 CPU; 512Mi–1Gi RAM.
- **Worker**: start at 2–4 replicas; 0.5–2 CPU; 512Mi–2Gi RAM (higher for OCR-heavy workloads).
- **Postgres**: prioritize IOPS and connection limits; monitor slow queries and lock contention.
- **RabbitMQ**: monitor queue depth and consumer lag; configure DLQs and alert on growth.

## What to monitor while scaling

- Stage latency distributions (`IDENTITY`, `CLASSIFY`, `EXTRACT`, `ROUTE`)
- Queue depth (normal + DLQ) and consumer lag
- Postgres: connections, locks, slow queries, disk I/O
- Object store: request latency, error rates
- Review backlog size and percent routed to HITL

