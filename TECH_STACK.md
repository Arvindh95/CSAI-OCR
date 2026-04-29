# CSAI-OCR Technology Stack

Comprehensive reference covering every technology in the system, what it does, why it is here, and how it is wired in.

---

## 1. System overview

CSAI-OCR is a multi-tenant OCR/verify SaaS for Malaysian SSM business certificates. Clients submit one or more page images to `/api/v1/ocr` or `/api/v1/verify`; the API validates, stores, and enqueues a job; an RQ worker runs PaddleOCR and template-based field extraction; results are persisted to Postgres and exposed via `GET /api/v1/jobs/{id}`. Operations is handled through a Streamlit admin UI behind nginx basic-auth.

```
   Client (HTTP+API key)
            │
            ▼
   ┌────────────────┐    ┌────────────┐      ┌──────────────┐
   │  nginx (TLS,   │ →  │  FastAPI   │  ──► │   Postgres   │
   │  basic-auth,   │    │ (uvicorn)  │      │ (clients,    │
   │  rate limit)   │    │            │      │  jobs, plans,│
   └───────┬────────┘    └─────┬──────┘      │  templates,  │
           │                   │              │  usage)      │
           │            enqueue│              └──────────────┘
           │                   ▼
           │             ┌──────────┐
           │             │  Redis   │  (queue + idempotency
           │             └────┬─────┘   + quota counter)
           │                  │
           │                  ▼
           │           ┌──────────────────────────┐
           │           │  RQ worker (rq + asyncio)│
           │           │  PaddleOCR, extractor    │
           │           └──────────────────────────┘
           │
           ▼
     Streamlit admin UI (operators only)
```

Everything runs on a single Ubuntu VPS under systemd.

---

## 2. Runtime & operating environment

### Python 3.12
Service language for API, worker, admin UI. Chosen for the FastAPI / Pydantic / SQLAlchemy 2.0 ecosystem and for `asyncio` first-class support which is essential for the API and async DB I/O inside the RQ worker. Installed via system Python and a project virtualenv at `/opt/ocr-saas/venv/`.

### Ubuntu 22.04 / 24.04 LTS
Target host OS. Provides systemd unit/timer support, modern OpenSSL, Python 3.12 packages, and `python-magic`'s `libmagic` system dependency.

### systemd
Process supervision and scheduling. Concrete units (in `systemd/`):

| Unit | Role |
| --- | --- |
| `ocr-api.service` | uvicorn process for the FastAPI app |
| `ocr-worker@.service` | Templated unit; one instance per worker (`ocr-worker@1`) running `python -m app.rq_worker` |
| `ocr-ui.service` | Streamlit admin UI on `:8503` |
| `ocr-reaper.{service,timer}` | Periodically marks stale `running` jobs as failed (`scripts/reap_stale_jobs.py`) |
| `ocr-reconcile.{service,timer}` | Reconciles quota counters in Redis against DB (`scripts/reconcile_quota.py`) |
| `ocr-disksweep.{service,timer}` | Cleans abandoned uploads from `/opt/ocr-saas/storage/` (`scripts/sweep_disk.py`) |

Why systemd vs Docker / Kubernetes: deliberate single-VPS deploy, tight memory budget (PaddleOCR can use 16 GB resident), and zero-orchestration ops surface.

---

## 3. API layer (`app/`)

### FastAPI 0.115
HTTP framework. Provides typed request/response models (Pydantic), dependency injection, OpenAPI generation, async route handlers, and starlette middleware. Wired in `app/main.py`:

```python
app = FastAPI(title="CSAI-OCR", version="2.0.0", lifespan=lifespan)
app.add_middleware(AccessLogMiddleware)
install_handlers(app)
app.include_router(health.router)
app.include_router(ocr.router)
app.include_router(verify.router)
app.include_router(admin.router)
app.include_router(admin_templates.router)
```

Used because: the workload is I/O bound (DB, Redis, multipart upload), Pydantic validation matches the strict input contract (file + mime + page_indexes JSON), and OpenAPI docs at `/docs` give clients a free reference.

### uvicorn 0.30 `[standard]`
ASGI server running FastAPI. The `[standard]` extras bring `httptools`, `uvloop` (Linux), and `websockets` for higher throughput. Run by systemd as `--workers 1` because the heavy work runs in the RQ worker process — the API only enqueues — and one worker keeps the in-memory rate-limit/idempotency state simple.

