from app.templates.extractor import extract_with_template
from app.templates.post_process import apply_post_process
from app.templates.strategies.anchor import find_by_anchor
from app.templates.strategies.regex import find_by_regex
from app.templates.strategies.zone import find_in_zone


def L(text, x, y, w=80, h=20, page=0):
    return {"text": text, "confidence": 0.9, "page_index": page,
            "bbox": [x, y, w, h]}


def test_anchor_right():
    lines = [L("INVOICE NO", 10, 10), L("INV-123", 150, 10),
             L("TOTAL", 10, 50), L("99.50", 150, 50)]
    val = find_by_anchor(lines,
        {"labels": ["INVOICE NO"], "direction": "right", "max_distance_px": 200})
    assert val == "INV-123"


def test_anchor_below():
    lines = [L("DATE", 10, 10, 50, 20), L("2026-04-18", 10, 40, 100, 20)]
    val = find_by_anchor(lines,
        {"labels": ["DATE"], "direction": "below", "max_distance_px": 100})
    assert val == "2026-04-18"


def test_anchor_same_line_colon():
    lines = [L("Invoice No: INV-42", 10, 10)]
    val = find_by_anchor(lines,
        {"labels": ["Invoice No"], "direction": "same_line_colon"})
    assert val == "INV-42"


def test_anchor_label_case_insensitive_multi_label():
    lines = [L("NO. INVOIS", 10, 10, 90, 20), L("X-999", 120, 10)]
    val = find_by_anchor(lines,
        {"labels": ["INVOICE NO", "NO. INVOIS"], "direction": "right",
         "max_distance_px": 100})
    assert val == "X-999"


def test_anchor_missing_returns_none():
    lines = [L("Hello", 10, 10)]
    assert find_by_anchor(lines,
        {"labels": ["TOTAL"], "direction": "right"}) is None


def test_zone_absolute_coords_merges():
    lines = [L("line1", 105, 205, 60, 20), L("line2", 105, 230, 60, 20),
             L("outside", 400, 400, 60, 20)]
    val = find_in_zone(lines, {"x": 100, "y": 200, "w": 100, "h": 80, "merge": True})
    assert val == "line1 line2"


def test_zone_normalized_coords():
    lines = [L("hit", 600, 800, 100, 20)]
    val = find_in_zone(lines, {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.1},
                       img_w=1200, img_h=1600)
    assert val == "hit"


def test_zone_no_merge_returns_first():
    lines = [L("A", 10, 10, 50, 20), L("B", 10, 40, 50, 20)]
    val = find_in_zone(lines, {"x": 0, "y": 0, "w": 200, "h": 200, "merge": False})
    assert val == "A"


def test_zone_miss():
    lines = [L("A", 10, 10)]
    assert find_in_zone(lines, {"x": 500, "y": 500, "w": 50, "h": 50}) is None


def test_regex_group():
    lines = [L("Header", 0, 0), L("TOTAL: RM 1,234.50", 0, 30)]
    val = find_by_regex(lines, {"pattern": r"TOTAL:\s*(RM\s*[\d,.]+)", "group": 1})
    assert val == "RM 1,234.50"


def test_regex_no_match():
    lines = [L("nothing here", 0, 0)]
    assert find_by_regex(lines, {"pattern": r"\d{10}"}) is None


def test_post_process_date():
    assert apply_post_process("18/04/2026", "date") == "2026-04-18"
    assert apply_post_process("2026-04-18", "date") == "2026-04-18"
    assert apply_post_process("garbage", "date") is None


def test_post_process_number():
    assert apply_post_process("RM 1,234.50", "number") == 1234.50
    assert apply_post_process("-45.7", "number") == -45.7
    assert apply_post_process("abc", "number") is None


def test_post_process_misc():
    assert apply_post_process(" hi ", "trim") == "hi"
    assert apply_post_process("hi", "uppercase") == "HI"
    assert apply_post_process("Hi", "lowercase") == "hi"
    assert apply_post_process(None, "trim") is None
    assert apply_post_process("x", None) == "x"
    assert apply_post_process("x", "unknown_rule") == "x"


def test_extractor_multi_page_and_errors():
    lines = [
        L("INVOICE NO", 10, 10, page=0), L("INV-1", 150, 10, page=0),
        L("TOTAL", 10, 50, page=1), L("99.50", 150, 50, page=1),
    ]
    template = {
        "pages": [
            {"page_index": 0, "width": 1200, "height": 1600},
            {"page_index": 1, "width": 1200, "height": 1600},
        ],
        "fields": [
            {"name": "invoice_no", "page_index": 0, "strategy": "anchor",
             "config": {"labels": ["INVOICE NO"], "direction": "right"},
             "post_process": "trim", "required": True, "display_order": 1},
            {"name": "total", "page_index": 1, "strategy": "anchor",
             "config": {"labels": ["TOTAL"], "direction": "right"},
             "post_process": "number", "required": True, "display_order": 2},
            {"name": "missing_req", "page_index": 0, "strategy": "regex",
             "config": {"pattern": r"NEVER_MATCHES"},
             "post_process": None, "required": True, "display_order": 3},
            {"name": "optional_miss", "page_index": 0, "strategy": "regex",
             "config": {"pattern": r"NOPE"},
             "post_process": None, "required": False, "display_order": 4},
        ],
    }
    out = extract_with_template(lines, template)
    assert out["invoice_no"] == "INV-1"
    assert out["total"] == 99.5
    assert out["missing_req"] is None
    assert out["optional_miss"] is None
    assert "_errors" in out
    names_with_error = [list(e.keys())[0] for e in out["_errors"]]
    assert "missing_req" in names_with_error
    assert "optional_miss" not in names_with_error


def test_extractor_unknown_strategy_logged_in_errors():
    lines = [L("x", 0, 0)]
    template = {"pages": [{"page_index": 0, "width": 100, "height": 100}],
                "fields": [{"name": "f", "page_index": 0, "strategy": "bogus",
                            "config": {}, "post_process": None, "required": False,
                            "display_order": 0}]}
    out = extract_with_template(lines, template)
    assert out["f"] is None
    assert "_errors" in out
    assert "f" in list(out["_errors"][0].keys())


def test_extractor_display_order_respected():
    lines = [L("x", 0, 0)]
    template = {"pages": [{"page_index": 0}], "fields": [
        {"name": "b", "page_index": 0, "strategy": "regex",
         "config": {"pattern": "x"}, "post_process": None,
         "required": False, "display_order": 2},
        {"name": "a", "page_index": 0, "strategy": "regex",
         "config": {"pattern": "x"}, "post_process": None,
         "required": False, "display_order": 1},
    ]}
    out = extract_with_template(lines, template)
    keys = [k for k in out.keys() if k != "_errors"]
    assert keys == ["a", "b"]
