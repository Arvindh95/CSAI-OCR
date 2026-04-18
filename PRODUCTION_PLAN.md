# OCR API — Full Production Implementation Plan

---

## Decisions (Final)

| # | Decision |
|---|---|
| 1 | **Hard-block** at quota — 429 returned, no overage |
| 2 | **Async** — POST returns `job_id`, client polls `/jobs/{id}` |
| 3 | **No domain yet** — HTTP only now, HTTPS added when domain ready |
| 4 | **Per-client configurable plans** — no fixed tiers |
| 5 | **Quota reserved on submit, committed on completion** (see §Quota Accounting) |
| 6 | **1 page = 1 uploaded file**. PDF not supported in v1. Multi-file upload not supported in v1. |
| 7 | **Deploy target = Linux** (Ubuntu 22.04 / Debian 12). Windows for dev only. |
| 8 | **Chatbot out of scope** for this plan. OCR stack only. Chatbot services stay on current host, not proxied by new nginx config. |
| 9 | **No backups, no offsite storage, no image archive.** Single-VPS infra only. Data loss risk accepted. |
| 10 | **All public routes versioned under `/api/v1/` and `/admin/v1/`.** Breaking changes go to `/v2/`. |
| 11 | **Usage alerts = polling only.** No email/webhook to clients in v1. Consumers read `X-Transactions-Remaining` header or poll `/usage/me`. |
| 12 | **Document extraction = template-driven** (Phase 9). Admins define templates via visual UI (Label Studio). No more hardcoded parsers per format after Phase 9 lands. SSM parser kept as built-in fallback. |

---

## Out of Scope (v1)

Explicit non-goals — document now, revisit later:

