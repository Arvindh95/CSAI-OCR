# CSAI-OCR Server / Infrastructure

Reference for the production VPS that runs CSAI-OCR. Snapshot taken 2026-04-29; values reflect what's actually running on the host, not aspirational config.

---

## 1. Host

| | |
| --- | --- |
| Hostname | `vmi3234511` (Contabo-style VM name) |
| Public IP | redacted in docs; placeholder `your-server.example.com` |
| Provider | KVM virtual machine (`pc-i440fx-9.0` BIOS, single socket) |
| OS | **Ubuntu 24.04.4 LTS** ("Noble Numbat") |
| Kernel | `6.8.0-110-generic` (PREEMPT_DYNAMIC) |
| Architecture | x86_64 |
| Uptime at snapshot | 11 days |

## 2. Hardware

| Resource | Value |
| --- | --- |
| CPU | AMD EPYC (with IBPB), 8 vCPUs, 1 thread/core, 2.0 GHz base |
| RAM | 23 GiB total, no swap |
| Disk | 193 GiB ext4 single root partition `/dev/sda1` (currently 34 GiB used, 18%) |

**Key constraint:** RAM headroom. PaddleOCR resident set has been observed at ~16 GiB on this host. With base services (~5 GiB) + Java/Elasticsearch + Streamlit UI, free memory drops to ~3 GiB during OCR. Two concurrent OCR jobs would OOM. That's why `ocr-worker@N` is run as a **single instance** (`ocr-worker@1`) and `WORKER_COUNT=1`.

There is **no swap**. OOM = process kill, not a slowdown.

---

## 3. Network

### Firewall (ufw)

Default policy: **deny incoming**, allow outgoing.

| Port | Proto | Action | Purpose |
| --- | --- | --- | --- |
| 22 | tcp | ALLOW | SSH (fail2ban-protected) |
| 80 | tcp | ALLOW | nginx (public HTTP — terminates basic-auth and proxies to internal services) |
| 8003 | tcp | DENY | FastAPI (loopback only) |
| 8503 | tcp | DENY | Streamlit admin UI (loopback only) |
| 8002 / 8502 | tcp | DENY | Reserved/legacy |
| 6379 | tcp | DENY | Redis (loopback only) |

Both IPv4 and IPv6 rules mirror each other. **There is no TLS terminator yet** — nginx listens on 80, not 443. TLS is on the deferred TODO list.

### Listening sockets (snapshot)

| Process | Address:port | Exposure |
| --- | --- | --- |
| nginx | `0.0.0.0:80` | public (CSAI-OCR vhost) |
| nginx | `0.0.0.0:8080` | public (`grp-images` separate project vhost) |
| sshd | `0.0.0.0:22` | public, fail2ban gated |
| FastAPI / uvicorn | `127.0.0.1:8003` | nginx proxy only |
| Streamlit (CSAI admin) | `127.0.0.1:8503` | nginx proxy only |
| PostgreSQL 16 | `127.0.0.1:5432` | local app + worker |
| Redis 7 | `127.0.0.1:6379` | local app + worker |
| Prometheus | `127.0.0.1:9090` | local Grafana scrape |
| Grafana | `127.0.0.1:3000` | proxied via separate vhost |
| Elasticsearch | `:::9200`, `9300` | dual-stack (separate project) |
| Kibana | `0.0.0.0:5601` | separate project |
| ollama | `127.0.0.1:11434` | unrelated |
| Streamlit (separate) | `0.0.0.0:8501` | separate project |

CSAI-OCR services bind to **localhost only**; nginx is the single public entry point for HTTP traffic.

---

## 4. CSAI-OCR services (systemd)

All units run as user `claudeuser` with working dir `/opt/ocr-saas`.

### Long-running services

| Unit | Process | Bind | Purpose |
| --- | --- | --- | --- |
| `ocr-api.service` | `uvicorn app.main:app --workers 1` | `127.0.0.1:8003` | FastAPI HTTP API |
| `ocr-worker@1.service` | `python -m app.rq_worker` | – | RQ worker pulling from `csai-ocr` queue |
| `ocr-ui.service` | `streamlit run admin_ui/app.py` | `127.0.0.1:8503` | Operator console |

`ocr-api` log config: `--log-config /opt/ocr-saas/config/logging.json` (JSON access log).

### Maintenance timers

