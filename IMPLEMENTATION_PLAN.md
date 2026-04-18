# OCR API — Implementation Plan (Execution Checklist)

Companion to `PRODUCTION_PLAN.md` (design). This doc = ordered, checkable tasks. One pass top-to-bottom. Check boxes as you go.

Assumptions:
- VPS: Ubuntu 24.04.4 LTS (`173.212.247.3`), root SSH via key works.
- New code lives at `/opt/ocr-saas` owned by `claudeuser` (legacy `/opt/paddleocr` stays untouched until cutover).
- Local dev on Windows; deploy to Linux VPS.
- **Read `PRODUCTION_PLAN.md` §Likely Blockers before Phase 1.** All 12 items must be mitigated or accepted.

---

## Phase 0 — Pre-flight  _(½ day)_

- [ ] SSH key works: `ssh root@173.212.247.3`
- [ ] Create non-root user: `adduser claudeuser && usermod -aG sudo claudeuser`
- [ ] Disable root SSH + password auth in `/etc/ssh/sshd_config`, reload sshd
- [ ] Install base: `apt update && apt install -y git curl build-essential python3.11 python3.11-venv python3-pip`
- [ ] Create dirs: `mkdir -p /opt/paddleocr /var/log/ocr && chown -R claudeuser:claudeuser /opt/paddleocr /var/log/ocr`
- [ ] Clone repo: `sudo -u claudeuser git clone <repo-url> /opt/paddleocr`
- [ ] Create venv: `sudo -u claudeuser python3.11 -m venv /opt/paddleocr/venv`
- [ ] `pip install -r requirements.txt` (existing deps, pre-billing)
- [ ] Smoke: manual uvicorn run reaches `/health` on 127.0.0.1:8002
- [ ] Note current git SHA for rollback: `git rev-parse HEAD > /opt/paddleocr/.deployed-sha`

**Gate:** app runs manually under claudeuser. Don't proceed otherwise.

---

## Phase 1 — Stability  _(Week 1, Days 1–2)_

Ref: `PRODUCTION_PLAN.md` §Phase 1.

### 1.1 systemd units

- [ ] Write `/etc/systemd/system/ocr-api.service` (per §1.1 — include sandboxing)
- [ ] Write `/etc/systemd/system/ocr-worker@.service` (per §1.2 — `PADDLEOCR_HOME`, `SIGINT`, sandboxing)
- [ ] Write `/etc/systemd/system/ocr-ui.service` (per §1.3)
- [ ] `systemctl daemon-reload`
- [ ] Start only `ocr-api` first: `systemctl start ocr-api && journalctl -u ocr-api -f` — verify startup clean
- [ ] Start `ocr-ui`, hit `http://127.0.0.1:8502` via `curl -I`

### 1.2 PaddleOCR model pre-cache

- [ ] `mkdir -p /opt/paddleocr/.paddleocr_cache && chown claudeuser:claudeuser $_`
- [ ] Run cache populate command (per §1.6). First run takes 1–3 min (downloads).
- [ ] Verify cache dir has files: `ls -la /opt/paddleocr/.paddleocr_cache`
- [ ] `systemctl start ocr-worker@1` — tail journal, confirm "model ready" log
- [ ] Enable worker@2, verify both in queue: `redis-cli` not yet installed — defer multi-worker verify to Phase 4

### 1.3 Reaper + reconcile timers (defer bodies — scripts not written yet)

- [ ] Stub `scripts/reap_stale_jobs.py` with `print("reaper noop")` and exit 0
- [ ] Stub `scripts/reconcile_quota.py` likewise
- [ ] Stub `scripts/sweep_disk.py` likewise
- [ ] Write `.service` + `.timer` files per §1.4/1.5/1.8
- [ ] `systemctl enable --now ocr-reaper.timer ocr-reconcile.timer ocr-disksweep.timer`
- [ ] `systemctl list-timers | grep ocr` — all listed, next trigger time sane

### 1.4 Structured logging

