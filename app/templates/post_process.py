import re
from datetime import datetime


def _as_date(s: str) -> str | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y",
                "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _as_number(s: str) -> float | None:
    cleaned = re.sub(r"[^\d.\-]", "", s.replace(",", ""))
    if not cleaned or cleaned in ("-", ".", "-."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def apply_post_process(value: str | None, rule: str | None):
    if value is None or rule is None:
        return value
    rule = rule.lower()
    if rule == "trim":
        return value.strip()
    if rule == "uppercase":
        return value.strip().upper()
    if rule == "lowercase":
        return value.strip().lower()
    if rule == "number":
        return _as_number(value)
    if rule == "date":
        return _as_date(value)
    return value
