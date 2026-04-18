import re
from datetime import datetime


_LABEL_PREFIX_RE = re.compile(r"^[\s:：\-–—]+")
_LABEL_SUFFIX_RE = re.compile(r"[\s:：\-–—]+$")


def _strip_label_punct(s: str) -> str:
    s = _LABEL_PREFIX_RE.sub("", s)
    s = _LABEL_SUFFIX_RE.sub("", s)
    return s.strip()


def _as_date(s: str) -> str | None:
    cleaned = _strip_label_punct(s)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y",
                "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
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
        return _strip_label_punct(value)
    if rule == "uppercase":
        return _strip_label_punct(value).upper()
    if rule == "lowercase":
        return _strip_label_punct(value).lower()
    if rule == "number":
        return _as_number(value)
    if rule == "date":
        return _as_date(value)
    if rule.startswith("strip_chars:"):
        chars = rule[len("strip_chars:"):]
        return value.strip(chars).strip()
    return value
