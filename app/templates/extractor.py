from app.templates.post_process import apply_post_process
from app.templates.strategies.anchor import find_by_anchor
from app.templates.strategies.regex import find_by_regex
from app.templates.strategies.zone import find_in_zone

_STRATEGIES = {"anchor", "zone", "regex"}


def extract_with_template(lines: list[dict], template: dict) -> dict:
    pages_by_idx = {p["page_index"]: p for p in template.get("pages", [])}
    fields = sorted(template.get("fields", []),
                    key=lambda f: (f.get("display_order", 0), f.get("name", "")))

    by_page: dict[int, list[dict]] = {}
    for ln in lines:
        by_page.setdefault(ln.get("page_index", 0), []).append(ln)

    out: dict = {}
    errors: list[dict] = []

    for field in fields:
        name = field["name"]
        strategy = field["strategy"]
        page_idx = int(field.get("page_index", 0))
        page_lines = by_page.get(page_idx, [])
        raw: str | None = None
        try:
            if strategy == "anchor":
                raw = find_by_anchor(page_lines, field["config"])
            elif strategy == "zone":
                page_meta = pages_by_idx.get(page_idx, {})
                raw = find_in_zone(
                    page_lines, field["config"],
                    img_w=page_meta.get("width"),
                    img_h=page_meta.get("height"),
                )
            elif strategy == "regex":
                raw = find_by_regex(page_lines, field["config"])
            else:
                raise ValueError(f"unknown strategy: {strategy}")
            value = apply_post_process(raw, field.get("post_process"))
        except Exception as e:
            value = None
            errors.append({name: f"extraction_error: {e}"})

        out[name] = value
        if value in (None, "") and field.get("required"):
            errors.append({name: "required_field_missing"})

    if errors:
        out["_errors"] = errors
    return out
