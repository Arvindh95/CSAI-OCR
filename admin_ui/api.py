import os

import httpx

API_BASE = os.environ.get("CSAI_ADMIN_API", "http://127.0.0.1:8003")
_TIMEOUT = 15.0


def _c() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=_TIMEOUT)


def list_clients(active_only: bool = False) -> list[dict]:
    with _c() as c:
        r = c.get("/admin/v1/clients", params={"active_only": active_only})
        r.raise_for_status()
        return r.json()


def get_client(client_id: int) -> dict:
    with _c() as c:
        r = c.get(f"/admin/v1/clients/{client_id}")
        r.raise_for_status()
        return r.json()


def create_client(name: str, email: str, max_transactions: int,
                  max_pages_per_txn: int, reset_period: str) -> dict:
    with _c() as c:
        r = c.post("/admin/v1/clients", json={
            "name": name, "email": email,
            "max_transactions": max_transactions,
            "max_pages_per_txn": max_pages_per_txn,
            "reset_period": reset_period,
        })
        r.raise_for_status()
        return r.json()


def update_client(client_id: int, **fields) -> dict:
    with _c() as c:
        r = c.patch(f"/admin/v1/clients/{client_id}",
                    json={k: v for k, v in fields.items() if v is not None})
        r.raise_for_status()
        return r.json()


def deactivate_client(client_id: int) -> dict:
    with _c() as c:
        r = c.delete(f"/admin/v1/clients/{client_id}")
        r.raise_for_status()
        return r.json()


def rotate_key(client_id: int) -> dict:
    with _c() as c:
        r = c.post(f"/admin/v1/clients/{client_id}/rotate-key")
        r.raise_for_status()
        return r.json()


def get_plan(client_id: int) -> dict:
    with _c() as c:
        r = c.get(f"/admin/v1/clients/{client_id}/plan")
        r.raise_for_status()
        return r.json()


def upsert_plan(client_id: int, max_transactions: int,
                max_pages_per_txn: int, reset_period: str) -> dict:
    with _c() as c:
        r = c.put(f"/admin/v1/clients/{client_id}/plan", json={
            "max_transactions": max_transactions,
            "max_pages_per_txn": max_pages_per_txn,
            "reset_period": reset_period,
        })
        r.raise_for_status()
        return r.json()


def get_usage(client_id: int) -> dict:
    with _c() as c:
        r = c.get(f"/admin/v1/clients/{client_id}/usage")
        r.raise_for_status()
        return r.json()


def reset_quota(client_id: int) -> dict:
    with _c() as c:
        r = c.post(f"/admin/v1/clients/{client_id}/quota/reset")
        r.raise_for_status()
        return r.json()


def list_jobs(client_id: int, status: str | None = None,
              limit: int = 50, offset: int = 0) -> list[dict]:
    with _c() as c:
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        r = c.get(f"/admin/v1/clients/{client_id}/jobs", params=params)
        r.raise_for_status()
        return r.json()
