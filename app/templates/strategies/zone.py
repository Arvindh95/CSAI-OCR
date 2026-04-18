def _overlap_ratio(line_bbox, zone):
    lx, ly, lw, lh = line_bbox
    zx1, zy1, zx2, zy2 = zone
    ix1 = max(lx, zx1)
    iy1 = max(ly, zy1)
    ix2 = min(lx + lw, zx2)
    iy2 = min(ly + lh, zy2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    line_area = max(lw * lh, 1)
    return inter / line_area


def find_in_zone(lines_on_page: list[dict], config: dict,
                 img_w: int | None = None, img_h: int | None = None) -> str | None:
    x = float(config["x"])
    y = float(config["y"])
    w = float(config["w"])
    h = float(config["h"])
    merge = bool(config.get("merge", True))
    min_overlap = float(config.get("min_overlap", 0.3))

    if max(x, y, w, h) <= 1.0 and img_w and img_h:
        x *= img_w
        y *= img_h
        w *= img_w
        h *= img_h

    zone = (x, y, x + w, y + h)
    hits = []
    for ln in lines_on_page:
        if "bbox" not in ln:
            continue
        if _overlap_ratio(ln["bbox"], zone) >= min_overlap:
            hits.append(ln)
    if not hits:
        return None
    hits.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    if merge:
        return " ".join(l["text"] for l in hits)
    return hits[0]["text"]
