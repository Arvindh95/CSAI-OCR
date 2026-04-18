# CSAI-OCR Operations

Runtime facts for this project. Keep short — plans live in `IMPLEMENTATION_PLAN.md`, `BILLING_PLAN.md`, `PRODUCTION_PLAN.md`.

---

## Where things run

Everything prod runs on **VPS `173.212.247.3`** (Ubuntu 24.04). Local `D:\paddleocr` = dev checkout + git origin only. Do NOT run API/worker locally — they need Redis + Postgres + env vars the VPS has.

### VPS layout

| Path                  | Purpose                                       |
|-----------------------|-----------------------------------------------|
| `/opt/ocr-saas`       | Active git checkout (owner `claudeuser`)      |
| `/opt/ocr-saas/venv`  | Python 3.12 venv                              |
| `/opt/ocr-saas/.env`  | Secrets (`DATABASE_URL`, `REDIS_URL`, `ADMIN_TOKEN`, `API_KEY_PEPPER`, `ENV`, `CORS_ALLOWED_ORIGINS`) |
| `/opt/paddleocr`      | Legacy paddleocr model cache                  |
| `/var/log/ocr/`       | Worker logs (`worker-1.log`, `worker-1.err`)  |

### Services (systemd, all `User=claudeuser`)

| Unit                  | Binds            | ExecStart                                                                 |
|-----------------------|------------------|---------------------------------------------------------------------------|
| `ocr-api.service`     | `127.0.0.1:8003` | `uvicorn app.main:app --host 127.0.0.1 --port 8003 --workers 1`           |
| `ocr-worker@1.service`| `127.0.0.1:8004` (metrics) | `python -m app.rq_worker` (RQ `SimpleWorker`, queue `csai-ocr`) |
| `ocr-ui.service`      | `127.0.0.1:8503` | `streamlit run admin_ui/Home.py --server.port 8503 --server.headless true` |
| `nginx.service`       | `0.0.0.0:80`     | Reverse proxy (routes below)                                              |
| `redis-server.service`| `127.0.0.1:6379` |                                                                           |
| `postgresql.service`  | `127.0.0.1:5432` | DB `ocr_billing`, user `ocr_user`                                         |

### Monitoring (docker compose, `deploy/monitoring/`)

| Service    | Binds            | Notes                                 |
|------------|------------------|---------------------------------------|
| Prometheus | `127.0.0.1:9090` | `network_mode: host`, scrapes 8003 + 8004 |
| Grafana    | `127.0.0.1:3000` | Dashboard auto-provisioned: `csai-ocr.json` |

## Nginx routing (`/etc/nginx/sites-enabled/csai-ocr`)

All via `http://173.212.247.3/` port 80.

| Path                         | Backend                       | Gate                        |
|------------------------------|-------------------------------|-----------------------------|
| `/api/v1/*`                  | 127.0.0.1:8003 (client API)   | Rate limit per-key + per-IP |
| `/ocr`, `/verify`, `/health` | 127.0.0.1:8003 (legacy)       | Rate limit per-IP           |
| `/admin/v1/*`                | 127.0.0.1:8003 (admin API)    | `allow 127.0.0.1` only      |
| `/docs`, `/redoc`, `/openapi.json` | 127.0.0.1:8003          | `allow 127.0.0.1` only      |
| `/metrics`                   | 127.0.0.1:8003                | `allow 127.0.0.1` only      |
| `/` (everything else)        | 127.0.0.1:8503 (Streamlit UI) | basic auth, `.htpasswd-csai`|

**Admin UI access:** browse `http://173.212.247.3/`, basic auth prompt. Streamlit on VPS calls admin API over loopback so nginx allowlist is satisfied. Do NOT open `/admin/v1/` from your laptop browser — 403.

---

## Access

```bash
ssh -i ~/.ssh/id_ed25519 root@173.212.247.3          # root, for systemctl / nginx
ssh -i ~/.ssh/id_ed25519 claudeuser@173.212.247.3     # for git operations in /opt/ocr-saas
```

