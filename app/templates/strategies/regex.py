import re


def find_by_regex(lines_on_page: list[dict], config: dict) -> str | None:
    pattern = config.get("pattern")
    if not pattern:
        return None
    group = int(config.get("group", 0))
    flags = re.IGNORECASE if config.get("ignore_case", True) else 0
    joined = "\n".join(ln["text"] for ln in lines_on_page)
    m = re.search(pattern, joined, flags)
    if not m:
        return None
    try:
        return m.group(group)
    except IndexError:
        return None