### Pydantic 2.11
Validates request bodies, response schemas, and admin DTOs (`app/admin/schemas.py`, `app/admin/templates_schemas.py`). The `model_validator` pattern is used to enforce cross-field rules (e.g. anchor strategy must declare a label or regex). v2 chosen for performance (`pydantic-core` Rust backend) and `model_config` configurability.

### python-multipart 0.0.9
Required by FastAPI to parse `multipart/form-data` for file uploads. Without it `UploadFile` and `Form(...)` would not work.

### email-validator 2.1
Backs Pydantic's `EmailStr` for client email normalization in admin endpoints.

---

## 4. OCR engine

### PaddleOCR 3.4
Two-stage OCR (text detection + text recognition). Loaded once per worker process in `app/worker.py::ocr_engine()` with:

```python
PaddleOCR(use_doc_orientation_classify=False,
          use_doc_unwarping=False,
          use_textline_orientation=False,
          enable_mkldnn=False)
```

Orientation/unwarping disabled because input images are scanned/photographed certificates already roughly upright; MKL-DNN disabled because it caused intermittent SIGILL on the VPS CPU. Each page is sent through `extract_lines(engine, path)` which returns line-level boxes + text.

### PaddlePaddle 3.3
Deep-learning framework underneath PaddleOCR. CPU build (`paddlepaddle`, not `paddlepaddle-gpu`) — the VPS has no GPU and the model fits in CPU RAM. Memory is the binding constraint: peak resident set has been observed at ~16 GB on a 23 GB box, which is why workers are kept at `--workers 1` and `WORKER_COUNT=1` in systemd.

### PaddleX 3.4
Model registry and pipeline glue used internally by PaddleOCR 3.x. Pinned alongside Paddle to ensure compatible model loaders.

### Pillow 11.2
Image manipulation: opening uploaded files, resizing each page to its template's declared `(width, height)` so OCR pixel coordinates align with annotated zone coordinates, and rendering preview/overlay images in the admin UI.

### python-magic 0.4
MIME sniffing on raw bytes (`magic.from_buffer`). Used in `app/upload.py` to reject anything that isn't `image/jpeg`, `image/png`, or `image/tiff` regardless of file extension. Backed by libmagic on the host.

---

## 5. Job queue & worker

### Redis 5+
Multi-purpose key-value store:

| Use | Key shape |
| --- | --- |
| RQ queue | `rq:queue:csai-ocr`, `rq:job:{job_id}` |
| Idempotency dedupe | `idem:{client_id}:{key}` (24 h TTL) |
| Quota counter | `quota:{client_id}:{period_id}` (monthly TTL) |

Single instance, no clustering — failure domain is the VPS itself.

### RQ 1.16
Python job queue running on top of Redis. Enqueue side in `app/queue.py`:

```python
q.enqueue(
    "app.worker.run_ocr_job", ...,
    job_timeout=600,
    on_failure="app.worker.on_ocr_failure",
)
```

Worker side in `app/rq_worker.py` connects to the `csai-ocr` queue and forks per-job processes (default behavior). The `on_failure` callback is the safety net for hard timeouts and OOMs — it marks the DB row failed, releases the quota counter, writes a `UsageLog`, and unlinks storage files even when the main `_process` was killed mid-execution.

### asyncio
Inside the synchronous RQ worker, `_process(...)` is an async function driven by `asyncio.run(...)`. Used because the DB driver (asyncpg) and Redis client (`redis.asyncio`) are async-native; running sync versions would cost a whole second driver dependency.

---

## 6. Data layer

### PostgreSQL 14+
Primary store. Schema in `alembic/versions/*.sql`:

| Table | Purpose |
| --- | --- |
| `clients` | Tenants — name, email, hashed API key, plan |
| `plans` | Quota limits — `max_transactions`, `max_pages_per_txn` |
| `billing_periods` | Monthly windows per client |
| `usage_logs` | Per-job page count, status, reject reason |
| `jobs` | Job lifecycle — `queued` → `running` → `done|failed`, `input_meta` JSONB |
| `templates` | OCR templates (doc_type + version), JSONB pages and fields |
| `client_doc_type_aliases` | Per-client `doc_type` → template binding |