Git as root inside `/opt/ocr-saas` = `fatal: dubious ownership` error. Always use `sudo -u claudeuser bash -c 'cd /opt/ocr-saas && git pull'` when SSH'd as root.

GitHub repo: `git@github.com:Arvindh95/CSAI-OCR.git` (SSH alias `github-csai` configured on VPS).

---

## Deploy flow

Local → GitHub → VPS pull → restart.

```bash
# 1. Local (D:\paddleocr)
git add -- <files>
git commit -m "..."
git push

# 2. VPS (from laptop shell)
ssh -i ~/.ssh/id_ed25519 root@173.212.247.3 \
  "sudo -u claudeuser bash -c 'cd /opt/ocr-saas && git pull' && \
   systemctl restart ocr-api ocr-worker@1 && \
   sleep 3 && systemctl is-active ocr-api ocr-worker@1"
```

**Restart matrix** — which service to bounce per change:

| Changed                       | Restart                                    |
|-------------------------------|--------------------------------------------|
| `app/routers/`, `app/*.py`    | `ocr-api`                                  |
| `app/worker.py`, `app/rq_worker.py`, `app/templates/` strategies | `ocr-worker@1` |
| Anything used by both (e.g. `app/db.py`, `app/billing/`) | `ocr-api ocr-worker@1` |
| `admin_ui/`                   | `ocr-ui`                                   |
| `alembic/versions/`           | Run migration manually first, then `ocr-api ocr-worker@1` |
| `deploy/monitoring/`          | `docker compose -f deploy/monitoring/docker-compose.yml up -d` |
| `/etc/nginx/sites-enabled/csai-ocr` | `nginx -t && systemctl reload nginx` |

---

## Database migrations (Alembic)

```bash
ssh -i ~/.ssh/id_ed25519 claudeuser@173.212.247.3
cd /opt/ocr-saas
source venv/bin/activate
alembic upgrade head        # apply new migrations after git pull
alembic current             # show current revision
alembic downgrade -1        # roll back one (careful)
```

Postgres creds come from `.env` via `app/db.py`.

---

## Logs

```bash
# API (stdout → journal)
journalctl -u ocr-api -f -n 100

# Worker (stdout → /var/log/ocr/)
tail -f /var/log/ocr/worker-1.log
tail -f /var/log/ocr/worker-1.err

# Streamlit UI
journalctl -u ocr-ui -f

# Nginx access/error
tail -f /var/log/nginx/csai-ocr.access.log /var/log/nginx/csai-ocr.error.log
```

---

## Smoke tests

```bash
# From VPS (bypasses nginx allowlist)
curl -s http://127.0.0.1:8003/health
curl -s http://127.0.0.1:8003/metrics | head -20
curl -s http://127.0.0.1:8004/metrics | grep csai_jobs_total

# From laptop (through nginx)
curl -s http://173.212.247.3/health
curl -sS -u admin:<pwd> http://173.212.247.3/            # Streamlit UI landing
curl -sS -H "X-API-Key: ocr_live_..." http://173.212.247.3/api/v1/jobs
```

Admin API (`/admin/v1/*`) is **not** reachable from laptop — 403 by nginx allowlist. Admin UI (Streamlit) does the proxying from inside VPS.

---

## Ports quick reference

| Port | Where       | What                                   |
|------|-------------|----------------------------------------|
| 80   | VPS public  | nginx                                  |
| 5432 | VPS loopback| Postgres                               |
| 6379 | VPS loopback| Redis                                  |
| 8003 | VPS loopback| FastAPI (uvicorn)                      |
| 8004 | VPS loopback| Worker prometheus `start_http_server`  |
| 8503 | VPS loopback| Streamlit admin UI                     |
| 9090 | VPS loopback| Prometheus (docker, `network_mode: host`) |
| 3000 | VPS loopback| Grafana (docker)                       |

---

## Template extraction strategies

