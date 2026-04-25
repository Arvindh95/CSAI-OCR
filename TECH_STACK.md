# CSAI-OCR Technology Stack

## Runtime

- **Python 3.12** — service language (API, worker, admin UI)
- **Ubuntu 22.04 / 24.04** — target host OS
- **systemd** — process supervision (`ocr-api`, `ocr-worker@N`, `ocr-ui`) and timers (`ocr-reaper`, `ocr-reconcile`, `ocr-disksweep`)

## API service (`app/`)

- **FastAPI 0.115** — HTTP framework
- **uvicorn 0.30** — ASGI server (`--workers 1`, single process)
- **Pydantic 2.11** — request/response models
- **python-multipart** — multipart form uploads
- **email-validator** — email field validation

## OCR engine

- **PaddleOCR 3.4** — text detection + recognition
- **PaddlePaddle 3.3** — underlying DL framework (CPU build, MKL-DNN disabled)
- **PaddleX 3.4** — model registry / pipeline glue
- **Pillow 11.2** — image manipulation, overlay rendering
- **pypdf 4.2** — PDF page extraction
- **python-magic** — MIME sniffing on uploads

## Job queue / worker (`app/worker.py`)

- **Redis 6+** — broker
- **RQ 1.16** — Python job queue (`csai-ocr` queue)
- **asyncio** — async event loop inside RQ worker for DB I/O

## Database

- **PostgreSQL 14+** — primary store
- **SQLAlchemy 2.0 (async)** — ORM
- **asyncpg 0.29** — async driver (API, worker)
- **psycopg2-binary 2.9** — sync driver (used by Alembic)
- **Alembic 1.13** — migration runner; schema applied via raw SQL files in `alembic/versions/` (`001_billing_schema.sql`, `002_templates_schema.sql`)

## Auth / security

- **argon2-cffi 23** — API key hashing (peppered)
- **python-dotenv 1.0** — `.env` loading (`/opt/ocr-saas/.env`, mode 600)
- **fail2ban** — basic-auth / SSH brute-force ban (config under `config/fail2ban/`)
- **nginx** — basic-auth gate on Streamlit UI, IP allowlist on `/admin/v1/`, rate limiting (`limit_req_zone`)

## Reverse proxy

- **nginx 1.24** — TLS terminator (when added), reverse proxy, rate limiter, basic-auth, `proxy_cache` for `/media/`, `htpasswd` user file at `/etc/nginx/.htpasswd-csai`

## Admin UI (`admin_ui/`)

- **Streamlit 1.56** — multi-page app at `:8503`
- **streamlit-drawable-canvas 0.9** — zone-annotation canvas (Fabric.js under the hood)
- **httpx 0.27** — sync HTTP client to the API

## Observability

- **Prometheus** — metrics scrape target at `/metrics`
- **prometheus-fastapi-instrumentator 6.1** — auto-metrics for FastAPI
- **python-json-logger 2.0** — structured JSON access + error logs (config in `config/logging.json`)
- **journalctl** — runtime log aggregation (services log to journal)
- **Grafana / Kibana / Elasticsearch** — present on the host for dashboarding (separate units)

## Testing

- **pytest 8.2** — test runner
- **pytest-asyncio 0.23** — async test support
- **fakeredis 2.23** — in-memory Redis double for unit tests
- **httpx 0.27** — TestClient transport

## Layout

| Path | Purpose |
| --- | --- |
| `app/` | FastAPI service + RQ worker + OCR + extractor |
| `app/templates/` | Template loader, field extractor strategies |
| `app/billing/` | Quotas, jobs, usage, redis client |
| `app/routers/` | HTTP routers (`ocr`, `verify`, `admin`, `admin_templates`) |
| `admin_ui/` | Streamlit pages + shared helpers |
| `nginx/csai-ocr.conf` | vhost shipped with the repo |
| `systemd/` | Unit + timer files |
| `alembic/versions/` | SQL migrations (raw .sql, applied with `psql`) |
| `config/` | `logging.json`, `fail2ban/` |
