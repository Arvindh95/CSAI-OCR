# OCR API — Billing Module Plan

## Overview

Track per-client usage (transactions + pages) against configurable limits.
Enable future invoicing based on actual usage.

---

## Definitions

| Term | Meaning |
|---|---|
| **Transaction** | One API call to `/ocr` or `/verify` |
| **Page** | One image file processed (1 image = 1 page) |
| **Plan** | Configurable limits assigned per client |
| **Period** | Usage reset window (monthly or lifetime) |

**Default plan:**
```
max_transactions     = 2000
max_pages_per_txn    = 5
reset_period         = monthly
```

---

## Database Schema

### `clients`
```sql
CREATE TABLE clients (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    api_key         TEXT NOT NULL UNIQUE,         -- ocr_live_xxxxxxxxxxxxxxxx
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### `plans`
```sql
CREATE TABLE plans (
    id                      SERIAL PRIMARY KEY,
    client_id               INT REFERENCES clients(id) ON DELETE CASCADE,
    max_transactions        INT DEFAULT 2000,
    max_pages_per_txn       INT DEFAULT 5,
    reset_period            TEXT DEFAULT 'monthly', -- monthly | lifetime | none
    effective_from          TIMESTAMPTZ DEFAULT NOW()
);
```

### `usage_log`
```sql
CREATE TABLE usage_log (
    id                  BIGSERIAL PRIMARY KEY,
    client_id           INT REFERENCES clients(id),
    endpoint            TEXT,                      -- /ocr | /verify
    pages_submitted     INT,
    pages_processed     INT,
    status              TEXT,                      -- success | rejected | error
    reject_reason       TEXT,
    response_time_ms    INT,
    timestamp           TIMESTAMPTZ DEFAULT NOW()
);
```

### `billing_summary`
```sql
CREATE TABLE billing_summary (
    id                      SERIAL PRIMARY KEY,
    client_id               INT REFERENCES clients(id),
    period_start            DATE,
    period_end              DATE,
    total_transactions      INT DEFAULT 0,
    total_pages             INT DEFAULT 0,
    rejected_transactions   INT DEFAULT 0,
    generated_at            TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Request Flow

```
Incoming request
    │
    ▼
Extract X-API-Key header
    │
    ├── Missing / invalid → 401 Unauthorized
    │
    ▼
Load client + plan from DB
    │
    ├── Client inactive → 403 Forbidden
    │
    ▼
Count current period usage
    │
    ├── transactions_used >= max_transactions → 429 Quota Exceeded
    │
    ▼
Count pages in request
    │
    ├── pages > max_pages_per_txn → 400 Too Many Pages
    │
    ▼
Process OCR
    │
    ▼
Log to usage_log (success)
    │
    ▼
Return result + usage headers:
    X-Transactions-Used: 150
    X-Transactions-Remaining: 1850
    X-Pages-Limit: 5
```

---

## API Endpoints

### Client-facing

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ocr` | OCR extract (requires API key) |
| `POST` | `/verify` | OCR verify (requires API key) |
| `GET` | `/usage/me` | Client checks own usage |

### Admin (protected by admin token)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/admin/clients` | Create new client + generate API key |
| `GET` | `/admin/clients` | List all clients |
| `GET` | `/admin/clients/{id}` | Get client detail |
| `PATCH` | `/admin/clients/{id}` | Update client (name, email, active) |
| `DELETE` | `/admin/clients/{id}` | Deactivate client |
| `GET` | `/admin/clients/{id}/usage` | View client usage |
| `PUT` | `/admin/clients/{id}/plan` | Update client plan/limits |
| `POST` | `/admin/clients/{id}/reset` | Manual usage reset |
| `GET` | `/admin/billing/report` | Full billing report (all clients) |
| `GET` | `/admin/billing/report?period=2025-04` | Report for specific period |

---

## Auth

### Client auth
```
Header: X-API-Key: ocr_live_xxxxxxxxxxxxxxxxxxxxxxxx
```

### Admin auth
```
Header: X-Admin-Token: <secret from env var>
```

### API key format
```
ocr_live_{32-char UUID without dashes}
```
Example: `ocr_live_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4`

---

## Response Headers (every request)

```
X-Transactions-Used: 150
X-Transactions-Remaining: 1850
X-Pages-Limit: 5
X-Period-Reset: 2025-05-01
```

---

## Error Responses

| Code | Reason | Message |
|---|---|---|
| 401 | Missing/invalid API key | `"Invalid or missing API key"` |
| 403 | Client inactive | `"Account suspended"` |
| 429 | Transaction quota exceeded | `"Monthly transaction limit reached (2000/2000)"` |
| 400 | Too many pages in request | `"Max 5 pages per transaction"` |

---

## File Structure (changes to codebase)

```
/opt/paddleocr/
├── app/
│   ├── main.py           ← add auth + billing middleware
│   ├── ocr.py            ← unchanged
│   ├── parser.py         ← unchanged
│   ├── billing/
│   │   ├── __init__.py
│   │   ├── db.py         ← DB connection (asyncpg / SQLAlchemy)
│   │   ├── models.py     ← SQLAlchemy models
│   │   ├── middleware.py ← API key check + quota enforcement
│   │   ├── admin.py      ← admin router
│   │   └── usage.py      ← usage tracking helpers
├── migrations/
│   └── 001_billing_schema.sql
├── .env                  ← DB_URL, ADMIN_TOKEN
├── requirements.txt      ← add: asyncpg, sqlalchemy, python-dotenv
```

---

## Environment Variables

```env
DATABASE_URL=postgresql://ocr_user:password@localhost:5432/ocr_billing
ADMIN_TOKEN=your-secret-admin-token
```

---

## Implementation Phases

### Phase 1 — Foundation
- [ ] PostgreSQL setup + schema migration
- [ ] SQLAlchemy models
- [ ] API key middleware (auth only, no limits yet)
- [ ] Usage logging on every request

### Phase 2 — Quota Enforcement
- [ ] Transaction counter per period
- [ ] Page limit per transaction
- [ ] 429/400 rejection responses
- [ ] Usage headers on all responses

### Phase 3 — Admin API
- [ ] Create/list/update clients
- [ ] View usage per client
- [ ] Update plan limits
- [ ] Manual reset

### Phase 4 — Reporting
- [ ] Billing summary endpoint
- [ ] Period-based report (monthly)
- [ ] CSV export option
- [ ] Auto-generate monthly summary (cron)

---

## Open Questions

1. Will clients prepay or postpay? (affects whether to hard-block or soft-warn at limit)
2. Overage policy — block at limit or allow + flag for billing?
3. Multiple plans/tiers needed or single configurable plan per client?
4. Need email alerts when client hits 80% / 100% of quota?
5. UI dashboard for admin or API-only sufficient?
