# CSAI-OCR Deployment Guide

Deploy the CSAI-OCR service on a fresh Linux VPS (tested on Ubuntu 22.04 / 24.04).

## Architecture

```
                          :80  nginx (reverse proxy + basic-auth + rate-limit)
                         /
client ---> public IP --+--- /api/v1/*   --> uvicorn :8003 (FastAPI)
                        +--- /admin/v1/* --> uvicorn :8003 (allowlist 127.0.0.1)
                        +--- /            --> streamlit :8503 (admin UI, basic-auth)
                                                   |
                           uvicorn :8003 -----> PostgreSQL :5432
                                   |          \
                                   +-- enqueue --> Redis :6379
                                                        |
                                                        v
                                       rq worker: ocr-worker@N.service
                                                        |
                                                        v
                                              PaddleOCR models (disk cache)
```

Timers: `ocr-reaper` (1 min, stale jobs), `ocr-reconcile` (5 min, quotas), `ocr-disksweep` (daily, cleanup).

## Prerequisites

- Ubuntu 22.04+ with root (or sudo) access
- 4 vCPU / 8 GB RAM / 50 GB disk minimum (PaddleOCR models ~2 GB + templates/storage grows)
- Domain or static IP
- Open ports: 22 (SSH), 80 (HTTP). 443 if adding TLS.

## 1. System packages

```bash
apt update && apt upgrade -y
apt install -y \
    python3 python3-venv python3-dev build-essential \
    postgresql postgresql-contrib \
    redis-server \
    nginx apache2-utils \
    git curl libmagic1 libgl1 libglib2.0-0 \
    fail2ban
```

## 2. Create service user

```bash
useradd -m -s /bin/bash claudeuser
install -d -o claudeuser -g claudeuser /opt/ocr-saas
install -d -o claudeuser -g claudeuser /var/log/ocr
install -d -o claudeuser -g claudeuser /opt/ocr-saas/storage /opt/ocr-saas/templates
```

## 3. Clone and build venv

```bash
sudo -u claudeuser -H bash <<'EOF'
cd /opt/ocr-saas
git clone <YOUR_REPO_URL> .
python3 -m venv venv
./venv/bin/pip install --upgrade pip wheel
./venv/bin/pip install -r requirements.txt
EOF
```

First PaddleOCR run downloads models (~2 GB) into `~/.paddlex`. Pre-warm if desired:

```bash
sudo -u claudeuser -H /opt/ocr-saas/venv/bin/python -c \
  "from paddleocr import PaddleOCR; PaddleOCR(use_textline_orientation=True, lang='en')"
```

## 4. PostgreSQL

```bash
sudo -u postgres psql <<SQL
CREATE ROLE ocr_billing WITH LOGIN PASSWORD 'CHANGE_ME';
CREATE DATABASE ocr_billing OWNER ocr_billing;
SQL
```

Apply schema (two SQL migrations in `alembic/versions/`):

```bash
sudo -u claudeuser -H bash <<'EOF'
cd /opt/ocr-saas
PGPASSWORD=CHANGE_ME psql -h 127.0.0.1 -U ocr_billing -d ocr_billing \
    -f alembic/versions/001_billing_schema.sql
PGPASSWORD=CHANGE_ME psql -h 127.0.0.1 -U ocr_billing -d ocr_billing \
    -f alembic/versions/002_templates_schema.sql
EOF
```

## 5. Environment file

Create `/opt/ocr-saas/.env` (mode 600, owned by `claudeuser`):

```bash
cat >/opt/ocr-saas/.env <<'EOF'
DATABASE_URL=postgresql+asyncpg://ocr_billing:CHANGE_ME@127.0.0.1:5432/ocr_billing
REDIS_URL=redis://127.0.0.1:6379/0
ADMIN_TOKEN=<generate: openssl rand -hex 32>
API_KEY_PEPPER=<generate: openssl rand -hex 32>
ENV=production
CORS_ALLOWED_ORIGINS=https://your.domain
TEMPLATES_DIR=/opt/ocr-saas/templates
OCR_STORAGE_DIR=/opt/ocr-saas/storage
LOG_CONFIG=/opt/ocr-saas/config/logging.json
EOF
chown claudeuser:claudeuser /opt/ocr-saas/.env
chmod 600 /opt/ocr-saas/.env
```

Required vars: `DATABASE_URL`, `API_KEY_PEPPER`, `ADMIN_TOKEN`. The rest have sensible defaults in code.

## 6. Install systemd units

Copy the shipped units into `/etc/systemd/system/`:

```bash
cp /opt/ocr-saas/systemd/ocr-api.service         /etc/systemd/system/
cp /opt/ocr-saas/systemd/ocr-worker@.service     /etc/systemd/system/
cp /opt/ocr-saas/systemd/ocr-ui.service          /etc/systemd/system/
cp /opt/ocr-saas/systemd/ocr-reaper.service      /etc/systemd/system/
cp /opt/ocr-saas/systemd/ocr-reaper.timer        /etc/systemd/system/
cp /opt/ocr-saas/systemd/ocr-reconcile.service   /etc/systemd/system/
cp /opt/ocr-saas/systemd/ocr-reconcile.timer     /etc/systemd/system/
cp /opt/ocr-saas/systemd/ocr-disksweep.service   /etc/systemd/system/
cp /opt/ocr-saas/systemd/ocr-disksweep.timer     /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now ocr-api ocr-worker@1 ocr-ui
systemctl enable --now ocr-reaper.timer ocr-reconcile.timer ocr-disksweep.timer
```

