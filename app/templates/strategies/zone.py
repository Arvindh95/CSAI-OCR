def _center(bbox):
    x, y, w, h = bbox
    return x + w / 2, y + h / 2


def find_in_zone(lines_on_page: list[dict], config: dict,
                 img_w: int | None = None, img_h: int | None = None) -> str | None:
    x = float(config["x"])
    y = float(config["y"])
    w = float(config["w"])
    h = float(config["h"])
    merge = bool(config.get("merge", True))

    if max(x, y, w, h) <= 1.0 and img_w and img_h:
        x *= img_w
        y *= img_h
        w *= img_w
        h *= img_h

    x2, y2 = x + w, y + h
    hits = []
    for ln in lines_on_page:
        if "bbox" not in ln:
            continue
        cx, cy = _center(ln["bbox"])
        if x <= cx <= x2 and y <= cy <= y2:
            hits.append(ln)
    if not hits:
        return None
    hits.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    if merge:
        return " ".join(l["text"] for l in hits)
    return hits[0]["text"]