- [ ] Write `/opt/paddleocr/logging.json` (per §1.7)
- [ ] `pip install python-json-logger`
- [ ] Restart `ocr-api`, verify JSON lines: `journalctl -u ocr-api -n 20 -o cat | jq .`

### 1.5 Log rotation

- [ ] Write `/etc/logrotate.d/ocr` (per §1.10)
- [ ] Test: `logrotate -d /etc/logrotate.d/ocr` (dry-run, no errors)

### 1.6 Reboot drill

- [ ] `reboot`
- [ ] SSH back in
- [ ] `systemctl status ocr-api ocr-worker@1 ocr-worker@2 ocr-ui` — all active
- [ ] `curl http://127.0.0.1:8002/health` → 200

**Gate:** services recover from reboot unattended.

---

## Phase 2 — Nginx  _(Week 1, Days 3–4)_

Ref: §Phase 2.

### 2.1 Firewall

- [ ] `apt install -y ufw`
- [ ] Apply rules per §2.1 (allow 22, 80; deny backend ports)
- [ ] **Before enabling:** confirm SSH still works from another session
- [ ] `ufw enable`
- [ ] `ss -tlnp | grep -E '8002|8502'` — confirm `127.0.0.1:` only

### 2.2 Nginx

- [ ] `apt install -y nginx apache2-utils`
- [ ] `htpasswd -c /etc/nginx/.htpasswd-ocr admin` (set strong password)
- [ ] Write `/etc/nginx/sites-available/ocr` per §2.2 (versioned locations, docs gate)
- [ ] **Replace** `203.0.113.0/24` with real office/VPN CIDR
- [ ] `rm /etc/nginx/sites-enabled/default`
- [ ] `ln -s /etc/nginx/sites-available/ocr /etc/nginx/sites-enabled/`
- [ ] `nginx -t && systemctl reload nginx`
- [ ] Curl test from external host:
  - [ ] `/` → 401 (basic-auth prompt)
  - [ ] `/api/v1/health` → 404 (routes not built yet — expected)
  - [ ] `/admin/v1/anything` from non-allowed IP → 403
  - [ ] `/docs` from non-allowed IP → 403

### 2.3 fail2ban

- [ ] `apt install -y fail2ban`
- [ ] Write filter + jail per §2.3
- [ ] `systemctl restart fail2ban`
- [ ] `fail2ban-client status ocr-api-401` — jail loaded
- [ ] Manual trigger: 25× `curl -H "X-API-Key: wrong" /api/v1/health` from spare IP, verify ban after threshold

**Gate:** public internet sees only `/`, `/api/v1/`, and admin from allowlist. Backend ports closed.

---

## Phase 3 — Database  _(Week 2, Days 1–2)_

Ref: §Phase 3.

### 3.1 Install

- [ ] `apt install -y postgresql postgresql-contrib libmagic1`
- [ ] `sudo -u postgres psql` → create user + DB per §3.1
- [ ] Test: `psql -U ocr_user -d ocr_billing -h localhost -W` connects

### 3.2 Alembic

- [ ] Add to `requirements.txt`: all entries from §3.5
- [ ] `pip install -r requirements.txt`
- [ ] `alembic init migrations`
- [ ] Edit `alembic.ini`: `sqlalchemy.url` reads from env
- [ ] Edit `migrations/env.py` to import models (even if empty stubs)

### 3.3 Initial schema

- [ ] Save schema DDL to `migrations/versions/001_billing_schema.sql` (copy from §3.3)
- [ ] Apply: `psql -U ocr_user -d ocr_billing -f migrations/versions/001_billing_schema.sql`
- [ ] Verify: `\dt` in psql shows all 7 tables (clients, plans, periods, jobs, usage_log, billing_summary, audit_log)
- [ ] Verify indexes: `\di`

### 3.4 .env

- [ ] Generate secrets (per §3.6): ADMIN_TOKEN, API_KEY_PEPPER
- [ ] Write `/opt/paddleocr/.env` with all keys
- [ ] `chmod 600 /opt/paddleocr/.env && chown claudeuser:claudeuser $_`
- [ ] Add `.env` to `.gitignore`, verify not committed

