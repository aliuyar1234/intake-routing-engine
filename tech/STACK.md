# Tech stack

This pack is implementation-neutral but provides a recommended default stack that best satisfies the NFRs.

## Option A — Python-first (recommended)

- Language: Python 3.12
- Framework: FastAPI for service APIs
- Worker runtime: Celery or Dramatiq
- Queue: RabbitMQ or Redis Streams (dev), Kafka (prod)
- Database: PostgreSQL (normalized store)
- Object store: S3-compatible (raw store and attachment extracted text)
- Audit store: PostgreSQL append-only table or Kafka->immutable log, with hash chain
- Observability: OpenTelemetry, Prometheus, Grafana, Loki

Strengths
- Fast delivery, strong ecosystem for MIME/OCR/PDF tooling
- Good hiring pool
- Fits hybrid and on-prem deployments

Tradeoffs
- Maximum throughput may require optimization in hot paths

## Option B — Polyglot Python + Go/Rust for hot paths

- Python for orchestration and APIs
- Go or Rust for high-throughput MIME parsing/attachment processing

Strengths
- Higher throughput and lower CPU cost at high scale

Tradeoffs
- Higher complexity and operational surface

## Option C — JVM/.NET enterprise stack

- Spring Boot or ASP.NET
- Strong enterprise compliance support

Tradeoffs
- Higher dev effort for OCR/PDF and rapid iteration of ML gating compared to Python

## Recommended default

Choose Option A for v1. Add Go/Rust modules only for attachment processing and canonicalization if profiling shows sustained saturation.

## Extension points

- Attachment processing worker (AV/OCR/PDF parsing)
- Hashing and canonicalization utilities
- High-volume ingestion adapters
