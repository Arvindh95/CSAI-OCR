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


import re


def _apply_extract(text: str, config: dict) -> str | None:
    pattern = config.get("extract_regex")
    if pattern:
        m = re.search(pattern, text)
        if not m:
            return None
        return m.group(1) if m.groups() else m.group(0)

    word_index = config.get("word_index")
    if word_index is not None:
        words = text.split()
        try:
            return words[int(word_index)]
        except (IndexError, ValueError):
            return None

    word_slice = config.get("word_slice")
    if word_slice is not None:
        words = text.split()
        try:
            if isinstance(word_slice, (list, tuple)) and len(word_slice) == 2:
                a, b = int(word_slice[0]), int(word_slice[1])
                return " ".join(words[a:b])
        except (IndexError, ValueError):
            return None
    return text


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
    merged = " ".join(l["text"] for l in hits) if merge else hits[0]["text"]
    return _apply_extract(merged, config)