| Timer | Cadence | Service runs |
| --- | --- | --- |
| `ocr-reaper.timer` | every 1 min | `scripts/reap_stale_jobs.py` — fails jobs stuck in `running` |
| `ocr-reconcile.timer` | every 5 min | `scripts/reconcile_quota.py` — sync Redis quota counter to `usage_logs` |
| `ocr-disksweep.timer` | daily 00:00 | `scripts/sweep_disk.py` — purge orphaned uploads under `/opt/ocr-saas/storage/` |

### Service-level environment

```
User=claudeuser
WorkingDirectory=/opt/ocr-saas
Environment=PYTHONPATH=/opt/ocr-saas
Environment=HOME=/opt/ocr-saas
EnvironmentFile=/opt/ocr-saas/.env       (mode 0600, secrets)
```

Secrets in `.env`: `DATABASE_URL`, `REDIS_URL`, `API_KEY_PEPPER`, admin basic-auth hash, `OCR_STORAGE_DIR`.

---

## 5. Filesystem layout

```
/opt/
├── ocr-saas/                    ← CSAI-OCR repo checkout (claudeuser)
│   ├── app/                     ← FastAPI + worker code
│   ├── admin_ui/                ← Streamlit UI
│   ├── alembic/versions/*.sql   ← raw-SQL migrations
│   ├── config/
│   │   ├── logging.json
│   │   └── fail2ban/
│   ├── nginx/csai-ocr.conf      ← shipped vhost (deployed copy in /etc/nginx)
│   ├── systemd/                 ← unit/timer source files
│   ├── scripts/                 ← reaper, reconcile, disksweep
│   ├── tests/
│   ├── storage/                 ← uploaded page images (transient, swept daily)
│   ├── venv/                    ← Python 3.12 virtualenv
│   └── .env                     ← secrets (mode 0600)
├── paddleocr/                   ← unrelated (older PaddleOCR install dir)
├── grp-manuals/  grp-scripts/   ← separate projects on same host
├── rfs-data/
└── containerd/
```

`storage/` holds raw uploads as `<job_id>_p<page_index>.{png,jpg,tif}`. Files are unlinked when the job finishes (`done` or `failed`). Stragglers are removed by the daily disksweep.

---

## 6. Stack versions (host-installed)

| Component | Version | Source | Notes |
| --- | --- | --- | --- |
| Ubuntu | 24.04.4 LTS | OS | Noble Numbat |
| Linux kernel | 6.8.0-110 | apt | |
| Python | 3.12.3 | apt (`python3`) | venv at `/opt/ocr-saas/venv` |
| PostgreSQL | **16.13** | `postgresql-16` apt | Cluster: `16-main` |
| Redis | **7.0.15** | apt | bound to `127.0.0.1` only |
| nginx | 1.24.0 | apt | reverse proxy + basic-auth |
| systemd | 255 | OS | unit + timer supervisor |
| fail2ban | apt | active | SSH + nginx auth bans |

Application Python deps are pinned in `requirements.txt` (see `TECH_STACK.md` §14).

---

## 7. Other tenants on the same host

The VPS hosts non-CSAI workloads. They share CPU/RAM but are isolated by user and ports.

| Stack | Bind | Owner |
| --- | --- | --- |
| Elasticsearch (9200/9300) + Kibana (5601) | dual-stack | log search for separate project |
| Grafana (3000) + Prometheus (9090) | loopback | metrics for CSAI-OCR + others |
| ollama (11434) | loopback | local LLM runtime |
| `grp-images` nginx vhost (8080) | public | separate project |
| Streamlit on 8501 | public | unrelated UI |

Co-tenancy implication: a runaway non-CSAI process can starve CSAI-OCR of memory. Worth migrating CSAI-OCR to a dedicated VPS once traffic justifies it.

---

## 8. Network entry / proxy

`nginx` (`/etc/nginx/sites-enabled/csai-ocr`) is the only public ingress for CSAI-OCR.

Routing inside the vhost:

| Path | Upstream | Auth |
| --- | --- | --- |
| `/api/v1/*` | `127.0.0.1:8003` | API key in `X-API-Key` header (validated by FastAPI) + nginx `limit_req_zone` rate limit |
| `/admin/v1/*` | `127.0.0.1:8003` | API key + nginx IP allowlist (admin endpoints never face open internet) |
| `/health`, `/metrics` | `127.0.0.1:8003` | open / scrape-only |
| `/` (admin UI) | `127.0.0.1:8503` | nginx basic-auth (`/etc/nginx/.htpasswd-csai`) |