**Gate:** DB reachable, schema applied, secrets in `.env` (not git).

---

## Phase 4 — Queue + Async OCR  _(Week 2, Days 3–5)_

Ref: §Phase 4.

### 4.1 Redis

- [ ] `apt install -y redis-server`
- [ ] Edit `/etc/redis/redis.conf`: `appendonly yes`, `maxmemory-policy noeviction`
- [ ] `systemctl restart redis && systemctl enable redis`
- [ ] `redis-cli ping` → PONG

### 4.2 Billing modules (code)

Each module: write → unit test → commit. Order matters (deps).

- [ ] `app/billing/db.py` — async SQLAlchemy session factory
- [ ] `app/billing/models.py` — SQLAlchemy ORM for all 7 tables
- [ ] `app/billing/auth.py` — hash(pepper+key), lookup client, constant-time compare
  - [ ] `tests/test_auth.py` passes
- [ ] `app/billing/periods.py` — `get_or_create_open_period`, monthly/lifetime logic
  - [ ] `tests/test_periods.py` passes (UTC boundary cases)
- [ ] `app/billing/quota.py` — Redis INCR/DECR, reserve/release
  - [ ] `tests/test_quota.py` — burst-race test (50 parallel, 5 slots left → 5 ok)
- [ ] `app/billing/idempotency.py` — Redis key store, 24h TTL
  - [ ] `tests/test_idempotency.py` — replay + conflict
- [ ] `app/billing/jobs.py` — INSERT/SELECT with client isolation
  - [ ] `tests/test_jobs.py` — cross-client 404
- [ ] `app/upload.py` — MIME sniff + PIL verify
  - [ ] `tests/test_upload.py` — bad MIME, corrupt jpeg, 0-byte
- [ ] `app/errors.py` — standard envelope + error codes enum
- [ ] `app/logging_mw.py` — request_id middleware
- [ ] `app/billing/health.py` — deep probe (DB, Redis, queue, workers)
- [ ] `app/worker.py` — RQ job function, retry classifier, graceful handling

### 4.3 Rewrite main.py

- [ ] Branch off new git branch `phase-4-async`
- [ ] Mount routers at `/api/v1/*`
- [ ] Add middlewares: CORS (tight), request_id, error envelope
- [ ] Gate `/docs` by `ENV` var
- [ ] Implement POST `/api/v1/ocr` with full flow per §4.3 (auth → upload-validate → idempotency → period → quota reserve → jobs.insert → idempotency.commit → enqueue)
- [ ] Implement POST `/api/v1/verify` (same pattern)
- [ ] Implement GET `/api/v1/jobs/{id}` with ETag + `?fields=status|full`
- [ ] Implement GET `/api/v1/usage/me`
- [ ] Implement GET `/api/v1/health` (shallow) and `/admin/v1/health` (deep)
- [ ] Response headers: `X-Transactions-*`, `X-Period-Reset`, `X-Request-Id`

### 4.4 Real reaper + reconcile scripts

- [ ] Replace stub `scripts/reap_stale_jobs.py` with real logic (fail + DECR)
- [ ] Replace stub `scripts/reconcile_quota.py` with rebuild-from-ledger logic
- [ ] Replace stub `scripts/sweep_disk.py` with real sweeper
- [ ] Manual test each: `sudo -u claudeuser venv/bin/python scripts/reap_stale_jobs.py`

### 4.5 Integration test

- [ ] `pytest tests/ -v` all green
- [ ] Create test client via SQL insert (not admin API yet)
- [ ] End-to-end curl:
  - [ ] Submit → 202 + job_id
  - [ ] Poll → status transitions queued → processing → done
  - [ ] Result structure matches spec
  - [ ] Second submit with same Idempotency-Key → same job_id, 200
  - [ ] Exhaust quota → 429 with detail

### 4.6 Deploy