- Database backups, offsite storage, image archive (Decision #9).
- Staging environment / CI/CD pipelines — deploys are manual (`scripts/deploy.sh`).
- PDF input, multi-file upload, multi-page per transaction.
- Email / webhook notifications to clients (quota warnings, job completion).
- GDPR data-subject deletion workflow (manual via admin endpoint if requested).
- Chatbot services — not proxied by new nginx.
- GPU inference — CPU only on current VPS (PaddleOCR p95 ~3–8s per image on modern CPU).
- Full audit-log review UI — raw table only.

---

## Current State

| Component | Status | Notes |
|---|---|---|
| OCR Backend (`app/main.py`) | Running, port 8002 | No auth, synchronous |
| OCR Frontend (`client.py`) | Running, port 8502 | Streamlit |
| Chatbot Backend (`api_server.py`) | Running, port 8000 | Separate app — out of scope |
| Chatbot Frontend (`grp_chat.py`) | Running, port 8501 | Streamlit — out of scope |
| SSL / HTTPS | None | Deferred |
| Auth | None | |
| Queue | None | |
| Billing / DB | None | |
| Monitoring | None | |
| Process manager | nohup (fragile) | |

---

## Likely Blockers (confirmed on VPS 2026-04-17)

Real risks observed on target VPS (`173.212.247.3`, Ubuntu 24.04.4 LTS, 23 GB RAM). Resolve or plan mitigation **before Phase 1**.

| # | Blocker | Impact | Mitigation |
|---|---------|--------|-----------|
| 1 | **Port 80 contention** — nginx already serves live `grp-chat.service` (`:8501`, `:8502`) and legacy OCR (`:8000`, `:8002`). Any edit to `/etc/nginx/sites-enabled/*` risks breaking live chat. | Live outage on unrelated service. | Audit `sites-enabled` first. Add new `server_name` / `location` block; never overwrite default. Reload + test both stacks. |
| 2 | **Memory pressure** — Ollama (`:11434`), ELK (`:5601/:9200/:9300`), grp-chat, 2× uvicorn, 2× streamlit, PaddleOCR model already resident. Adding Postgres + Redis + new API + worker + Prometheus + Grafana could push into swap. | OOM killer, latency spikes. | Baseline `free -h` + `ps aux --sort=-%mem` before Phase 3. Set systemd `MemoryMax=` per service. Consider co-locating Prometheus+Grafana off-VPS if tight. |
| 3 | **PaddleOCR model double-load during cutover** — live service holds model (~1–2 GB). New API loads its own copy. Running parallel = 2× RAM. | Transient OOM on cutover. | Cutover strategy: stop legacy `:8000/:8002` **before** starting new API. No parallel run. |
| 4 | **Live service on `/opt/paddleocr`** — root-owned, serving real traffic, has Windows path literal bug (`PADDLE_PDX_CACHE_HOME = D:\docling\models\paddlex` created as a Linux folder). | Chown mid-flight = log file perms break + service crash. | Build new stack in `/opt/ocr-saas` owned by `claudeuser`. Leave legacy dir alone. Cutover = stop legacy, switch nginx upstream, delete later. |
| 5 | **Billing defaults unconfirmed** — Phase 3 schema hardcodes: calendar-month UTC periods, failed jobs free, MYR, manual admin provisioning, CSV export only, no tax/portal. | Schema migration cost if wrong. | Lock defaults in §Decisions **before** writing Alembic migration. Answer the 7 billing questions explicitly. |
| 6 | **No domain / no TLS** — plan assumes LE cert. IP-only = no HTTPS, no SNI, rate limiters keyed on raw IP (fragile behind NAT'd clients). | API keys traverse plaintext. No brand trust. | Acquire domain + point A record to `173.212.247.3` before Phase 7. Until then: treat prod as private beta, issue keys only to controlled clients. |
| 7 | **UFW self-lockout risk** — default-deny applied without prior `ufw allow 22/tcp` cuts the SSH session. | Locked out of VPS, recovery needs Contabo console. | Always `ufw allow 22/tcp` + `ufw allow from <home_ip>` **first**, enable **second**. Test via a second SSH connection before closing the first. |
| 8 | **fail2ban + current SSH traffic** — deploy script SSH, monitoring checks, existing admin IPs may trip bans. | Accidental self-ban. | Whitelist `sshd` jail for home IP + `127.0.0.1` in `jail.local`. Start with `bantime = 10m` not permanent until tuned. |
| 9 | **No backup / no rollback** — single-VPS plan explicitly strips backups per user decision. Disk corruption or dropped DB = total data loss. | Accepted risk. | Snapshot via Contabo panel before Phase 3 schema apply + before every prod deploy. Document in runbook. |
| 10 | **Systemd unit contention with legacy** — old OCR runs under `nohup`, not systemd. New `ocr-api.service` must not conflict on port, working dir, or log paths. | Port bind failure on boot. | New service binds `127.0.0.1:8010` (not 8000/8002). Separate unit name. Separate logs under `/var/log/ocr-saas/`. |
| 11 | **Existing nginx version / module set unknown** — adding rate-limit zones, `limit_req_zone`, `auth_basic`, `map` directives may require modules or syntax checks against running nginx. | Config reload fails, takes down live nginx. | `nginx -t` before reload. `nginx -V` to confirm modules. Keep diff small per reload. |
| 12 | **Redis `maxmemory-policy noeviction` required for quota counters** — but other services on host (if any use Redis later) may assume LRU. Conflict if shared. | Quota counters silently evicted = over/under-billing. | Run a dedicated Redis instance for OCR (different port or socket). Do not share with ELK/chatbot if they ever add Redis. |

All 12 must be addressed in pre-flight checklist (see `IMPLEMENTATION_PLAN.md` Phase 0).

---

## Target Architecture

```
[Clients — Web / PHP / Python / C# / Mobile]
                    │ HTTP (HTTPS later)
                    ▼
        ┌───────────────────────┐
        │   Nginx  (port 80)    │
        │   rate limit per IP   │
        │   401-burst block     │
        │   /api/v1/*   → 8002  │
        │   /admin/v1/* → 8002 (IP allowlist + token) │
        │   /ui/*       → 8502 (basic-auth) │
        └──────────┬────────────┘
                   │
        ┌──────────▼────────────┐
        │   OCR API  (FastAPI)  │
        │   Auth → Quota reserve│
        │   Enqueue job         │
        │   /jobs/{id} poll     │
        └──────────┬────────────┘
                   │
        ┌──────────▼────────────┐
        │   Redis               │
        │   - RQ job queue      │
        │   - quota counters    │
        └──────────┬────────────┘
                   │
        ┌──────────▼────────────┐
        │   OCR Workers (RQ)    │
        │   PaddleOCR loaded    │
        │   Commit quota on done│
        │   Retry policy        │
        └──────────┬────────────┘
                   │
        ┌──────────▼────────────┐
        │   PostgreSQL          │
        │   clients / plans     │
        │   periods / jobs      │
        │   usage_log / billing │
        └──────────┬────────────┘
                   │
        ┌──────────▼────────────┐
        │ Prometheus + Grafana  │
        │ uptime/latency/quota  │
        └───────────────────────┘

  [Phase 9 — admin only]
        ┌───────────────────────┐
        │  Label Studio         │  ← visual template editor
        │  /labelstudio/*       │     (admin IP allowlist)
        └───────────────────────┘
```

---

## Quota Accounting (Reserve → Commit model)

**Goal:** never overshoot limit even under burst submit.

**Source of truth:** Redis counter per client per period, reconciled to Postgres.

- Key: `quota:{client_id}:{period_id}` → integer count of *reserved + committed* transactions.
- Atomic `INCR` at submit, `DECR` at cancel/fail.
- Postgres `usage_log` = ledger, written by worker on final state. Reconciliation job re-derives Redis counter from ledger every 5 min (idempotent).

### Submit flow

```
1. Auth — resolve client from api_key hash
2. Resolve current period (open period row, create if missing)
3. Validate file (extension, size, 1 page per request)
4. Redis: new = INCR quota:{cid}:{pid}
5. IF new > plan.max_transactions:
       DECR quota key, return 429
6. INSERT jobs row (status=queued, reserved=true)
7. Enqueue RQ task, return 202
```

### Worker flow

```
1. UPDATE jobs status=processing, started_at=now()
2. Run PaddleOCR
3. On success:
     UPDATE jobs status=done, result, completed_at
     INSERT usage_log (status=success)
     — counter already reserved, no change
4. On failure (after all retries):
     UPDATE jobs status=failed, error_msg
     INSERT usage_log (status=error)
     Redis DECR quota:{cid}:{pid}  ← release reservation (failures don't bill)
5. Cleanup temp file
```

### Decisions on edge cases

| Case | Behavior |
|---|---|
| Worker crash mid-job | Stale reaper (systemd timer, every 1 min) fails jobs `started_at < now() - 10 min AND status=processing`, then DECR |
| Client cancels (future feature) | Only if status=queued; DECR |
| Plan change mid-period | New limit applies immediately; existing reservations honored |
| Period rollover | Cron at period boundary creates new `periods` row, resets Redis key |
| Redis flush / cold start | Reconcile job reads `SELECT count(*) FROM usage_log WHERE client_id=? AND period_id=?` + pending reserved jobs, rebuilds Redis |

---

## Async API Contract

All routes prefixed `/api/v1/` (clients) or `/admin/v1/` (operators). Examples below show route after version prefix.

### Standard error envelope

Every 4xx/5xx response shares this shape:
```json
{ "error": { "code": "quota_exceeded", "message": "human-readable", "detail": {...} } }
```

Codes: `invalid_api_key`, `account_suspended`, `quota_exceeded`, `invalid_file`, `file_too_large`, `idempotency_conflict`, `not_found`, `rate_limited`, `internal_error`.

### Submit job
```
POST /api/v1/ocr
Headers:
  X-API-Key: ocr_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  Idempotency-Key: <client-generated UUID, optional but recommended>
Body: multipart/form-data  { file: image.jpg }   ← 1 file = 1 page = 1 transaction

→ 202 Accepted
{
  "job_id": "3f7a1c2d-...",
  "status_url": "/api/v1/jobs/3f7a1c2d-...",
  "queued_at": "2025-04-17T10:00:00Z"
}

→ 200 OK  (Idempotency-Key replay — returns existing job, no new reservation)
→ 400  invalid_file       { "detail": { "allowed": [".jpg",".png",...] } }
→ 400  file_too_large     { "detail": { "max_bytes": 20971520 } }
→ 401  invalid_api_key
→ 403  account_suspended
→ 409  idempotency_conflict  (same Idempotency-Key, different body)
→ 429  quota_exceeded     { "detail": { "used": 2000, "limit": 2000, "period_reset": "..." } }
→ 429  rate_limited       (nginx per-key or per-IP)
```

**Idempotency semantics:** if the same `(client_id, Idempotency-Key)` arrives within 24h, return the original `job_id` with `200` instead of creating a new one. Body hash (SHA-256 of file) must match — mismatch → `409`. Keys stored 24h in Redis: `idemp:{cid}:{key}` → `{job_id, body_hash}`.

### Poll result
```
GET /api/v1/jobs/{job_id}?fields=status|full    (default: full)
Headers: X-API-Key: ocr_live_xxx
         If-None-Match: "<etag from previous poll>"

→ 200
ETag: "<sha1 of result>"
{
  "job_id": "3f7a1c2d-...",
  "status": "queued | processing | done | failed",
  "queued_at": "...",
  "started_at": "...",      ← null until processing
  "completed_at": "...",    ← null until done/failed
  "attempts": 1,
  "result": {               ← null until done; omitted if fields=status
    "lines": [{"text": "...", "confidence": 0.99}],
    "fields": { "company_name": "...", "reg_no": "..." }
  },
  "error": null             ← populated if failed (after all retries exhausted)
}

→ 304 Not Modified   (ETag match — zero-body, poll-friendly)
→ 404 not_found      Job not found or belongs to different client
```

- `fields=status` returns the envelope without `result` — cheap polling while job runs.
- `ETag` set once `completed_at` is non-null; clients should send `If-None-Match` on subsequent polls.

### Verify job
```
POST /api/v1/verify
Headers: X-API-Key, Idempotency-Key (optional)
Body: multipart/form-data  { file, name?, reg_no? }   ← at least one of name/reg_no

→ 202 Accepted  { "job_id": "...", "status_url": "..." }

GET /api/v1/jobs/{job_id}  → same poll pattern, result contains verification fields
```

### Usage check (client self-service)
```
GET /api/v1/usage/me
Headers: X-API-Key: ocr_live_xxx

→ 200
{
  "transactions_used": 150,
  "transactions_remaining": 1850,
  "transactions_limit": 2000,
  "pages_per_txn_limit": 1,
  "period_start": "2025-04-01T00:00:00Z",
  "period_end":   "2025-05-01T00:00:00Z",
  "period_type":  "monthly"
}
```

### Response headers on every request
```
X-Transactions-Used: 150
X-Transactions-Remaining: 1850
X-Period-Reset: 2025-05-01T00:00:00Z
X-Request-Id: <uuid>         ← generated per request, echoed in logs
```

### Health endpoints

```
GET /api/v1/health        (public, no auth)
→ 200 { "status": "ok" }
→ 503 { "status": "degraded", "checks": { ... } }
```
Shallow check — process alive + config loaded. Safe to expose publicly.

```
GET /admin/v1/health      (admin-gated)
→ 200 {
  "status": "ok",
  "checks": {
    "db":            { "ok": true, "latency_ms": 3 },
    "redis":         { "ok": true, "latency_ms": 1 },
    "queue_depth":   12,
    "workers_up":    2,
    "stuck_jobs":    0,
    "disk_free_pct": 42
  }
}
```
Deep probe — DB + Redis roundtrip, queue depth, worker heartbeat, stale jobs, disk. This is what Prometheus scrapes for `up` alerts.

---

## Implementation Phases

---

### Phase 1 — Stability  _(Week 1, Days 1–2)_

**Goal:** Services survive reboot. Crashes auto-recover.

#### 1.1 systemd — OCR API

`/etc/systemd/system/ocr-api.service`
```ini
[Unit]
Description=OCR API
After=network.target redis.service postgresql.service

[Service]
User=claudeuser
WorkingDirectory=/opt/paddleocr
EnvironmentFile=/opt/paddleocr/.env
ExecStart=/opt/paddleocr/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --workers 2 --log-config /opt/paddleocr/logging.json
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal

# Sandboxing
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/paddleocr /var/log/ocr

[Install]
WantedBy=multi-user.target
```

> API workers = 2 (stateless, no OCR model). OCR model only loaded in worker service.

#### 1.2 systemd — OCR Worker (templated, N copies)

`/etc/systemd/system/ocr-worker@.service`
```ini
[Unit]
Description=OCR Queue Worker %i
After=redis.service

[Service]
User=claudeuser
WorkingDirectory=/opt/paddleocr
EnvironmentFile=/opt/paddleocr/.env
Environment=PADDLEOCR_HOME=/opt/paddleocr/.paddleocr_cache
ExecStart=/opt/paddleocr/venv/bin/rq worker ocr-queue --url redis://localhost:6379 --name worker-%i
Restart=always
RestartSec=5
# Graceful — let RQ finish current job before exit
KillSignal=SIGINT
TimeoutStopSec=120
StandardOutput=journal
StandardError=journal

# Sandboxing
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/paddleocr /var/log/ocr /tmp/ocr_uploads

[Install]
WantedBy=multi-user.target
```

> RQ handles `SIGINT` as "finish current job, then exit". `TimeoutStopSec=120` gives OCR time to complete. After that, systemd escalates to `SIGKILL` and the reaper cleans up.

Enable N workers:
```bash
systemctl enable ocr-worker@1 ocr-worker@2
systemctl start  ocr-worker@1 ocr-worker@2
```

> Each worker loads PaddleOCR once → constant RAM per worker (~1.5–2 GB). Scale by enabling more instances when queue depth >100 sustained.

#### 1.3 systemd — OCR UI

`/etc/systemd/system/ocr-ui.service`
```ini
[Unit]
Description=OCR Streamlit UI
After=ocr-api.service

[Service]
User=claudeuser
WorkingDirectory=/opt/paddleocr
ExecStart=/opt/paddleocr/venv/bin/streamlit run client.py --server.port 8502 --server.address 127.0.0.1 --server.headless true
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### 1.4 systemd — Stale-job reaper

`/etc/systemd/system/ocr-reaper.service`
```ini
[Unit]
Description=OCR stale-job reaper

[Service]
Type=oneshot
User=claudeuser
EnvironmentFile=/opt/paddleocr/.env
ExecStart=/opt/paddleocr/venv/bin/python /opt/paddleocr/scripts/reap_stale_jobs.py
```

`/etc/systemd/system/ocr-reaper.timer`
```ini
[Unit]
Description=Run OCR reaper every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min

[Install]
WantedBy=timers.target
```

Reaper logic: fail jobs where `status='processing' AND started_at < now() - interval '10 minutes'`, then `DECR` Redis quota.

#### 1.5 systemd — Quota reconciliation

`/etc/systemd/system/ocr-reconcile.timer` (every 5 min). Rebuilds Redis quota counters from Postgres ledger to heal drift / Redis restart.

#### 1.6 PaddleOCR model pre-cache

Models are ~200MB, downloaded on first inference. Without pre-cache, first request hangs 30–60s and may fail if network blips.

One-time setup:
```bash
mkdir -p /opt/paddleocr/.paddleocr_cache
chown claudeuser:claudeuser /opt/paddleocr/.paddleocr_cache
sudo -u claudeuser PADDLEOCR_HOME=/opt/paddleocr/.paddleocr_cache \
    /opt/paddleocr/venv/bin/python -c \
    "from app.ocr import get_ocr; get_ocr()"
```

Verify cache populated before enabling `ocr-worker@*`. Same `PADDLEOCR_HOME` env in worker unit file.

#### 1.7 Structured logging

`/opt/paddleocr/logging.json` — uvicorn log config emitting JSON lines to journald:
```json
{
  "version": 1,
  "formatters": {
    "json": {
      "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
      "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(client_id)s"
    }
  },
  "handlers": {
    "default": { "class": "logging.StreamHandler", "formatter": "json" }
  },
  "root": { "level": "INFO", "handlers": ["default"] }
}
```

Add `python-json-logger` to requirements. FastAPI middleware injects `request_id` (UUID) + `client_id` (after auth) into log context.

Query: `journalctl -u ocr-api -o json | jq 'select(.client_id == "42")'`.

#### 1.8 systemd — Disk sweep

`/etc/systemd/system/ocr-disksweep.service` + `.timer` (daily).
```python
# scripts/sweep_disk.py
# - Delete /tmp/ocr_uploads/* older than 1 hour (temp upload orphans)
# - Vacuum PADDLEOCR_HOME/.cache if >500MB
# - Warn to journal if /opt filesystem <20% free
```

Alternative: `systemd-tmpfiles` rule:
```
/etc/tmpfiles.d/ocr.conf:
d /tmp/ocr_uploads 0750 claudeuser claudeuser 1h -
```

#### 1.9 Enable all services

```bash
systemctl daemon-reload
systemctl enable ocr-api ocr-worker@1 ocr-worker@2 ocr-ui \
                 ocr-reaper.timer ocr-reconcile.timer ocr-disksweep.timer
systemctl start  ocr-api ocr-worker@1 ocr-worker@2 ocr-ui \
                 ocr-reaper.timer ocr-reconcile.timer ocr-disksweep.timer
systemctl status ocr-api ocr-worker@1 ocr-ui
```

#### 1.10 Log rotation

`/etc/logrotate.d/ocr`
```
/opt/paddleocr/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
```

---

### Phase 2 — Nginx  _(Week 1, Days 3–4)_

**Goal:** Single entry point on port 80. Backend ports not directly accessible. Rate limiting. Admin + UI protected.

#### 2.1 Firewall

```bash
ufw allow 22/tcp     # SSH
ufw allow 80/tcp     # HTTP (nginx)
ufw deny  8000       # chatbot api — internal
ufw deny  8002       # ocr api    — internal
ufw deny  8501       # chatbot ui — internal
ufw deny  8502       # ocr ui     — internal
ufw enable
```

All backend services bind to `127.0.0.1` (belt + braces). Verify:
```bash
ss -tlnp | grep -E '8002|8502'   # must show 127.0.0.1:, not 0.0.0.0:
```

#### 2.2 Nginx config

`/etc/nginx/sites-available/ocr`
```nginx
# Rate limit zones
limit_req_zone $http_x_api_key     zone=per_key:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=per_ip:10m  rate=100r/m;

server {
    listen 80;
    server_name 173.212.247.3;

    # --- Client API (versioned) ---
    location /api/v1/ {
        limit_req zone=per_key burst=20 nodelay;
        limit_req zone=per_ip  burst=30 nodelay;

        proxy_pass         http://127.0.0.1:8002/api/v1/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Request-Id $request_id;
        proxy_read_timeout 30s;
        client_max_body_size 20M;
    }

    # --- Admin API (IP allowlist + app-level token + audit log) ---
    location /admin/v1/ {
        allow 203.0.113.0/24;   # REPLACE with office/VPN CIDR
        allow 127.0.0.1;
        deny  all;

        proxy_pass         http://127.0.0.1:8002/admin/v1/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Request-Id $request_id;
        client_max_body_size 1M;
    }

    # --- Block FastAPI docs in prod (leak endpoint list) ---
    location ~ ^/(docs|redoc|openapi\.json)$ {
        allow 203.0.113.0/24;   # office only
        allow 127.0.0.1;
        deny  all;
        proxy_pass http://127.0.0.1:8002;
    }

    # --- Streamlit UI (basic auth) ---
    location / {
        auth_basic           "OCR UI";
        auth_basic_user_file /etc/nginx/.htpasswd-ocr;

        proxy_pass         http://127.0.0.1:8502/;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 86400s;
    }
}
```

```bash
htpasswd -c /etc/nginx/.htpasswd-ocr admin
ln -s /etc/nginx/sites-available/ocr /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

#### 2.3 Brute-force lockout (fail2ban)

Unlimited 401 attempts = key enumeration. Install fail2ban, watch nginx access log for 401 bursts:

```bash
apt install fail2ban
```

`/etc/fail2ban/filter.d/ocr-api-401.conf`
```
[Definition]
failregex = ^<HOST> .* "POST /api/v1/.* HTTP/.*" 401
ignoreregex =
```

`/etc/fail2ban/jail.d/ocr-api.conf`
```
[ocr-api-401]
enabled  = true
filter   = ocr-api-401
logpath  = /var/log/nginx/access.log
maxretry = 20
findtime = 60
bantime  = 3600
action   = iptables-multiport[name=ocr, port="80,443"]
```

Thresholds: 20 × 401 in 60s from one IP → ban 1h. Tune after observing real traffic.

> When domain ready: add `server_name yourdomain.com;`, run certbot, update `listen 443 ssl`, redirect 80→443.

**App-level docs gate** (belt + braces — nginx IP allow is primary):
```python
# main.py
docs_url  = "/docs"  if os.getenv("ENV") != "production" else None
redoc_url = "/redoc" if os.getenv("ENV") != "production" else None
app = FastAPI(..., docs_url=docs_url, redoc_url=redoc_url)
```

---

### Phase 3 — Database  _(Week 2, Days 1–2)_

**Goal:** PostgreSQL running with full billing schema, period tracking, hashed keys.

#### 3.1 Install

```bash
apt install postgresql postgresql-contrib libmagic1
sudo -u postgres psql -c "CREATE USER ocr_user WITH PASSWORD 'STRONG_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE ocr_billing OWNER ocr_user;"
```

> `libmagic1` required by `python-magic` for MIME sniffing on uploads.

#### 3.2 Migration tooling

Use **Alembic** (sqlalchemy-native). Raw SQL for v1 migration only; all subsequent schema changes via alembic revisions.

```bash
cd /opt/paddleocr
venv/bin/alembic init migrations
# edit alembic.ini + env.py to read DATABASE_URL from .env
```

Add to requirements: `alembic==1.13.2`.

#### 3.3 Initial schema

`migrations/versions/001_billing_schema.sql` (or alembic revision)
```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- for gen_random_uuid()

-- Clients
CREATE TABLE clients (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    api_key_hash    BYTEA NOT NULL UNIQUE,          -- SHA-256(raw_key)
    api_key_prefix  TEXT NOT NULL,                  -- first 12 chars for admin display
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_clients_api_key_hash ON clients(api_key_hash);
CREATE INDEX idx_clients_active ON clients(is_active) WHERE is_active;

-- Plans (one active row per client; history via effective_to)
CREATE TABLE plans (
    id                   SERIAL PRIMARY KEY,
    client_id            INT REFERENCES clients(id) ON DELETE CASCADE,
    max_transactions     INT NOT NULL DEFAULT 2000,
    max_pages_per_txn    INT NOT NULL DEFAULT 1,    -- v1: always 1
    reset_period         TEXT NOT NULL DEFAULT 'monthly',   -- monthly | lifetime
    effective_from       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to         TIMESTAMPTZ                        -- NULL = current
);
CREATE UNIQUE INDEX idx_plans_current ON plans(client_id) WHERE effective_to IS NULL;

-- Periods (explicit rollover tracking)
CREATE TABLE periods (
    id              BIGSERIAL PRIMARY KEY,
    client_id       INT REFERENCES clients(id) ON DELETE CASCADE,
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    is_open         BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX idx_periods_open ON periods(client_id) WHERE is_open;
CREATE INDEX idx_periods_client_range ON periods(client_id, period_start DESC);

-- Jobs
CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       INT REFERENCES clients(id),
    period_id       BIGINT REFERENCES periods(id),
    endpoint        TEXT NOT NULL,               -- ocr | verify
    status          TEXT NOT NULL DEFAULT 'queued',  -- queued | processing | done | failed
    pages_submitted INT NOT NULL DEFAULT 1,
    attempts        INT NOT NULL DEFAULT 0,
    idempotency_key TEXT,
    body_hash       BYTEA,                       -- SHA-256 of uploaded bytes
    input_meta      JSONB,
    result          JSONB,
    error_msg       TEXT,
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    ip_address      INET
);
CREATE INDEX idx_jobs_client ON jobs(client_id, queued_at DESC);
CREATE INDEX idx_jobs_status ON jobs(status) WHERE status IN ('queued','processing');
CREATE INDEX idx_jobs_period ON jobs(period_id);
CREATE UNIQUE INDEX idx_jobs_idempotency ON jobs(client_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Audit log (admin actions)
CREATE TABLE audit_log (
    id           BIGSERIAL PRIMARY KEY,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_ip    INET,
    method       TEXT NOT NULL,
    path         TEXT NOT NULL,
    actor_note   TEXT,
    request_body JSONB,
    status_code  INT
);
CREATE INDEX idx_audit_time ON audit_log(timestamp DESC);

-- Usage log (ledger)
CREATE TABLE usage_log (
    id              BIGSERIAL PRIMARY KEY,
    client_id       INT REFERENCES clients(id),
    period_id       BIGINT REFERENCES periods(id),
    job_id          UUID REFERENCES jobs(id),
    pages           INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL,          -- success | error | rejected
    reject_reason   TEXT,
    response_ms     INT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_usage_client_time ON usage_log(client_id, timestamp DESC);
CREATE INDEX idx_usage_period ON usage_log(period_id);

-- Monthly billing summary
CREATE TABLE billing_summary (
    id                    SERIAL PRIMARY KEY,
    client_id             INT REFERENCES clients(id),
    period_id             BIGINT REFERENCES periods(id) UNIQUE,
    period_start          DATE NOT NULL,
    period_end            DATE NOT NULL,
    total_transactions    INT DEFAULT 0,
    total_pages           INT DEFAULT 0,
    rejected_transactions INT DEFAULT 0,
    error_transactions    INT DEFAULT 0,
    generated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

Run:
```bash
psql -U ocr_user -d ocr_billing -f migrations/versions/001_billing_schema.sql
# subsequent changes:
alembic revision -m "add X"
alembic upgrade head
```

#### 3.4 Period semantics

- `reset_period='monthly'` → period = calendar month UTC. Cron at `00:05 UTC on day 1` closes current period (`is_open=false`) and opens next.
- `reset_period='lifetime'` → one period row, `period_end = '9999-12-31'`, never rolls.
- Period creation is lazy: if a client has no open period on first request, API creates one before reservation.

#### 3.5 Python dependencies

Add to `requirements.txt`:
```
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.30
alembic==1.13.2
python-dotenv==1.0.1
rq==1.16.2
redis==5.0.4
argon2-cffi==23.1.0
prometheus-fastapi-instrumentator==6.1.0
python-magic==0.4.27
python-json-logger==2.0.7
pytest==8.2.0
pytest-asyncio==0.23.7
httpx==0.27.0
fakeredis==2.23.2
```

#### 3.6 Environment file

`/opt/paddleocr/.env` (mode 0600, owner claudeuser)
```env
DATABASE_URL=postgresql+asyncpg://ocr_user:STRONG_PASSWORD@localhost:5432/ocr_billing
REDIS_URL=redis://localhost:6379
ADMIN_TOKEN=<64-char hex>
API_KEY_PEPPER=<32-char hex>       # mixed into SHA-256 before storage
ENV=production
CORS_ALLOWED_ORIGINS=https://yourdomain.com,http://localhost:3000
```

Generate secrets:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"    # ADMIN_TOKEN
python3 -c "import secrets; print(secrets.token_hex(16))"    # API_KEY_PEPPER
```

---

### Phase 4 — Queue + Async OCR  _(Week 2, Days 3–5)_

**Goal:** POST /ocr returns job_id immediately. Workers process in background. Quota reserved on submit, released on failure.

#### 4.1 Install Redis

```bash
apt install redis-server
# /etc/redis/redis.conf:
#   appendonly yes
#   maxmemory-policy noeviction   (quota counters must not evict)
systemctl enable --now redis
```

#### 4.2 File structure

```
/opt/paddleocr/
├── app/
│   ├── main.py              ← rewrite: versioned routers, middlewares
│   ├── ocr.py               ← unchanged
│   ├── parser.py            ← unchanged
│   ├── worker.py            ← NEW: RQ job function
│   ├── upload.py            ← NEW: MIME sniff + image verify
│   ├── logging_mw.py        ← NEW: request_id + client_id injection
│   ├── errors.py            ← NEW: standard error envelope
│   └── billing/
│       ├── __init__.py
│       ├── db.py
│       ├── models.py
│       ├── auth.py
│       ├── quota.py
│       ├── periods.py
│       ├── idempotency.py   ← NEW: Redis-backed key store
│       ├── health.py        ← NEW: deep probe for /admin/v1/health
│       ├── retention.py     ← NEW: DELETE FROM jobs older than N
│       ├── admin.py
│       └── jobs.py
├── scripts/
│   ├── reap_stale_jobs.py
│   ├── reconcile_quota.py
│   ├── generate_billing_summary.py
│   ├── rollover_periods.py
│   ├── sweep_disk.py
│   ├── retention_cleanup.py
│   └── deploy.sh
├── logging.json
├── migrations/
├── tests/
│   ├── test_auth.py
│   ├── test_quota.py
│   ├── test_jobs.py
│   ├── test_idempotency.py
│   ├── test_upload.py
│   └── conftest.py
├── .env
└── requirements.txt
```

#### 4.3 Request flow

```
POST /api/v1/ocr
├── auth.py: sha256(API_KEY_PEPPER || header) → SELECT clients WHERE api_key_hash=?
│            → 401 if no row or !is_active
├── upload.validate_file(tmp):
│     - extension ∈ ALLOWED_EXT
│     - size ≤ 20MB (stream-checked before full read)
│     - MIME sniff via python-magic matches declared ext
│     - PIL.Image.verify() confirms decodable image
│     → 400 invalid_file on any failure (before quota touched)
├── idempotency.check(client_id, Idempotency-Key, body_hash):
│     IF key exists AND body_hash matches: return existing job (200)
│     IF key exists AND body_hash differs: return 409
│     ELSE: mark pending
├── periods.py: get_or_create_open_period(client_id)
├── quota.py:
│     new = INCR quota:{cid}:{pid}
│     IF new > plan.max_transactions:
│         DECR quota:{cid}:{pid}
│         idempotency.clear(key)
│         return 429
├── jobs.py: INSERT job (status=queued, period_id, idempotency_key)
├── idempotency.commit(key, job_id, body_hash)   ← TTL 24h
├── rq: enqueue('ocr-queue', worker.process_ocr, job_id, tmp_path,
│              retry=Retry(max=3, interval=[10,60,300]))
└── return 202
```

```
worker.process_ocr(job_id, tmp_path)
├── UPDATE jobs SET status=processing, started_at=now(), attempts=attempts+1
├── try:
│     lines = extract_lines(model, tmp_path)
│     fields = parse_ssm(lines)
│     UPDATE jobs SET status=done, result=..., completed_at=now()
│     INSERT usage_log (status=success)
│   except on final retry:
│     UPDATE jobs SET status=failed, error_msg=...
│     INSERT usage_log (status=error)
│     DECR quota:{cid}:{pid}          ← release reservation
└── finally: os.unlink(tmp_path)
```

```
GET /jobs/{job_id}
├── auth
├── SELECT * FROM jobs WHERE id=? AND client_id=?    ← client isolation
└── 404 if no row, else 200 with status + result
```

#### 4.4 API key lifecycle

Generation (once, at `POST /admin/v1/clients`):
```python
raw = "ocr_live_" + secrets.token_hex(16)
hash = hashlib.sha256((PEPPER + raw).encode()).digest()
prefix = raw[:12]      # "ocr_live_a1b"
```
- Return `raw` to caller **once**. Store `hash` + `prefix` only.
- Rekey endpoint invalidates old hash, issues new one.
- Lookup at auth: hash incoming header same way, lookup by `api_key_hash`.

#### 4.5 Retry policy

- Transient errors (I/O, model temporary fail): RQ retries 3× with backoff `[10s, 60s, 5m]`.
- Permanent errors (corrupt image, parse fail): no retry, mark failed immediately, release quota.
- Classifier in `worker.py` decides by exception type.

---

### Phase 5 — Admin API  _(Week 3, Days 1–3)_

**Goal:** Full client + billing management.

#### 5.1 Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/admin/v1/clients` | Create, returns `{client, api_key}` (plaintext once) |
| `GET` | `/admin/v1/clients` | List with plan + current usage |
| `GET` | `/admin/v1/clients/{id}` | Single client detail |
| `PATCH` | `/admin/v1/clients/{id}` | Update name, email, is_active |
| `DELETE` | `/admin/v1/clients/{id}` | Soft delete (is_active=false) |
| `PUT` | `/admin/v1/clients/{id}/plan` | Update plan (closes old, opens new effective row) |
| `POST` | `/admin/v1/clients/{id}/reset` | Manual period reset (closes current, opens new) |
| `POST` | `/admin/v1/clients/{id}/rekey` | Revoke + issue new key |
| `GET` | `/admin/v1/clients/{id}/usage` | Usage log `?from=&to=` |
| `GET` | `/admin/v1/clients/{id}/jobs` | Job history |
| `GET` | `/admin/v1/billing/report` | Summary all clients `?period=2025-04` |
| `GET` | `/admin/v1/billing/report/export` | CSV download |
| `GET` | `/admin/v1/health` | Services + DB + Redis + queue depth |
| `GET` | `/admin/v1/audit` | Recent admin actions `?from=&to=` |
| `DELETE` | `/admin/v1/clients/{id}/data` | GDPR-style purge: redact PII in `jobs.result`, keep usage_log for billing |

#### 5.2 Create client

```json
POST /admin/v1/clients
{
  "name": "Acme Corp",
  "email": "billing@acme.com",
  "max_transactions": 2000,
  "max_pages_per_txn": 1,
  "reset_period": "monthly"
}

→ 201
{
  "id": 1,
  "name": "Acme Corp",
  "email": "billing@acme.com",
  "api_key": "ocr_live_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",   ← shown ONCE
  "api_key_prefix": "ocr_live_a1b",
  "created_at": "2025-04-17T..."
}
```

Subsequent `GET /admin/v1/clients/{id}` returns `api_key_prefix` only. Lost keys → `/rekey`.

#### 5.3 Admin auth (defense in depth)

1. Nginx IP allowlist on `/admin/*` (Phase 2).
2. `X-Admin-Token` header validated in FastAPI dependency (constant-time compare).
3. All admin requests logged to `audit_log` (source IP, endpoint, timestamp, actor note).

#### 5.4 Cron schedule

```cron
# crontab -u claudeuser -e
0 0 1 * * /opt/paddleocr/venv/bin/python /opt/paddleocr/scripts/generate_billing_summary.py
5 0 1 * * /opt/paddleocr/venv/bin/python /opt/paddleocr/scripts/rollover_periods.py
0 4 * * * /opt/paddleocr/venv/bin/python /opt/paddleocr/scripts/retention_cleanup.py
```

> No DB backup in scope (Decision #9). If this changes later, add `pg_dump` cron.

#### 5.5 Data retention

`retention_cleanup.py` runs nightly:
- `DELETE FROM jobs WHERE completed_at < now() - interval '180 days'` — job bodies drop off.
- `DELETE FROM audit_log WHERE timestamp < now() - interval '365 days'`.
- `usage_log` kept forever (billing record).

Tune intervals via `.env` (`JOBS_RETENTION_DAYS=180`, `AUDIT_RETENTION_DAYS=365`).

---

### Phase 6 — Monitoring  _(Week 3, Days 4–5)_

#### 6.1 Stack

```bash
apt install docker.io docker-compose
```

`/opt/monitoring/docker-compose.yml`
```yaml
version: "3"
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports: ["127.0.0.1:9090:9090"]
    restart: always

  grafana:
    image: grafana/grafana
    ports: ["127.0.0.1:3000:3000"]
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=CHANGE_THIS
    volumes:
      - grafana_data:/var/lib/grafana
    restart: always

  redis_exporter:
    image: oliver006/redis_exporter
    command: ["--redis.addr=redis://host.docker.internal:6379"]
    ports: ["127.0.0.1:9121:9121"]
    restart: always

  postgres_exporter:
    image: prometheuscommunity/postgres-exporter
    environment:
      - DATA_SOURCE_NAME=postgresql://ocr_user:PASS@host.docker.internal:5432/ocr_billing?sslmode=disable
    ports: ["127.0.0.1:9187:9187"]
    restart: always

volumes:
  prometheus_data:
  grafana_data:
```

#### 6.2 FastAPI metrics

```python
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, include_in_schema=False)
```

Custom gauges:
- `ocr_queue_depth` (from Redis LLEN)
- `ocr_worker_jobs_in_flight`
- `ocr_quota_usage_ratio_top10{client_id}` — only **top 10 clients by usage**; rest aggregated as `client_id="other"`.
- `ocr_quota_near_limit` (count of clients ≥90% used — single gauge, no per-client label)

> Cardinality discipline: never label metrics with unbounded-growth IDs (full `client_id`, `job_id`). Top-N + "other" pattern keeps Prometheus memory flat.

#### 6.3 Alerts

| Metric | Threshold | Alert |
|---|---|---|
| `up{service="ocr-api"}` | 0 for 2m | page |
| `http_request_duration_seconds{quantile="0.95"}` | >30s | warn |
| `ocr_queue_depth` | >100 for 5m | warn — scale workers |
| Job failure rate | >5% over 15m | warn |
| Disk free | <20% | page |
| RAM used | >85% | warn |
| Quota reservation ≥90% | per client | log (email in later phase) |
| Redis down | any | page (quota accounting halts) |
| Postgres down | any | page |

#### 6.4 Nginx proxy for Grafana

```nginx
location /grafana/ {
    allow 203.0.113.0/24;   # office/VPN
    deny all;
    proxy_pass http://127.0.0.1:3000/;
}
```

---

### Phase 7 — SSL + Domain  _(When domain ready)_

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d yourdomain.com -d ocr.yourdomain.com
ufw allow 443/tcp
```

- Redirect 80→443 in nginx.
- Update `CORS_ALLOWED_ORIGINS` env.
- Certbot auto-renews via systemd timer.

---

### Phase 9 — Template Editor  _(MANDATORY, ~3–4 weeks)_

**Goal:** admins define document extraction visually. Click fields on scanned image → assign label → save as template. New formats added without code.

Replaces per-format hardcoded parsers (Option A). SSM parser stays as built-in default/fallback.

**Status: MANDATORY for v1 launch.** Not deferrable. Core product value proposition — without template editor, product = hardcoded SSM-only tool. With it = generic document OCR SaaS. Phase 9 ships as part of v1; paying clients require template flexibility from day 1.

#### 9.1 Bbox-aware OCR

Current `app/ocr.py` drops bounding boxes. Extend:

```python
# app/ocr.py
def extract_lines(ocr, image_path: str) -> list[dict]:
    result = ocr.predict(image_path)
    lines = []
    for page in result:
        texts  = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        polys  = page.get("rec_polys", [])
        for text, score, poly in zip(texts, scores, polys):
            if text.strip():
                lines.append({
                    "text": text.strip(),
                    "confidence": round(score, 3),
                    "bbox": poly_to_xywh(poly),   # [x, y, w, h]
                })
    return lines
```

Existing SSM parser keeps working (ignores new `bbox` key).

#### 9.2 Label Studio (self-hosted annotation UI)

Pick **Label Studio** (open source, free, OCR-aware) over custom build. ~3–5 days integration vs 2–3 weeks custom.

```yaml
# add to /opt/monitoring/docker-compose.yml  (or separate compose)
label_studio:
  image: heartexlabs/label-studio:latest
  ports: ["127.0.0.1:8080:8080"]
  volumes:
    - label_studio_data:/label-studio/data
  environment:
    - LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK=true
  restart: always
```

Nginx location (admin IP allow):
```nginx
location /labelstudio/ {
    allow 203.0.113.0/24;
    deny all;
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

Workflow:
1. Admin uploads sample image to Label Studio project.
2. Label Studio runs (via webhook or manual) — admin draws boxes + labels.
3. Export JSON → import to our `doc_templates` via sync endpoint.

#### 9.3 Schema additions

```sql
CREATE TABLE doc_templates (
    id               SERIAL PRIMARY KEY,
    client_id        INT REFERENCES clients(id),        -- NULL = global
    name             TEXT NOT NULL,                     -- "Malaysian Invoice v1"
    doc_type_code    TEXT NOT NULL,                    -- stable slug for API
    sample_image_path TEXT,                             -- /opt/paddleocr/templates/{id}/sample.jpg
    image_width      INT NOT NULL,
    image_height     INT NOT NULL,
    is_active        BOOLEAN DEFAULT TRUE,
    created_by       TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_templates_code ON doc_templates(doc_type_code) WHERE is_active;

CREATE TABLE template_fields (
    id           SERIAL PRIMARY KEY,
    template_id  INT REFERENCES doc_templates(id) ON DELETE CASCADE,
    field_name   TEXT NOT NULL,               -- "invoice_no"
    strategy     TEXT NOT NULL,               -- anchor | zone | regex
    config       JSONB NOT NULL,
    post_process TEXT,                        -- date | number | uppercase | trim
    required     BOOLEAN DEFAULT FALSE,
    display_order INT DEFAULT 0
);
CREATE INDEX idx_template_fields_template ON template_fields(template_id);

-- Per-client whitelist of usable templates
CREATE TABLE client_templates (
    client_id    INT REFERENCES clients(id) ON DELETE CASCADE,
    template_id  INT REFERENCES doc_templates(id) ON DELETE CASCADE,
    PRIMARY KEY (client_id, template_id)
);
```

Config payload examples:

```json
// anchor strategy
{ "labels": ["INVOICE NO","INV NO","NO. INVOIS"],
  "direction": "right|below|same_line_colon",
  "max_distance_px": 150 }

// zone strategy
{ "x": 120, "y": 340, "w": 200, "h": 50,
  "merge": true }         // merge multiple text lines in zone

// regex strategy
{ "pattern": "TOTAL\\s*:?\\s*(RM\\s*[\\d,.]+)",
  "group": 1 }
```

#### 9.4 Extraction engine

New module `app/templates/extractor.py`:

```python
def extract_with_template(lines: list[Line], template: Template) -> dict:
    out = {}
    for field in template.fields:
        try:
            if field.strategy == "anchor":
                raw = find_by_anchor(lines, field.config)
            elif field.strategy == "zone":
                raw = find_in_zone(lines, field.config,
                                   img_w=template.image_width,
                                   img_h=template.image_height)
            elif field.strategy == "regex":
                raw = find_by_regex(lines, field.config)
            out[field.name] = apply_post_process(raw, field.post_process)
        except Exception as e:
            out[field.name] = None
            if field.required:
                out.setdefault("_errors", []).append({field.name: str(e)})
    return out
```

Strategy implementations in `app/templates/strategies/{anchor,zone,regex}.py`.

#### 9.5 Admin API additions

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/admin/v1/templates` | Create template (multipart: sample image + JSON definition) |
| `GET` | `/admin/v1/templates` | List |
| `GET` | `/admin/v1/templates/{id}` | Detail incl. fields |
| `PUT` | `/admin/v1/templates/{id}` | Update (new version — old kept for audit) |
| `DELETE` | `/admin/v1/templates/{id}` | Soft delete (`is_active=false`) |
| `POST` | `/admin/v1/templates/{id}/test` | Upload test doc, return extraction preview (no quota charge) |
| `POST` | `/admin/v1/templates/{id}/sync-label-studio` | Pull annotations from Label Studio project, overwrite fields |
| `POST` | `/admin/v1/clients/{id}/templates` | Whitelist templates for client |

#### 9.6 Client API change

Add optional param to submit:

```
POST /api/v1/ocr
  file: ...
  doc_type: <template.doc_type_code>       ← resolves to template
```

Flow:
1. Auth + upload validate + quota reserve as before.
2. If `doc_type` given:
   a. Resolve template by `doc_type_code`.
   b. Verify client is whitelisted for that template (via `client_templates`).
   c. Worker runs OCR → `extract_with_template(lines, template)`.
3. If `doc_type` omitted: fallback to SSM parser (backward compat).

Response `fields` structure same as today — just populated by template engine.

#### 9.7 Template versioning

- `PUT /admin/v1/templates/{id}` doesn't mutate. It creates a new row with incremented `version` column (add to schema), marks old inactive.
- Jobs record `template_id + template_version_at_submit` so re-runs are reproducible.

#### 9.8 Open questions (answer before building Phase 9)

- Template assignment: client-specified `doc_type` (v1) or auto-detect from image content (ML classifier, later)?
- Pricing: flat rate for template extraction, or premium over built-in SSM parser?
- Who creates templates — ops staff only, or can customers bring their own?
- Multi-page docs: one template per page, or template with page-index per field?
- Failure mode: template can't find required field → job fails (bill customer?) or returns partial result?

---

## Deployment

No CI/CD in v1. Deploys are manual and scripted.

`scripts/deploy.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/paddleocr

echo "[1/6] Pulling latest code..."
git fetch origin
git checkout main
git pull --ff-only

echo "[2/6] Installing deps..."
venv/bin/pip install -r requirements.txt --upgrade

echo "[3/6] Running migrations..."
venv/bin/alembic upgrade head

echo "[4/6] Restarting API..."
sudo systemctl restart ocr-api

echo "[5/6] Rolling workers (one at a time, graceful)..."
for w in 1 2; do
  sudo systemctl restart ocr-worker@${w}
  sleep 10
done

echo "[6/6] Smoke test..."
curl -fsS http://127.0.0.1:8002/api/v1/health || { echo "Health FAIL"; exit 1; }

echo "Deploy OK. $(date -u +%FT%TZ) $(git rev-parse --short HEAD)" >> /var/log/ocr/deploys.log
```

Rollback: `git checkout <prev-sha>` then re-run `deploy.sh`. Schema-forward rollbacks require a separate `alembic downgrade` revision — only add when actually needed.

---

## Runbook

One-page operator guide. Keep at `/opt/paddleocr/RUNBOOK.md`, in sync with prod.

### API down
1. `systemctl status ocr-api` → `journalctl -u ocr-api -n 100 -o cat`.
2. Common: DB unreachable → `systemctl status postgresql`. Redis unreachable → `systemctl status redis`.
3. OOM → `dmesg -T | grep -i kill`. Reduce `--workers` or worker count, or upgrade VPS.

### Queue backing up
1. `redis-cli LLEN rq:queue:ocr-queue`.
2. Worker alive? `systemctl status ocr-worker@1 ocr-worker@2`.
3. If workers stuck: `systemctl restart ocr-worker@*` (graceful — finishes current job, up to 120s).
4. Sustained backlog → enable `ocr-worker@3`, monitor RAM.

### Quota counter drift
1. Suspect if `/admin/v1/health` shows reconcile errors or client reports wrong usage.
2. Run `venv/bin/python scripts/reconcile_quota.py --client-id <ID>` — rebuilds one client.
3. `--all` to rebuild everything (safe, idempotent).

### Stuck "processing" jobs
1. Normally auto-reaped every 60s.
2. Check reaper: `systemctl list-timers | grep ocr-reaper`.
3. Manual: `venv/bin/python scripts/reap_stale_jobs.py --force`.

### Disk full
1. `df -h`. Culprits (order of likelihood): `/var/lib/postgresql`, `/opt/paddleocr/.paddleocr_cache`, `journal` logs, `/tmp`.
2. Trim journal: `journalctl --vacuum-time=7d`.
3. Old jobs: run `scripts/retention_cleanup.py` early.
4. Last resort: upgrade VPS disk.

### Key suspected leaked
1. `POST /admin/v1/clients/{id}/rekey` — invalidates old, returns new.
2. Communicate new key to client out-of-band.
3. Review `usage_log` for abnormal spikes: `SELECT date_trunc('hour', timestamp), count(*) FROM usage_log WHERE client_id=? GROUP BY 1 ORDER BY 1 DESC LIMIT 48;`.

### Admin token rotation
1. Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"`.
2. Update `/opt/paddleocr/.env`.
3. `systemctl restart ocr-api`.
4. Notify admin consumers.

### Rollback a bad deploy
1. `git log --oneline -10` in `/opt/paddleocr`.
2. `git checkout <last-good-sha>`.
3. `bash scripts/deploy.sh`.
4. If schema already advanced: add a new alembic revision reverting the change — do NOT `alembic downgrade` on a running system without testing.

---

## Testing Strategy

Required before Phase 5 kickoff.

### Unit
- `auth.py` — hash round-trip, pepper applied, constant-time compare.
- `quota.py` — reserve, release, over-limit rejection, period rollover.
- `periods.py` — monthly boundary math (UTC), lifetime never rolls.
- `jobs.py` — client isolation (404 across clients).

### Integration (pytest + httpx + test DB + fakeredis)
- Submit → poll → done happy path.
- Submit with exhausted quota → 429, no row in `jobs`, counter unchanged.
- Worker failure → `status=failed`, quota released, retry count recorded.
- Burst submit (50 parallel) when 5 slots left → exactly 5 accepted, rest 429.
- Stale reaper releases quota after worker kill -9 simulation.
- Admin endpoint returns 403 without token, 200 with.
- **Idempotency replay** — same key + same body → same job_id, single quota charge.
- **Idempotency conflict** — same key + different body → 409.
- **Upload validation** — `.txt` renamed `.jpg` rejected by MIME sniff.
- **Upload validation** — 0-byte file + oversized file + corrupted JPEG rejected before quota.
- **ETag 304** — poll after completion with `If-None-Match` → 304 no body.
- **Deep health** — simulated DB-down returns 503 on `/admin/v1/health`.

### Load (before go-live)
- `locust` or `k6`, 1 client, 60 req/min sustained 10 min.
- Measure p95 latency, worker queue depth, RAM growth.
- Target: p95 < 10s with 2 workers on current VPS.

---

## Secret Rotation

| Secret | Rotation | Procedure |
|---|---|---|
| Client API key | On request / on suspected leak | `POST /admin/v1/clients/{id}/rekey` |
| `ADMIN_TOKEN` | Every 90 days | Generate, update `.env`, `systemctl restart ocr-api`. Coordinate with admin consumers. |
| `API_KEY_PEPPER` | Only on breach (invalidates ALL keys) | Generate, re-hash all keys (requires forced client rekey — coordinated migration). Document as last-resort. |
| DB password | Every 180 days | `ALTER USER`, update `.env`, restart services. |
| Grafana admin | Every 90 days | Set via env, restart container. |

---

## File Changes Summary

| File | Change |
|---|---|
| `app/main.py` | Full rewrite — versioned routers `/api/v1/*` + `/admin/v1/*`, middlewares (request_id, CORS, error envelope), docs gated by `ENV` |
| `app/worker.py` | NEW — RQ job, retry classifier, graceful SIGINT |
| `app/upload.py` | NEW — MIME sniff + PIL verify + size guard |
| `app/logging_mw.py` | NEW — request_id + client_id log context |
| `app/errors.py` | NEW — standard error envelope + code enum |
| `app/billing/db.py` | NEW |
| `app/billing/models.py` | NEW |
| `app/billing/auth.py` | NEW — SHA-256 + pepper lookup, constant-time compare |
| `app/billing/quota.py` | NEW — Redis reserve/release |
| `app/billing/periods.py` | NEW — open/close/rollover |
| `app/billing/idempotency.py` | NEW — Redis key store, body hash check |
| `app/billing/health.py` | NEW — deep probe for `/admin/v1/health` |
| `app/billing/retention.py` | NEW |
| `app/billing/jobs.py` | NEW |
| `app/billing/admin.py` | NEW — admin router, audit_log middleware |
| `app/ocr.py` | Unchanged |
| `app/parser.py` | Unchanged |
| `client.py` | Update default URL + `/api/v1/` prefix |
| `logging.json` | NEW — uvicorn JSON log config |
| `scripts/reap_stale_jobs.py` | NEW |
| `scripts/reconcile_quota.py` | NEW |
| `scripts/rollover_periods.py` | NEW |
| `scripts/generate_billing_summary.py` | NEW |
| `scripts/sweep_disk.py` | NEW |
| `scripts/retention_cleanup.py` | NEW |
| `scripts/deploy.sh` | NEW |
| `migrations/versions/001_billing_schema.sql` | NEW — incl. audit_log, idempotency indexes |
| `alembic.ini`, `migrations/env.py` | NEW |
| `tests/**` | NEW — unit + integration (incl. idempotency, upload, ETag) |
| `RUNBOOK.md` | NEW |
| `requirements.txt` | Additions listed §3.5 + `python-magic`, `python-json-logger` |
| `.env` | NEW |
| **Phase 9 additions** | |
| `app/ocr.py` | Update — return `bbox` per line |
| `app/templates/__init__.py` | NEW |
| `app/templates/extractor.py` | NEW — strategy dispatcher |
| `app/templates/strategies/anchor.py` | NEW |
| `app/templates/strategies/zone.py` | NEW |
| `app/templates/strategies/regex.py` | NEW |
| `app/templates/post_process.py` | NEW — date, number, trim, etc. |
| `app/templates/label_studio_sync.py` | NEW — import Label Studio JSON |
| `app/billing/admin.py` | Update — template CRUD + test endpoint |
| `migrations/versions/002_templates.sql` | NEW — doc_templates, template_fields, client_templates |
| `scripts/import_label_studio.py` | NEW |
| `tests/test_templates.py` | NEW — anchor, zone, regex strategies |

---

## Full Deployment Order

```
Week 1
  Day 1–2:  Phase 1 — systemd (stability, reaper, reconcile timer)
  Day 3–4:  Phase 2 — Nginx (entry point, UI basic-auth, admin IP allowlist)
  Day 5:    Reboot-and-recover drill

Week 2
  Day 1–2:  Phase 3 — PostgreSQL + alembic + schema
  Day 3–5:  Phase 4 — Redis + async endpoints + reserve/commit quota
            + unit tests

Week 3
  Day 1–3:  Phase 5 — Admin API + billing cron + backup script
            + integration tests
  Day 4–5:  Phase 6 — Prometheus + Grafana + alerts
            + load test

Go-live gate
  - All checklist items ticked
  - Burst-quota race test passes
  - Reboot-recovery drill passed

Week 4–6 (MANDATORY before go-live)
  Phase 9 — Template Editor
  Week 4:  bbox-aware OCR + schema + extraction engine + tests
  Week 5:  Label Studio self-host + nginx + sync endpoint
  Week 6:  admin UI wiring, client API doc_type param, per-client whitelist
           migrate SSM parser to template (dogfood), ship to clients

Post-launch
  When domain ready:  Phase 7 — SSL
```

---

## Production Checklist

### Security
- [ ] Firewall: only 22, 80 (443 later) open externally
- [ ] All backend ports bind `127.0.0.1`
- [ ] API key on all `/api/v1/ocr`, `/verify`, `/jobs/*`, `/usage/me`
- [ ] API keys stored as SHA-256(pepper || key), never plaintext
- [ ] Admin token in `.env` (mode 0600), not in code, not in git
- [ ] Admin routes: nginx IP allowlist + token header + audit_log table populated
- [ ] Streamlit UI behind nginx basic-auth
- [ ] `/docs`, `/redoc`, `/openapi.json` IP-restricted OR disabled via `ENV=production`
- [ ] fail2ban active on 401 bursts
- [ ] systemd sandboxing set on all services (`NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`)
- [ ] `.env` in `.gitignore`
- [ ] CORS restricted to known origins (no `*` in prod)
- [ ] Nginx rate limiting active (per-key + per-IP)
- [ ] Secret rotation documented + calendared
- [ ] Upload validation: MIME sniff + PIL.verify before quota reserve

### Reliability
- [ ] All services under systemd `Restart=always`
- [ ] Services enabled on boot
- [ ] Graceful worker shutdown (`KillSignal=SIGINT`, `TimeoutStopSec=120`) verified
- [ ] PaddleOCR model pre-cache populated before worker start
- [ ] Stale-job reaper timer active
- [ ] Quota reconciliation timer active
- [ ] Period rollover cron active
- [ ] Disk sweep timer active
- [ ] Retention cleanup cron active
- [ ] Log rotation active + journald JSON format verified
- [ ] Redis `appendonly yes`, `maxmemory-policy noeviction`
- [ ] Reboot recovery drill passed

### Billing / Quota
- [ ] Schema deployed via alembic
- [ ] Every job logged to `jobs` + `usage_log`
- [ ] Reserve-on-submit race test passes (parallel burst)
- [ ] Release-on-failure verified
- [ ] Stale reaper releases quota verified
- [ ] Idempotency replay returns same job_id, no double charge
- [ ] Monthly billing summary cron active
- [ ] Period rollover boundary test passed

### API contract
- [ ] All public routes under `/api/v1/` and `/admin/v1/`
- [ ] Standard error envelope on every 4xx/5xx
- [ ] `X-Request-Id` emitted + echoed + logged
- [ ] ETag / 304 on completed jobs
- [ ] Public `/api/v1/health` shallow, `/admin/v1/health` deep

### Performance
- [ ] PaddleOCR model pre-loaded at worker startup
- [ ] Temp files cleaned up (finally block + periodic sweep)
- [ ] Redis queue depth monitored
- [ ] Worker count matches load target

### Monitoring
- [ ] Prometheus scraping FastAPI, Redis, Postgres
- [ ] Grafana dashboards live
- [ ] Alerts wired (page vs warn separated)
- [ ] Metric cardinality capped (top-N + "other" on client_id labels)
- [ ] `/admin/v1/health` returns full stack status

### Ops
- [ ] `scripts/deploy.sh` tested on non-critical change
- [ ] `RUNBOOK.md` present at `/opt/paddleocr/RUNBOOK.md`
- [ ] Rollback procedure walked through once

### Phase 9 — Templates (when rolled out)
- [ ] OCR returns bbox on every line
- [ ] Label Studio up at `/labelstudio/`, IP-restricted
- [ ] `doc_templates` + `template_fields` + `client_templates` migrated
- [ ] Anchor strategy tests green (label match, direction, distance cap)
- [ ] Zone strategy tests green (scale tolerance, merge option)
- [ ] Regex strategy tests green
- [ ] Template test endpoint doesn't charge quota
- [ ] Per-client template whitelist enforced (client X can't use client Y's template)
- [ ] Template versioning: PUT creates new version, jobs record version used
- [ ] Fallback verified: no `doc_type` param → SSM parser still runs

### Testing
- [ ] Unit tests pass in CI
- [ ] Integration tests pass against ephemeral DB + fakeredis
- [ ] Load test run before go-live, results recorded

---

## Cost Estimate

| Item | Cost |
|---|---|
| Contabo VPS (current) | ~€15–30/mo |
| Domain + SSL (Let's Encrypt) | ~€10/yr (when ready) |
| Prometheus + Grafana | Self-hosted, no extra cost |
| PostgreSQL / Redis / Nginx | Self-hosted, no extra cost |
| **Total** | **~€15–30/mo** |

Upgrade hardware when: sustained >50 req/min OR p95 latency >10s OR RAM >85% OR queue depth >100 for 5 min despite max workers on node.
