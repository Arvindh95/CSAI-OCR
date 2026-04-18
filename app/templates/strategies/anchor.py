import re


def _center(bbox):
    x, y, w, h = bbox
    return x + w / 2, y + h / 2


def _line_has_label(text: str, labels: list[str]) -> str | None:
    norm = text.strip().upper()
    for lab in labels:
        if lab.strip().upper() in norm:
            return lab
    return None


def _same_line_colon(text: str, labels: list[str]) -> str | None:
    for lab in labels:
        pat = re.compile(
            rf"{re.escape(lab.strip())}\s*[:\-]?\s*(.+)$",
            re.IGNORECASE,
        )
        m = pat.search(text)
        if m:
            value = m.group(1).strip()
            if value:
                return value
    return None


def find_by_anchor(lines_on_page: list[dict], config: dict) -> str | None:
    labels = config.get("labels", [])
    if not labels:
        return None
    direction = config.get("direction", "right")
    max_dist = float(config.get("max_distance_px", 200))

    if direction == "same_line_colon":
        for ln in lines_on_page:
            val = _same_line_colon(ln["text"], labels)
            if val:
                return val
        return None

    anchor = None
    for ln in lines_on_page:
        if _line_has_label(ln["text"], labels) and "bbox" in ln:
            anchor = ln
            break
    if anchor is None:
        return None

    ax, ay = _center(anchor["bbox"])
    ax_r = anchor["bbox"][0] + anchor["bbox"][2]
    ay_b = anchor["bbox"][1] + anchor["bbox"][3]

    candidates = []
    for ln in lines_on_page:
        if ln is anchor or "bbox" not in ln:
            continue
        bx, by = _center(ln["bbox"])
        if direction == "right":
            if bx < ax_r:
                continue
            if abs(by - ay) > anchor["bbox"][3]:
                continue
            dist = bx - ax_r
        elif direction == "below":
            if by < ay_b:
                continue
            if abs(bx - ax) > max_dist:
                continue
            dist = by - ay_b
        else:
            continue
        if dist > max_dist:
            continue
        candidates.append((dist, ln))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]["text"]