- [ ] Merge branch `phase-4-async` to `main`
- [ ] `systemctl restart ocr-api ocr-worker@1 ocr-worker@2`
- [ ] Verify JSON logs showing request_id

**Gate:** full async OCR pipeline working end-to-end with one hand-crafted test client.

---

## Phase 5 — Admin API  _(Week 3, Days 1–3)_

Ref: §Phase 5.

### 5.1 Admin router

- [ ] `app/billing/admin.py` — router + audit_log middleware
- [ ] Implement each endpoint from §5.1 table
- [ ] `X-Admin-Token` dependency with constant-time compare
- [ ] Every admin call writes `audit_log` row
- [ ] Mount at `/admin/v1/*`

### 5.2 Client lifecycle

- [ ] Test POST `/admin/v1/clients` — returns api_key once
- [ ] Verify `api_key_prefix` stored, full key only in response
- [ ] Test `/rekey` invalidates old, issues new
- [ ] Test `/plan` PUT closes old, opens new effective row (both visible in history)
- [ ] Test soft delete sets `is_active=false`, requests with that key → 403

### 5.3 Reporting + retention

- [ ] `scripts/generate_billing_summary.py` — cron runs 1st of month
- [ ] `scripts/rollover_periods.py` — cron 5min after billing summary
- [ ] `scripts/retention_cleanup.py` — nightly
- [ ] Install user crontab entries (per §5.4)
- [ ] Manual test each script on empty DB — no errors

### 5.4 Admin access check

- [ ] From allowed IP + valid token → 200
- [ ] From allowed IP + wrong token → 403, audit_log records attempt
- [ ] From disallowed IP → nginx 403 (request never reaches app)

### 5.5 Integration tests

- [ ] Full admin test suite green
- [ ] Burst-quota race integration test green
- [ ] Stale reaper test green (kill -9 worker mid-job, verify reaper fails + DECRs)

**Gate:** onboard a real client via admin API, they run 10 OCRs successfully, quota deducts correctly.

---

## Phase 6 — Monitoring  _(Week 3, Days 4–5)_

Ref: §Phase 6. Skippable if time-constrained — can add later.

- [ ] `apt install -y docker.io docker-compose`
- [ ] `mkdir -p /opt/monitoring && cd $_`
- [ ] Write `docker-compose.yml` per §6.1
- [ ] Write `prometheus.yml` with scrape targets: `ocr-api:8002/metrics`, redis_exporter, postgres_exporter
- [ ] `docker-compose up -d`
- [ ] Verify each container up: `docker ps`
- [ ] In app, wire `Instrumentator().instrument(app).expose(app, ...)` per §6.2
- [ ] Add custom gauges (top-10 + "other" cardinality cap per §6.2)
- [ ] `systemctl restart ocr-api`
- [ ] Grafana: SSH tunnel, login, add Prometheus data source
- [ ] Import/build dashboard: queue depth, p95 latency, worker RAM, quota usage top-10
- [ ] Configure alerts (§6.3) in Grafana or Alertmanager
- [ ] Add Grafana nginx location (§6.4) with IP allow

### 6.2 Load test

- [ ] `pip install locust` (local machine, not prod)
- [ ] Write locust scenario: auth → submit → poll → done
- [ ] Run 60 req/min × 10 min against prod
- [ ] Record p95, queue depth peak, RAM peak
- [ ] Pass target: p95 < 10s with 2 workers. If fail → add worker OR upgrade VPS

**Gate:** dashboards show live traffic, alert paths tested.

---

## Phase 6.5 — Admin Dashboard (Streamlit)  _(Week 4, Days 1–3)_

Ops-facing UI to manage clients, keys, quota, billing without hand-crafting curl calls. No client-facing portal — admin only. Dogfoods `/admin/v1/*` endpoints built in Phase 5.

**Stack:** Streamlit (reuse legacy `ssm_ui.py` patterns) → calls `/admin/v1/*` via `requests` lib. Runs as `ocr-admin-ui.service` on `127.0.0.1:8503`. nginx IP-allowlist + basic-auth in front.

