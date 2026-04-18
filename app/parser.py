import re
from datetime import datetime


def clean(text: str) -> str:
    return re.sub(r"^[\s:]+", "", text).strip()


def parse_ssm(lines: list[dict]) -> dict:
    texts = [l["text"] for l in lines]
    fields = {}

    for i, text in enumerate(texts):
        t = text.upper()

        # ── Company name ──────────────────────────────────────
        # Format 1 (MyData): label "NAMA PERNIAGAAN"
        if "NAMA PERNIAGAAN" in t and "NO" not in t and "ALAMAT" not in t:
            if i + 1 < len(texts):
                fields["company_name"] = clean(texts[i + 1])

        # Format 2 (Borang D): after "dijalankan dengan nama"
        if "DIJALANKAN DENGAN NAMA" in t:
            if i + 1 < len(texts):
                fields["company_name"] = clean(texts[i + 1])

        # ── Registration number ───────────────────────────────
        # Format 1: label "NO PENDAFTARAN PERNIAGAAN"
        if "NO PENDAFTARAN PERNIAGAAN" in t or "NO. PENDAFTARAN" in t:
            if i + 1 < len(texts):
                fields["reg_no"] = clean(texts[i + 1])
            colon_val = re.search(r":(.+)", text)
            if colon_val and len(colon_val.group(1).strip()) > 2:
                fields["reg_no"] = colon_val.group(1).strip()

        # ── Address ───────────────────────────────────────────
        if "ALAMAT UTAMA PERNIAGAAN" in t:
            addr_parts = []
            for j in range(i + 1, min(i + 5, len(texts))):
                val = clean(texts[j])
                if any(kw in texts[j].upper() for kw in ["BENTUK", "TARIKH", "STATUS", "JENIS"]):
                    break
                if val:
                    addr_parts.append(val)
            fields["address"] = ", ".join(addr_parts)

        # ── Business type ─────────────────────────────────────
        if "BENTUK PERNIAGAAN" in t:
            if i + 1 < len(texts):
                fields["business_type"] = clean(texts[i + 1])

        # ── Status ────────────────────────────────────────────
        if t.strip() == "STATUS" or (t.startswith("STATUS") and len(t) < 20):
            if i + 1 < len(texts):
                fields["status"] = clean(texts[i + 1])

        # ── Dates ─────────────────────────────────────────────
        if "TARIKH LUPUT" in t:
            if i + 1 < len(texts):
                fields["expiry_date"] = clean(texts[i + 1])

        if "TARIKH PENDAFTARAN" in t and "LUPUT" not in t:
            if i + 1 < len(texts):
                fields["reg_date"] = clean(texts[i + 1])

    return fields


def check_expiry(fields: dict) -> dict:
    expiry_str = fields.get("expiry_date", "")
    if not expiry_str:
        return {"expiry_date": None, "expired": None, "days": None}

    # try common date formats from OCR
    formats = ["%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"]
    parsed = None
    for fmt in formats:
        try:
            parsed = datetime.strptime(expiry_str.strip(), fmt)
            break
        except ValueError:
            continue

    if not parsed:
        return {"expiry_date": expiry_str, "expired": None, "days": None, "note": "unrecognised date format"}

    today = datetime.today()
    days = (parsed - today).days
    return {
        "expiry_date": expiry_str,
        "expired": days < 0,
        "days": abs(days),
        "note": f"Expired {abs(days)} days ago" if days < 0 else f"Valid for {days} more days"
    }


def verify_fields(fields: dict, name: str | None, reg_no: str | None) -> dict:
    results = {}

    if name and name.strip():
        extracted = fields.get("company_name", "")
        match = name.strip().upper() == extracted.strip().upper()
        results["company_name"] = {
            "input": name.strip(),
            "extracted": extracted,
            "match": match
        }

    if reg_no and reg_no.strip():
        extracted = fields.get("reg_no", "")
        match = reg_no.strip().upper() == extracted.strip().upper()
        results["reg_no"] = {
            "input": reg_no.strip(),
            "extracted": extracted,
            "match": match
        }

    return results
