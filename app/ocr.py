import os
import re

os.environ.setdefault("PADDLE_PDX_CACHE_HOME", r"D:\docling\models\paddlex")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ["FLAGS_use_mkldnn"] = "0"


def get_ocr():
    from paddleocr import PaddleOCR
    return PaddleOCR(lang="en", enable_mkldnn=False)


def extract_lines(ocr, image_path: str) -> list[dict]:
    result = ocr.predict(image_path)
    lines = []
    for page in result:
        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        for text, score in zip(texts, scores):
            if text.strip():
                lines.append({"text": text.strip(), "confidence": round(score, 3)})
    return lines
