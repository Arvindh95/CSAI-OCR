from app.templates.extractor import extract_with_template
from app.templates.strategies.between import find_between


def L(text, page=0):
    return {"text": text, "confidence": 0.9, "page_index": page, "bbox": [0, 0, 0, 0]}


def test_between_basic():
    lines = [L("preamble"), L("START anchor"), L("captured value"), L("END anchor")]
    val = find_between(lines, {"after": "START anchor", "before": "END anchor"})
    assert val == "captured value"


def test_between_multiline_capture():
    lines = [
        L("di sini dan tempat utama perniagaannya NO. 49, JALAN KHABAR HIDUP"),
        L("42, TAMAN PERUNDING 5, 41000, KLANG, NEGERI SEMBILAN."),
        L("Jenis Perniagaan"),
        L("MENJUAL DAN MEMBEKAL"),
    ]
    val = find_between(lines, {
        "after": "tempat utama perniagaannya",
        "before": "Jenis Perniagaan",
    })
    assert "NO. 49" in val
    assert "NEGERI SEMBILAN." in val
    assert "Jenis" not in val


def test_between_skip_after_token():
    lines = [
        L("perniagaannya di NO. 85, JLN MERANTI 12, TAMAN RINTING"),
        L("81750 MASAI JOHOR."),
        L("Jenis Perniagaan"),
    ]
    val = find_between(lines, {
        "after": "perniagaannya",
        "before": "Jenis Perniagaan",
        "skip_after": ["di"],
    })
    assert val.startswith("NO. 85")


def test_between_no_before_captures_to_end():
    lines = [L("header"), L("START"), L("line1"), L("line2")]
    val = find_between(lines, {"after": "START"})
    assert val == "line1\nline2"


def test_between_anchor_split_across_lines():
    # OCR splits the after-phrase across two lines; \s+ tolerance must match.
    lines = [L("tempat utama"), L("perniagaannya value here"), L("Jenis Perniagaan")]
    val = find_between(lines, {
        "after": "tempat utama perniagaannya",
        "before": "Jenis Perniagaan",
    })
    assert val == "value here"


def test_between_missing_after_returns_none():
    lines = [L("nothing here")]
    val = find_between(lines, {"after": "MISSING ANCHOR"})
    assert val is None


def test_between_empty_capture_returns_none():
    lines = [L("STARTEND")]
    val = find_between(lines, {"after": "START", "before": "END"})
    assert val is None


def test_between_case_insensitive_default():
    lines = [L("AFTER value BEFORE")]
    val = find_between(lines, {"after": "after", "before": "before"})
    assert val == "value"


def test_between_case_sensitive_opt_in():
    lines = [L("AFTER value BEFORE")]
    val = find_between(lines, {"after": "after", "before": "before",
                                "ignore_case": False})
    assert val is None


def test_extractor_dispatches_between():
    template = {
        "pages": [{"page_index": 0, "width": 1000, "height": 1000}],
        "fields": [{
            "name": "addr",
            "page_index": 0,
            "strategy": "between",
            "config": {"after": "perniagaannya", "before": "Jenis"},
            "post_process": "trim",
            "required": True,
        }],
    }
    lines = [L("perniagaannya NO. 49, JALAN KHABAR"), L("HIDUP 42, KLANG."), L("Jenis Perniagaan")]
    out = extract_with_template(lines, template)
    assert out["addr"].startswith("NO. 49")
    assert "_errors" not in out