**TLS:** not yet terminated on this host. Public traffic is HTTP/80. Adding Let's Encrypt + redirecting to 443 is on the TODO list before external customer rollout.

---

## 9. Databases

### PostgreSQL 16

Cluster: `16-main` on `127.0.0.1:5432`. Two DBs:

| DB | Purpose |
| --- | --- |
| `postgres` | default admin DB |
| `ocr_billing` | CSAI-OCR schema (clients, plans, jobs, templates, usage_logs, etc.) |

Connection string in `.env`: `postgresql+asyncpg://...@127.0.0.1/ocr_billing`. Schema applied via raw SQL files in `alembic/versions/`.

### Redis 7

Single instance on `127.0.0.1:6379`. No password (loopback-only and ufw-firewalled). Three logical uses keyed by prefix:

| Prefix | Purpose |
| --- | --- |
| `rq:*` | Job queue (`csai-ocr` queue + per-job hashes) |
| `idem:*` | Idempotency-key dedupe (24 h TTL) |
| `quota:*` | Per-client per-period transaction counter (monthly TTL) |

---

## 10. Operational basics

### Deploy

```bash
# Local: push to feature branch (or main when merged)
git push origin <branch>

# VPS: pull as the service user, restart units
ssh root@<server>
sudo -u claudeuser bash -c 'cd /opt/ocr-saas && git pull --ff-only'
systemctl restart ocr-api ocr-worker@1 ocr-ui
```

If the change touches dependencies:

```bash
sudo -u claudeuser /opt/ocr-saas/venv/bin/pip install -r /opt/ocr-saas/requirements.txt
```

### Logs

All services log to journald. No log files on disk.

```bash
journalctl -u ocr-api -f
journalctl -u ocr-worker@1 --since '10 min ago'
journalctl -u ocr-ui -n 100
```

### Database backup

`pg_dump ocr_billing | gzip > /opt/backups/ocr_billing_$(date +%F).sql.gz` — run manually before risky migrations. (Automated daily backup is on the TODO list.)

### Restart everything

```bash
systemctl restart ocr-api ocr-worker@1 ocr-ui
systemctl status ocr-api ocr-worker@1 ocr-ui --no-pager
```

### Quota / job reconciliation

```bash
# Reap any 'running' jobs older than threshold
sudo -u claudeuser /opt/ocr-saas/venv/bin/python /opt/ocr-saas/scripts/reap_stale_jobs.py

# Recompute Redis counter from usage_logs
sudo -u claudeuser /opt/ocr-saas/venv/bin/python /opt/ocr-saas/scripts/reconcile_quota.py
```

Both are also triggered on timers; manual run is for ad-hoc reconciliation.

---

## 11. Known limitations / TODO

- **No TLS** — nginx serves HTTP/80 only. Add certbot before customer launch.
- **No swap** — keeps OOM behavior predictable but means a single bad allocation kills the worker.
- **Single worker** — concurrent OCR is impossible because two PaddleOCR processes would exceed RAM.
- **Single VPS** — no HA. A box reboot is downtime.
- **No automated DB backup** — only manual `pg_dump`.
- **Co-tenancy with unrelated projects** — Elasticsearch, Kibana, ollama, grp-* sit on the same host and compete for RAM.
- **Basic firewall only** — ufw + fail2ban; no WAF.

---

## 12. Quick command cheatsheet

```bash
# Status
systemctl status ocr-api ocr-worker@1 ocr-ui --no-pager

# RAM / CPU snapshot
free -h
top -bn1 -p $(pgrep -f 'rq_worker|app.main') | tail -10

# Queue depth
sudo -u claudeuser /opt/ocr-saas/venv/bin/python -c \
  "import redis; r=redis.Redis(); print(r.llen('rq:queue:csai-ocr'))"

# DB live job count
sudo -u postgres psql ocr_billing -c \
  "SELECT status, count(*) FROM jobs GROUP BY status;"

# Tail latest worker job
journalctl -u ocr-worker@1 --since '5 min ago' --no-pager

# Disk usage of storage dir
du -sh /opt/ocr-saas/storage
```
