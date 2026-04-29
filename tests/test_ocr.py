from app.ocr import extract_lines, poly_to_xywh


class _FakePage(dict):
    pass


class _FakeOCR:
    def __init__(self, pages):
        self._pages = pages

    def predict(self, path):
        return self._pages


def test_poly_to_xywh_axis_aligned():
    poly = [[10, 20], [110, 20], [110, 45], [10, 45]]
    assert poly_to_xywh(poly) == [10, 20, 100, 25]


def test_poly_to_xywh_rotated():
    poly = [[10, 20], [100, 25], [95, 60], [5, 55]]
    assert poly_to_xywh(poly) == [5, 20, 95, 40]


def test_extract_lines_single_page_with_bbox():
    pages = [_FakePage({
        "rec_texts": ["INVOICE", "NO: 123"],
        "rec_scores": [0.98, 0.91],
        "rec_polys": [
            [[10, 10], [100, 10], [100, 30], [10, 30]],
            [[10, 40], [120, 40], [120, 60], [10, 60]],
        ],
    })]
    lines = extract_lines(_FakeOCR(pages), "x.png")
    assert len(lines) == 2
    assert lines[0] == {
        "text": "INVOICE", "confidence": 0.98,
        "page_index": 0, "bbox": [10, 10, 90, 20],
    }
    assert lines[1]["page_index"] == 0
    assert lines[1]["bbox"] == [10, 40, 110, 20]


def test_extract_lines_multi_page_page_index_set():
    pages = [
        _FakePage({
            "rec_texts": ["PAGE1"],
            "rec_scores": [0.9],
            "rec_polys": [[[0, 0], [50, 0], [50, 20], [0, 20]]],
        }),
        _FakePage({
            "rec_texts": ["PAGE2"],
            "rec_scores": [0.8],
            "rec_polys": [[[0, 0], [60, 0], [60, 20], [0, 20]]],
        }),
    ]
    lines = extract_lines(_FakeOCR(pages), "x.tif")
    assert [l["page_index"] for l in lines] == [0, 1]
    assert [l["text"] for l in lines] == ["PAGE1", "PAGE2"]


def test_extract_lines_skips_blank_text():
    pages = [_FakePage({
        "rec_texts": ["real", "   ", ""],
        "rec_scores": [0.9, 0.5, 0.1],
        "rec_polys": [
            [[0, 0], [10, 0], [10, 10], [0, 10]],
            [[0, 20], [10, 20], [10, 30], [0, 30]],
            [[0, 40], [10, 40], [10, 50], [0, 50]],
        ],
    })]
    lines = extract_lines(_FakeOCR(pages), "x.png")
    assert len(lines) == 1
    assert lines[0]["text"] == "real"


def test_extract_lines_handles_missing_polys():
    pages = [_FakePage({
        "rec_texts": ["no_bbox"],
        "rec_scores": [0.7],
    })]
    lines = extract_lines(_FakeOCR(pages), "x.png")
    assert len(lines) == 1
    assert "bbox" not in lines[0]
    assert lines[0]["text"] == "no_bbox"
    assert lines[0]["page_index"] == 0


def test_extract_lines_falls_back_to_dt_polys():
    pages = [_FakePage({
        "rec_texts": ["hello"],
        "rec_scores": [0.9],
        "dt_polys": [[[5, 5], [25, 5], [25, 15], [5, 15]]],
    })]
    lines = extract_lines(_FakeOCR(pages), "x.png")
    assert lines[0]["bbox"] == [5, 5, 20, 10]
