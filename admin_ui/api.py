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


def list_templates(active_only: bool = False,
                   doc_type_code: str | None = None,
                   client_id: int | None = None) -> list[dict]:
    with _c() as c:
        params: dict = {"active_only": active_only}
        if doc_type_code:
            params["doc_type_code"] = doc_type_code
        if client_id is not None:
            params["client_id"] = client_id
        r = c.get("/admin/v1/templates", params=params)
        r.raise_for_status()
        return r.json()


def get_template(template_id: int) -> dict:
    with _c() as c:
        r = c.get(f"/admin/v1/templates/{template_id}")
        r.raise_for_status()
        return r.json()


def create_template(name: str, doc_type_code: str,
                    client_id: int | None, fields: list[dict]) -> dict:
    body = {"name": name, "doc_type_code": doc_type_code, "fields": fields}
    if client_id is not None:
        body["client_id"] = client_id
    with _c() as c:
        r = c.post("/admin/v1/templates", json=body)
        r.raise_for_status()
        return r.json()


def update_template(template_id: int, name: str | None,
                    fields: list[dict] | None) -> dict:
    body: dict = {}
    if name is not None:
        body["name"] = name
    if fields is not None:
        body["fields"] = fields
    with _c() as c:
        r = c.put(f"/admin/v1/templates/{template_id}", json=body)
        r.raise_for_status()
        return r.json()


def delete_template(template_id: int) -> dict:
    with _c() as c:
        r = c.delete(f"/admin/v1/templates/{template_id}")
        r.raise_for_status()
        return r.json()


def upload_page(template_id: int, page_index: int,
                filename: str, content: bytes, mime: str) -> dict:
    with _c() as c:
        r = c.post(
            f"/admin/v1/templates/{template_id}/pages",
            data={"page_index": str(page_index)},
            files={"file": (filename, content, mime)},
        )
        r.raise_for_status()
        return r.json()


def delete_page(template_id: int, page_index: int) -> dict:
    with _c() as c:
        r = c.delete(f"/admin/v1/templates/{template_id}/pages/{page_index}")
        r.raise_for_status()
        return r.json()


def test_template(template_id: int, filename: str,
                  content: bytes, mime: str) -> dict:
    with _c() as c:
        r = c.post(
            f"/admin/v1/templates/{template_id}/test",
            files={"file": (filename, content, mime)},
            timeout=120.0,
        )
        r.raise_for_status()
        return r.json()


def list_client_templates(client_id: int) -> list[dict]:
    with _c() as c:
        r = c.get(f"/admin/v1/clients/{client_id}/templates")
        r.raise_for_status()
        return r.json()


def grant_template(client_id: int, template_id: int) -> dict:
    with _c() as c:
        r = c.post(f"/admin/v1/clients/{client_id}/templates",
                   json={"template_id": template_id})
        r.raise_for_status()
        return r.json()


def revoke_template(client_id: int, template_id: int) -> dict:
    with _c() as c:
        r = c.delete(f"/admin/v1/clients/{client_id}/templates/{template_id}")
        r.raise_for_status()
        return r.json()
