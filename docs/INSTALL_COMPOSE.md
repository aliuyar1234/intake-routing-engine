# Install (Docker Compose)

This phase provides a runnable Docker Compose distribution with two profiles:

- `starter`: single-node demo stack for local evaluation
- `production`: hardened defaults and TLS at ingress (single node), plus optional embedded dependencies

## Prerequisites

- Docker Engine (Docker Desktop on Windows)
- Docker Compose v2 (`docker compose`)
- Python 3.12+ for running the demo CLI (`ieimctl.py`)

## Starter profile

Start the stack:

```bash
docker compose -f deploy/compose/starter/docker-compose.yml up -d --build
```

Check API health (default port `8080`):

```bash
curl http://localhost:8080/healthz
```

Run the end-to-end demo flow against the sample corpus:

```bash
python ieimctl.py demo run --config configs/dev.yaml --samples data/samples
```

Stop and remove volumes:

```bash
docker compose -f deploy/compose/starter/docker-compose.yml down -v
```

## Production profile

Start the stack (TLS termination via Caddy, exposed on `https://localhost:8443/` by default):

```bash
docker compose -f deploy/compose/production/docker-compose.yml up -d --build
```

The production profile uses an internal TLS certificate by default. Browsers and HTTP clients will warn unless you trust the local CA.

Stop and remove volumes:

```bash
docker compose -f deploy/compose/production/docker-compose.yml down -v
```

### Optional embedded dependencies (production compose)

The production compose file supports running Postgres, RabbitMQ, MinIO, and Keycloak as embedded services via the `embedded` profile:

```bash
docker compose -f deploy/compose/production/docker-compose.yml --profile embedded up -d
```

### Optional retention job (production compose)

The production compose file includes an optional retention loop via the `ops` profile:

```bash
docker compose -f deploy/compose/production/docker-compose.yml --profile ops up -d
```

## Notes

- The demo pipeline execution is driven by `python ieimctl.py demo run`. The long-running worker orchestration is expanded in later phases (see `spec/09_PHASE_PLAN.md`).
- Compose files are designed to expose only the API endpoint by default (starter: `http://localhost:8080`, production: `https://localhost:8443/`). Ports can be overridden with `IEIM_HTTP_PORT` and `IEIM_HTTPS_PORT`.
