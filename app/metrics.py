from prometheus_client import Counter, Gauge, Histogram

jobs_total = Counter(
    "csai_jobs_total",
    "OCR jobs by terminal status",
    ["status", "endpoint"],
)

jobs_submitted_total = Counter(
    "csai_jobs_submitted_total",
    "OCR jobs accepted by submit endpoint",
    ["template", "mime"],
)

ocr_duration_seconds = Histogram(
    "csai_ocr_duration_seconds",
    "Wall time from queued_at to completed_at",
    ["status"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)

quota_denies_total = Counter(
    "csai_quota_denies_total",
    "429 quota-exceeded responses",
)

auth_failures_total = Counter(
    "csai_auth_failures_total",
    "401 auth failures",
)

idempotency_conflicts_total = Counter(
    "csai_idempotency_conflicts_total",
    "409 idempotency conflicts",
)

queue_depth = Gauge(
    "csai_queue_depth",
    "RQ queue depth (scraped)",
    ["queue"],
)

active_clients = Gauge(
    "csai_active_clients",
    "Distinct clients seen in last scrape window",
)