### 6.5.1 Scaffold

- [ ] `app/admin_ui/` new module (keep separate from client API)
- [ ] `app/admin_ui/main.py` — Streamlit entrypoint
- [ ] `app/admin_ui/api_client.py` — thin wrapper around `requests`, injects `X-Admin-Token`
- [ ] Login page: admin token input → validate via `/admin/v1/health` → store in `st.session_state`
- [ ] Logout clears session

### 6.5.2 Pages

- [ ] **Clients list** — `st.dataframe`: name, email, key_prefix, plan, used/limit, last_seen, active. Filter by active/inactive + search by name/email.
- [ ] **Client detail** — click row → tabs:
  - Overview: plan, status, created_at, key_prefix, period_reset
  - Usage: 30-day line chart (transactions/day), current period counter
  - Jobs: last 50 jobs w/ status
  - Audit log: admin actions on this client
- [ ] **Create client** — form (name, email, plan selector) → POST `/admin/v1/clients` → show raw key ONCE in green box with copy button + warning "save now, not recoverable"
- [ ] **Actions on client detail page:**
  - Rekey button (confirm dialog) → shows new raw key once
  - Change plan (form) → PUT `/admin/v1/clients/{id}/plan`
  - Reset period (confirm) → POST `/admin/v1/clients/{id}/reset`
  - Suspend/Reactivate toggle
- [ ] **Billing report page** — period selector (month picker) → table + CSV download button
- [ ] **System health page** — `/admin/v1/health` deep probe output

### 6.5.3 systemd + nginx

- [ ] Write `/etc/systemd/system/ocr-admin-ui.service` (runs `streamlit run app/admin_ui/main.py --server.port 8503 --server.address 127.0.0.1`, sandboxed like other units)
- [ ] `systemctl enable --now ocr-admin-ui`
- [ ] nginx: add `/admin-ui/` location block → proxy to `127.0.0.1:8503`, same IP allowlist as `/admin/v1/` + basic-auth
- [ ] `nginx -t && systemctl reload nginx`

### 6.5.4 Verify

- [ ] From allowed IP: login → create test client → copy key → use key against `/api/v1/ocr` → returns 202
- [ ] Dashboard shows new client w/ 1 txn used
- [ ] Rekey → old key returns 403, new key works
- [ ] Suspend → both keys return 403
- [ ] Change plan to 10/month → submit 11 → 11th returns 429
- [ ] From disallowed IP: 403 at nginx (never reaches Streamlit)

**Gate:** can onboard + manage a client end-to-end via UI only, no curl.

---

## Phase 7 — SSL  _(When domain ready — post-launch)_

- [ ] Point DNS A record to VPS IP, wait for propagation
- [ ] `apt install -y certbot python3-certbot-nginx`
- [ ] `certbot --nginx -d yourdomain.com`
- [ ] Verify redirect 80→443 in updated nginx config
- [ ] `ufw allow 443/tcp`
- [ ] Update `CORS_ALLOWED_ORIGINS` in `.env`
- [ ] `systemctl restart ocr-api`
- [ ] Test: `curl https://yourdomain.com/api/v1/health`
- [ ] Verify auto-renew timer: `systemctl list-timers | grep certbot`

---

## Phase 9 — Template Editor  _(MANDATORY, ~3–4 weeks)_

Ref: `PRODUCTION_PLAN.md` §Phase 9.

**Status: MANDATORY for v1 launch.** Not optional, not deferred. Runs immediately after Phase 6.

**Prerequisites:** Phase 5 (Admin API) + Phase 6 (Monitoring) complete. v1 does **not** go live without Phase 9.

### 9.0 Decide open questions (½ day)

Answer before coding — these change the schema:

- [ ] Who creates templates? (ops only / ops + customers)
- [ ] Auto-detect template from image or require `doc_type` param? (start: require param)
- [ ] Pricing: flat or premium over built-in parser? (start: flat)
- [ ] Multi-page docs in v1 of Phase 9? (start: no, one page per doc)
- [ ] Required-field missing → fail job or partial result? (start: partial + flag errors)
- [ ] Lock decisions in `PRODUCTION_PLAN.md` §9.8 table

