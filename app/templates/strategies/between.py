import re


def _phrase_pattern(phrase: str) -> str:
    return re.escape(phrase).replace(r"\ ", r"\s+")


def find_between(lines_on_page: list[dict], config: dict) -> str | None:
    after = config.get("after")
    if not after:
        return None
    before = config.get("before")
    flags = re.IGNORECASE if config.get("ignore_case", True) else 0
    joined = "\n".join(ln["text"] for ln in lines_on_page)

    pat = _phrase_pattern(after) + r"\s*([\s\S]+?)"
    pat += r"\s*" + _phrase_pattern(before) if before else r"\s*\Z"

    m = re.search(pat, joined, flags)
    if not m:
        return None
    val = m.group(1).strip()
    if config.get("collapse_whitespace", True):
        val = re.sub(r"\s+", " ", val)
    for tok in config.get("skip_after", []):
        val = re.sub(rf"^{re.escape(tok)}\s+", "", val, flags=flags)
    val = val.strip()
    return val or None