JSONB on `jobs.input_meta`, `templates.pages`, `templates.fields` so we can iterate template schemas without migrations.

### SQLAlchemy 2.0 (async)
ORM. v2.0 style only — `select(...)` + `await session.execute(...)`. Models live in `app/billing/models.py` and `app/templates/models.py`. Async sessions are created per request via `async_sessionmaker(engine, expire_on_commit=False)`.

### asyncpg 0.29
High-performance async Postgres driver used by SQLAlchemy from the API and worker. Configured with `connect_args={"ssl": False}` because Postgres is on localhost.

### psycopg2-binary 2.9
Sync Postgres driver. Only used by Alembic for migrations because Alembic is sync-only.

### Alembic 1.13
Migration runner. CSAI-OCR uses **raw SQL migrations** (not autogenerated Python ones) — `001_billing_schema.sql`, `002_templates_schema.sql`, `003_template_strategy_between.sql`. Applied manually with `psql` or via `alembic upgrade` in CI/deploy. This gives precise control over CHECK constraints (e.g. strategy whitelist on `templates`), BTREE/GIN indexes on JSONB, and `ON DELETE` semantics that ORM autogeneration would miss.

---

## 7. Auth & security

### argon2-cffi 23
Hashes API keys at write time (`/admin/v1/clients`) and verifies on every authenticated request via `app/billing/auth.py`. Argon2id parameters tuned for ~100ms verification on the VPS — slow enough to defeat offline dictionary attacks if the DB ever leaked.

### python-dotenv 1.0
Loads `/opt/ocr-saas/.env` (mode 0600, owned by `claudeuser`). Holds `DATABASE_URL`, `REDIS_URL`, `API_KEY_PEPPER`, `ADMIN_BASIC_USER`/`ADMIN_BASIC_PASS_HASH`, and `OCR_STORAGE_DIR`. Worker explicitly loads it before any os.environ access.

### fail2ban
SSH and nginx basic-auth brute-force protection. Filters under `config/fail2ban/`.

### nginx (auth + ACL layer)
- Basic-auth on the admin UI vhost (`/etc/nginx/.htpasswd-csai`)
- IP allowlist on `/admin/v1/*` so admin endpoints never face the public internet
- `limit_req_zone` rate limiting per client IP for `/api/v1/*`

### Idempotency
Per-client + idempotency-key dedupe is a security feature too — it blocks accidental duplicate billing on retries. Implemented in `app/billing/idempotency.py` against Redis with a 24 h TTL and a body-hash check that raises 409 on key reuse with different content.

---

## 8. Reverse proxy

### nginx 1.24
Single vhost (`nginx/csai-ocr.conf`) terminates TLS, applies basic-auth and IP allowlists, rate-limits the API, and proxies:

| Upstream | Path |
| --- | --- |
| FastAPI on `:8000` | `/api/v1/*`, `/admin/v1/*`, `/health`, `/metrics` |
| Streamlit on `:8503` | `/` (with basic-auth) |

`proxy_cache` is enabled for `/media/` (preview thumbnails).

---

## 9. Admin UI (`admin_ui/`)

### Streamlit 1.56
Multi-page operator console served on `:8503`. The page registry is now declared in `admin_ui/app.py` using the new `st.navigation` API and grouped:

```python
pg = st.navigation({
    "Clients":   [home, client_detail, actions, client_tmpls],
    "Templates": [templates, annotate],
    "Docs":      [field_guide, api_ref, user_manual],
})
```

Pages are stateful Python scripts re-executed top-to-bottom on every interaction. Cross-rerun toasts use a session_state flash pattern (`tpl_flash = (kind, msg)`) because `st.rerun()` would otherwise wipe transient `st.success(...)` calls.

### streamlit-drawable-canvas 0.9
Fabric.js-backed React component used on the **Annotate** page for drawing zone bounding boxes on top of the template's sample image. Returns rect objects in pixel space which are stored as `{x,y,w,h}` on each field.

### httpx 0.27
Synchronous HTTP client used by Streamlit pages to call the API (`admin_ui/api.py`). One client per page request.

---

## 10. Observability