See `app/templates/strategies/`:

- `anchor` — find label text, read value in `direction` (right | below | same_line_colon), bounded by `max_distance_px`
- `zone` — coordinate rect (`x,y,w,h` native pixels or normalized 0..1), match lines by bbox overlap ≥ `min_overlap` (default 0.3), merge if `merge=true`
- `regex` — re.search on joined OCR text, return capture `group`

Post-process: `trim | uppercase | lowercase | number | date`.

---

## Admin UI — Annotate page workflow

1. Create template on **Templates** tab (Browse/Create)
2. Upload page image via **Templates** detail panel
3. Open **Annotate** → pick page → click **Load OCR lines (preview)** once (caches OCR result in session state)
4. Draw rectangle on canvas → preview box shows matched lines + merged text live
5. Tune `min_overlap` slider until only intended lines are captured
6. Set field name + post_process → **Add zone field**
7. Repeat per field; edit raw JSON if needed; delete fields with ✕
8. **Save** — pick "In-place (overwrite)" by default; "New version" only when you need to keep old template alive alongside

### Gotchas fixed

- Streamlit 1.56 + drawable-canvas 0.9.3 incompat → shim in `admin_ui/pages/5_Annotate.py` wraps `image_to_url` signature
- `text_area` widget state is sticky across reruns — synced programmatically via content-hash in `raw_key`/`hash_key`
- Zone strategy originally matched by line center point → missed lines when zone was slightly off. Now uses bbox overlap ratio (`app/templates/strategies/zone.py`)
- Hard-deleting a template was unlinking images shared with sibling versions. New-version PUT now copies physical image files to new template dir; hard-delete unlinks only files inside own dir

---

## Observability (Phase 6 complete)

Metrics exposed:

- `csai_jobs_submitted_total{template,mime}` — API increment on enqueue
- `csai_jobs_total{status,endpoint}` — worker increment on completion
- `csai_ocr_duration_seconds{status}` — worker histogram
- `csai_idempotency_conflicts_total`
- `csai_quota_denies_total`
- `csai_auth_failures_total`
- `csai_queue_depth` — gauge polled from Redis
- Plus `prometheus-fastapi-instrumentator` HTTP metrics

Grafana dashboard UID auto-provisioned from `deploy/monitoring/grafana/dashboards/csai-ocr.json`. 9 panels: queue depth, active clients, quota/auth failure rates, jobs/min, jobs by template, OCR duration p50/p95/p99, HTTP status, HTTP latency p95.

**Worker metrics quirk:** default RQ `Worker` forks per job → counter increments in child are lost. We use `SimpleWorker` (in-process) so metrics survive. Trade-off: one bad job can crash the worker; systemd `Restart=on-failure` handles it.

---

## Load test

`deploy/load/locustfile.py` — `OCRUser` with `between(3, 6)` wait, generates random invoice PNGs. Run from VPS (not laptop — client API gated per-key rate limit, you'd throttle yourself):

```bash
cd /opt/ocr-saas
source venv/bin/activate
export CSAI_API_KEY=ocr_live_...
locust -f deploy/load/locustfile.py --host http://127.0.0.1:8003
```

Last run: 59 submits / 0 fail @ 10 users × 2 min.

---

## Backups & hardening

**Not set up.** Phases 8 (backups) and 10 (hardening) deferred. Postgres data at `/var/lib/postgresql/17/main/`, uploaded page images at `/opt/ocr-saas/storage/templates/`. If you need a snapshot, rsync both to off-box storage.

---

## Known gaps

- No SSL/TLS. Everything over HTTP. Add certbot + 443 listener when going outside dev.
- No client portal / self-serve. Admin UI is the only interface.
- `/api/v1/*` is Phase 4 placeholder in nginx but wired in FastAPI — keep both in sync.
- Worker runs a single instance (`ocr-worker@1`). Scale by starting `ocr-worker@2`, `@3`, etc. — systemd template unit already supports it.