### 9.1 Bbox-aware OCR  _(Day 1)_

- [ ] Extend `app/ocr.py`: add `rec_polys` extraction + `poly_to_xywh` helper
- [ ] Verify existing SSM parser ignores new `bbox` key (no regression)
- [ ] Unit test: `tests/test_ocr.py` — assert bbox shape + present on every line
- [ ] Deploy to prod via `scripts/deploy.sh` behind feature flag (`OCR_RETURN_BBOX=true`) to verify no perf regression
- [ ] Remove flag after 2 days clean

### 9.2 Schema  _(Day 2)_

- [ ] Write `migrations/versions/002_templates.sql`:
  - `doc_templates`, `template_fields`, `client_templates`
  - add `template_id INT REFERENCES doc_templates(id)` + `template_version INT` to `jobs`
- [ ] `alembic revision --autogenerate -m "template tables"` (verify matches hand-written SQL)
- [ ] Apply to staging-equivalent: drop+recreate ocr_billing on a dev box, run `alembic upgrade head`, verify tables

### 9.3 Extraction engine  _(Days 3–5)_

Build in pure-Python first, unit-test heavily, wire into API last.

- [ ] `app/templates/strategies/anchor.py` — given lines + `{labels, direction, max_distance_px}` → return nearest matching text
  - [ ] Test: label above/below/right/same-line variants
  - [ ] Test: multiple label aliases
  - [ ] Test: distance cap works
  - [ ] Test: no match → None
- [ ] `app/templates/strategies/zone.py` — given lines + `{x, y, w, h, merge}` + image size → return text in rect
  - [ ] Test: exact hit
  - [ ] Test: partial overlap (configurable threshold)
  - [ ] Test: merge multiple lines in order (top-to-bottom)
- [ ] `app/templates/strategies/regex.py` — given lines + `{pattern, group}` → capture
  - [ ] Test: multiline, case-insensitive, group 0 vs 1
- [ ] `app/templates/post_process.py` — `date | number | uppercase | trim | strip_currency`
  - [ ] Test: each transform idempotent + safe on None
- [ ] `app/templates/extractor.py` — dispatcher over strategies, aggregates output + error list
  - [ ] Test: all strategies together on realistic sample
  - [ ] Test: required field missing → `_errors` populated, other fields still returned

### 9.4 Admin API  _(Days 6–7)_

- [ ] Extend `app/billing/admin.py` with template CRUD endpoints (per §9.5)
- [ ] `POST /admin/v1/templates` — multipart (sample image + fields JSON)
  - [ ] Save image to `/opt/paddleocr/templates/{id}/sample.jpg`
  - [ ] Return template with id + field IDs
- [ ] `PUT /admin/v1/templates/{id}` — create new version row, mark old inactive
- [ ] `POST /admin/v1/templates/{id}/test` — upload doc, run extraction, return preview (no quota)
- [ ] `POST /admin/v1/clients/{id}/templates` — whitelist management
- [ ] Audit log writes on every admin change
- [ ] Integration test: full CRUD happy path

### 9.5 Client API integration  _(Day 8)_

- [ ] Add optional `doc_type` form field to `POST /api/v1/ocr`
- [ ] Worker: resolve template from `doc_type_code`, verify client whitelisted, run `extract_with_template`
- [ ] If `doc_type` missing: fallback to SSM parser (backward compat, no breaking change)
- [ ] Record `template_id` + `template_version` on `jobs` row
- [ ] `GET /jobs/{id}` response unchanged (fields dict populated by extractor)
- [ ] Integration test: submit with doc_type → verify correct extraction
- [ ] Integration test: submit with unauthorized doc_type → 403
- [ ] Integration test: submit without doc_type → SSM parser runs

### 9.6 Label Studio  _(Days 9–11)_