### Prometheus
Scrape target is `/metrics` on the FastAPI app. Local Prometheus instance scrapes every 15s and feeds Grafana dashboards.

### prometheus-fastapi-instrumentator 6.1
Auto-instruments FastAPI with HTTP latency / request count / status code metrics. Custom counters defined in `app/metrics.py`:

| Metric | Type | Purpose |
| --- | --- | --- |
| `jobs_submitted_total{template,mime}` | counter | Inbound traffic |
| `jobs_total{status,endpoint}` | counter | Job lifecycle outcomes |
| `quota_denies_total` | counter | Plan limit rejections |
| `idempotency_conflicts_total` | counter | Duplicate-key collisions |
| `ocr_duration_seconds{status}` | histogram | OCR wall time per page-batch |
| `queue_depth{queue}` | gauge | Set on every `/metrics` scrape |

### python-json-logger 2.0
Structured JSON access + error logs configured via `config/logging.json` and loaded in `app/main.py` if the file exists. Each line is a single JSON object with `time`, `level`, `logger`, `request_id`, and message.

### journalctl
All services log to the systemd journal — no separate log files. Operators tail with `journalctl -u ocr-api -f`. Disk pressure managed by journald rotation (default `SystemMaxUse`).

### Grafana / Kibana / Elasticsearch
Already present on the host as separate units. Grafana visualizes the Prometheus metrics; Elasticsearch + Kibana ingest journald via Filebeat for free-text log search.

---

## 11. Testing

### pytest 8.2
Test runner. Tests under `tests/`. Style is "fast unit tests + a few integration tests against fakeredis + an in-memory SQLite ASGI client where possible".

### pytest-asyncio 0.23
Required because most code under test is async (DB, Redis). `asyncio_mode = "auto"` is set so tests don't need the `@pytest.mark.asyncio` decorator on every async test.

### fakeredis 2.23
In-memory Redis double. Lets the idempotency, quota, and queue code paths run in unit tests without spinning up a real broker.

### httpx 0.27
Doubles as the FastAPI `TestClient` transport (`AsyncClient(transport=ASGITransport(app=...))`).

---

## 12. Operations & maintenance scripts

`scripts/` directory, each invoked by a systemd timer:

| Script | Timer | Job |
| --- | --- | --- |
| `reap_stale_jobs.py` | `ocr-reaper.timer` | Mark `running` jobs older than N minutes as `failed` (defends against worker crashes that bypassed `on_failure`) |
| `reconcile_quota.py` | `ocr-reconcile.timer` | Recompute the Redis quota counter from `usage_logs` to repair drift |
| `sweep_disk.py` | `ocr-disksweep.timer` | Delete files in `OCR_STORAGE_DIR` that have no live job referencing them |

Each takes a `--dry-run` flag for safe rehearsal.

---

## 13. Repository layout

| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI app factory, middleware, router wiring, `/metrics` |
| `app/routers/` | HTTP routers — `ocr.py`, `verify.py`, `admin.py`, `admin_templates.py`, `health.py` |
| `app/upload.py` | MIME sniffing, size limit, `parse_page_indexes` |
| `app/queue.py` | RQ enqueue helper (`job_timeout=600`, `on_failure` callback) |
| `app/worker.py` | OCR worker entry, async `_process`, `on_ocr_failure` callback, `_reconcile_failed` helper |
| `app/rq_worker.py` | RQ worker bootstrap (`python -m app.rq_worker`) |
| `app/ocr.py` | Thin wrapper over PaddleOCR returning `[{box, text, score}]` |
| `app/templates/` | Template loader (`resolver.py`), strategy implementations (`strategies/anchor.py`, `regex.py`, `between.py`, `zone.py`), and `extractor.py` orchestrator |
| `app/billing/` | `models.py`, `jobs.py`, `quota.py`, `idempotency.py`, `periods.py`, `auth.py`, `redis_client.py` |
| `app/admin/` | Pydantic DTOs for admin endpoints |
| `app/metrics.py` | Prometheus counters/histograms/gauges |
| `app/errors.py` | Custom exception classes (`BadRequest`, `PayloadTooLarge`, `UnsupportedMedia`, `NotFound`, `IdempotencyConflict`, `QuotaExceeded`) and FastAPI handlers |
| `app/logging_mw.py` | JSON access log middleware |
| `admin_ui/app.py` | Streamlit nav root |
| `admin_ui/Home.py` | Dashboard page |
| `admin_ui/pages/` | Client detail, Actions, Templates, Annotate, Field Strategies Guide, API Reference, User Manual |
| `admin_ui/api.py` | Sync httpx client wrapper |
| `alembic/versions/*.sql` | Raw SQL migrations |
| `nginx/csai-ocr.conf` | Production vhost (TLS, basic-auth, rate limits) |
| `systemd/*.service`, `*.timer` | Unit files |
| `config/logging.json` | python-json-logger dictConfig |
| `config/fail2ban/` | Filter + jail definitions |
| `scripts/` | Maintenance jobs run by timers |
| `tests/` | pytest suite |

