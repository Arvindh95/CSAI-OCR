import os
import re

os.environ.setdefault("PADDLE_PDX_CACHE_HOME", r"D:\docling\models\paddlex")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ["FLAGS_use_mkldnn"] = "0"


def get_ocr():
    from paddleocr import PaddleOCR
    return PaddleOCR(lang="en", enable_mkldnn=False)


def poly_to_xywh(poly) -> list[int]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    x, y = min(xs), min(ys)
    return [int(x), int(y), int(max(xs) - x), int(max(ys) - y)]


def extract_lines(ocr, image_path: str) -> list[dict]:
    result = ocr.predict(image_path)
    lines = []
    for page_index, page in enumerate(result):
        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        polys = page.get("rec_polys", []) or page.get("dt_polys", [])
        n = len(texts)
        polys_padded = list(polys) + [None] * max(0, n - len(polys))
        for text, score, poly in zip(texts, scores, polys_padded):
            if not text.strip():
                continue
            entry = {
                "text": text.strip(),
                "confidence": round(float(score), 3),
                "page_index": page_index,
            }
            if poly is not None:
                entry["bbox"] = poly_to_xywh(poly)
            lines.append(entry)
    return lines