- [ ] Add `label_studio` service to `/opt/monitoring/docker-compose.yml`
- [ ] `docker-compose up -d label_studio`
- [ ] Add nginx `/labelstudio/` location block with IP allowlist
- [ ] `nginx -t && systemctl reload nginx`
- [ ] Access Label Studio via browser from allowed IP, create admin account
- [ ] Configure OCR labeling template in Label Studio UI (Rectangle + Text Label tags)
- [ ] Upload test image, annotate, export JSON — inspect format
- [ ] Build `scripts/import_label_studio.py`:
  - input: Label Studio export JSON + target `doc_templates.id`
  - output: populated `template_fields` rows
- [ ] Test round-trip: Label Studio annotate → export → import → run extraction on fresh doc → correct fields

### 9.7 Migrate SSM to template (dogfood)  _(Days 12–13)_

- [ ] Create SSM template in Label Studio from existing sample doc
- [ ] Label every field current `parse_ssm` extracts (company_name, reg_no, address, business_type, status, expiry_date, reg_date)
- [ ] Import into DB
- [ ] Run diff test: same doc through old parser vs template → fields identical
- [ ] Fix any mismatches (label variations, date formats, multi-line address)
- [ ] Keep `parse_ssm` as fallback — do NOT delete yet

### 9.8 Rollout  _(Day 14+)_

- [ ] Document template creation workflow in `RUNBOOK.md`
- [ ] Train ops staff to create templates via Label Studio
- [ ] Announce `doc_type` param to existing clients (opt-in)
- [ ] Monitor: extraction error rate per template (add Prometheus gauge)
- [ ] After 1 month clean: deprecate `parse_ssm` code path, set `doc_type=ssm` as default

### 9.9 Gate

- [ ] All strategy unit tests green
- [ ] Admin can create + edit templates via Label Studio end-to-end
- [ ] At least 1 non-SSM template running in production
- [ ] Client isolation verified (no cross-client template access)
- [ ] Per-format extraction error rate < 5% on production traffic

---

## Go-live gate (before accepting first paying client)

- [ ] All Phase 1–5 checklists complete
- [ ] `PRODUCTION_PLAN.md` §Production Checklist all ticked
- [ ] Burst-quota race integration test green
- [ ] Reboot-recovery drill passed
- [ ] `scripts/deploy.sh` exercised once
- [ ] `RUNBOOK.md` exists at `/opt/paddleocr/RUNBOOK.md`
- [ ] `/admin/v1/health` returns full green
- [ ] At least 1 test client onboarded, 100+ successful OCRs, usage counter correct

---

## Rough time budget

| Phase | Estimate | Worst case |
|---|---|---|
| 0 — Pre-flight | 0.5 day | 1 day |
| 1 — Stability | 2 days | 3 days |
| 2 — Nginx | 2 days | 3 days |
| 3 — Database | 2 days | 3 days |
| 4 — Queue + async | 3 days | 5 days |
| 5 — Admin | 3 days | 5 days |
| 6 — Monitoring | 2 days | 3 days |
| 6.5 — Admin Dashboard (Streamlit) | 3 days | 5 days |
| 9 — Template Editor (MANDATORY) | 14 days | 20 days |
| **v1 subtotal (incl. Phase 9)** | **~6–7 weeks** | **~8–9 weeks** |
| 7 — SSL | 0.5 day | 1 day |

Single developer, full-time. Halve it if pairing, double if part-time. Phase 9 is part of v1 launch — no go-live without it.

---

## If you must cut scope

Minimum viable order (drop rest, add later):

1. Phase 0 + 1 — must have (stability)
2. Phase 2 — must have (security)
3. Phase 3 + 4 — must have (the actual product)
4. Phase 5 — can hand-manage clients via SQL for 1–2 weeks
5. Phase 6 — can fly blind briefly, `journalctl` + `redis-cli LLEN` cover 80% of ops

Never cut: quota race test, reboot drill, systemd sandboxing, `.env` 0600, fail2ban.