---

## 14. At-a-glance dependency table

| Package | Version | Layer | Why |
| --- | --- | --- | --- |
| fastapi | 0.115.0 | API | HTTP framework |
| uvicorn[standard] | 0.30.6 | API | ASGI server |
| python-multipart | 0.0.9 | API | multipart parsing |
| pydantic | 2.11.3 | API | validation/serialization |
| email-validator | 2.1.1 | API | `EmailStr` |
| paddlepaddle | 3.3.1 | OCR | DL framework (CPU) |
| paddleocr | 3.4.0 | OCR | det+rec models |
| paddlex | 3.4.3 | OCR | model registry |
| Pillow | 11.2.1 | OCR | image I/O & resize |
| python-magic | 0.4.27 | OCR | MIME sniff |
| rq | 1.16.2 | Queue | job queue |
| redis | 5.0.4 | Queue | client (sync + async) |
| sqlalchemy[asyncio] | 2.0.30 | DB | ORM |
| asyncpg | 0.29.0 | DB | async PG driver |
| psycopg2-binary | 2.9.9 | DB | sync PG driver (Alembic) |
| alembic | 1.13.2 | DB | migrations |
| python-dotenv | 1.0.1 | Sec | `.env` loader |
| argon2-cffi | 23.1.0 | Sec | API-key hashing |
| streamlit | 1.56.0 | UI | admin console |
| streamlit-drawable-canvas | 0.9.3 | UI | zone annotation |
| httpx | 0.27.0 | UI / Test | HTTP client / TestClient |
| prometheus-fastapi-instrumentator | 6.1.0 | Obs | auto-metrics |
| python-json-logger | 2.0.7 | Obs | structured logs |
| pytest | 8.2.0 | Test | runner |
| pytest-asyncio | 0.23.7 | Test | async tests |
| fakeredis | 2.23.2 | Test | redis double |

---

## 15. Why these choices, in one paragraph each

**Async Python end-to-end.** The workload is I/O bound at the API edge (Postgres + Redis + multipart upload) and CPU bound at the worker edge (PaddleOCR). Splitting into an async API + sync RQ worker means each side picks the concurrency model that fits, with Redis as the seam.

**Postgres + JSONB over a document store.** Billing data is relational (`clients`, `plans`, `billing_periods`, `usage_logs` join naturally), but template definitions and per-job input metadata are schemaless. Postgres JSONB gives both shapes without operating two databases.

**RQ over Celery.** The job graph is trivial (single-step OCR), workers are long-lived, and RQ's Redis-only model means one fewer broker to operate. Celery's complexity buys nothing here.

**Streamlit over a custom React admin.** The admin console is operator-only with maybe ten users. Streamlit's "everything is a Python script" model lets one engineer ship a full multi-page app in a day; React would take a week. The trade-off is the rerun-on-every-interaction model, handled with the flash pattern documented in the Templates page.

**PaddleOCR over Tesseract / cloud OCR.** Malaysian SSM certificates contain a mix of Latin and stylized text on a busy background; Tesseract accuracy is markedly worse on this corpus. Cloud OCR (Google Vision, AWS Textract) was rejected because the workload is per-document billable and per-page external API costs would erase margin.

**single-VPS systemd over Kubernetes.** PaddleOCR's 16 GB resident set is too large for cheap container nodes, and a single-tenant operator team has no need for a cluster. systemd timers + journalctl + Prometheus give 90% of the operability at 5% of the complexity.