Scale workers: `systemctl enable --now ocr-worker@2` (one instance per CPU core is a safe starting point).

## 7. nginx

```bash
# replace <PUBLIC_IP_OR_DOMAIN> in the shipped config
sed "s/173.212.247.3/<PUBLIC_IP_OR_DOMAIN>/g" \
    /opt/ocr-saas/nginx/csai-ocr.conf \
    > /etc/nginx/sites-available/csai-ocr

ln -sf /etc/nginx/sites-available/csai-ocr /etc/nginx/sites-enabled/csai-ocr

# Remove the stock default vhost. Otherwise it becomes default_server
# and any request without a matching Host header is served by the empty
# /var/www/html site (you will see 404s on /health etc. from localhost).
rm -f /etc/nginx/sites-enabled/default

# Basic-auth credentials for the Streamlit admin UI at /
htpasswd -c /etc/nginx/.htpasswd-csai admin

nginx -t && systemctl reload nginx
```

For HTTPS, install `certbot`, obtain a cert for your domain, and add `listen 443 ssl;` plus the cert paths to the server block.

## 8. fail2ban (optional, shipped)

```bash
cp -r /opt/ocr-saas/config/fail2ban/* /etc/fail2ban/
systemctl restart fail2ban
```

## 9. Verify

```bash
systemctl is-active ocr-api ocr-worker@1 ocr-ui nginx redis-server postgresql
curl -sS http://127.0.0.1:8003/health                       # {"status":"ok"}
curl -sS -H 'Host: <your.domain>' http://127.0.0.1/health   # {"status":"ok"}
redis-cli llen rq:queue:csai-ocr                            # 0 (worker queue name)
systemctl list-timers | grep ocr-                           # 3 timers scheduled
```

Open `http://<your.domain>/` in a browser, log in with the basic-auth credentials from step 7. The Streamlit admin UI loads.

## 10. Create first client / API key

```bash
# ADMIN_TOKEN must be the value from /opt/ocr-saas/.env
curl -sS -X POST http://127.0.0.1/admin/v1/clients \
    -H "X-Admin-Token: $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"acme","email":"ops@acme.com"}'
```

The response contains a one-time `api_key`. Save it — only the prefix is recoverable later.

Call the public API:

```bash
curl -sS -X POST http://<your.domain>/api/v1/ocr \
    -H "X-API-Key: ocr_live_..." \
    -F "file=@invoice.jpg"
```

## Updating

```bash
sudo -u claudeuser -H bash <<'EOF'
cd /opt/ocr-saas
git pull
./venv/bin/pip install -r requirements.txt
EOF
systemctl restart ocr-api 'ocr-worker@*' ocr-ui
```

If a migration ships, apply it before restart.

## Troubleshooting

| Symptom | Likely cause | Check |
| --- | --- | --- |
| `curl /health` from localhost returns 404 HTML with `nginx/1.24.0` | `sites-enabled/default` still installed, catching `Host: 127.0.0.1` | `ls /etc/nginx/sites-enabled/` — remove `default` |
| `/admin/v1/*` returns `403 Forbidden` | Request from non-localhost IP (allowlist denies) | SSH to host and use 127.0.0.1 |
| Jobs stuck in `queued` | Worker not running | `systemctl status ocr-worker@1`, `journalctl -u ocr-worker@1 -n 100` |
| OCR times out | Paddle first-run download or CPU saturated | `journalctl -u ocr-worker@1 -f` during a test request |
| `API_KEY_PEPPER` KeyError on boot | `.env` not loaded or missing var | `EnvironmentFile=` only in `ocr-worker@.service` — copy the pattern to `ocr-api.service` if you add env vars the API reads |
| 429 from nginx | Rate limit `csai_per_key` (60/min) or `csai_per_ip` (100/min) tripped | Tune the `limit_req_zone` lines in `csai-ocr.conf` |

Logs:
- API: `journalctl -u ocr-api -f`
- Worker: `/var/log/ocr/worker-1.log`, `/var/log/ocr/worker-1.err`
- nginx: `/var/log/nginx/csai-ocr.access.log`, `csai-ocr.error.log`

## Paths reference

| Path | Purpose |
| --- | --- |
| `/opt/ocr-saas` | App code + venv |
| `/opt/ocr-saas/.env` | Secrets (mode 600) |
| `/opt/ocr-saas/storage` | Uploaded files, job outputs |
| `/opt/ocr-saas/templates` | Template JSON files |
| `/var/log/ocr` | Worker logs |
| `/etc/systemd/system/ocr-*.service` | Unit files |
| `/etc/nginx/sites-enabled/csai-ocr` | nginx vhost |
| `/etc/nginx/.htpasswd-csai` | Basic-auth users for Streamlit UI |
