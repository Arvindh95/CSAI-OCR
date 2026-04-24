"""Shared error formatter for the admin UI.

All admin pages surface errors via `st.error(err_to_str(exc))`. The API
returns structured JSON of the shape
`{"error": {"code": ..., "message": ..., "request_id": ...}}` — we parse
that so the user sees a human-readable message instead of raw JSON.
"""
from __future__ import annotations

import json
import httpx


def err_to_str(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        try:
            body = resp.json()
        except (json.JSONDecodeError, ValueError):
            body = None
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            err = body["error"]
            msg = err.get("message") or err.get("code") or "unknown error"
            code = err.get("code")
            rid = err.get("request_id")
            parts = [f"API {resp.status_code}", msg]
            tags = []
            if code and code != msg:
                tags.append(f"code={code}")
            if rid:
                tags.append(f"request_id={rid}")
            if tags:
                parts.append(f"({', '.join(tags)})")
            return " · ".join(parts[:2]) + (" " + parts[2] if len(parts) > 2 else "")
        # Fallback: raw body
        return f"API {resp.status_code}: {resp.text[:500]}"
    if isinstance(exc, httpx.HTTPError):
        return f"Network error: {exc}"
    return f"{type(exc).__name__}: {exc}"
