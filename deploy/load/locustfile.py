import io
import os
import random

from locust import HttpUser, between, task
from PIL import Image, ImageDraw


def _sample_image() -> bytes:
    img = Image.new("RGB", (800, 600), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 40), f"INVOICE NO INV-{random.randint(1000, 9999)}", fill="black")
    d.text((40, 100), "DATE 2026-04-18", fill="black")
    d.text((40, 160), f"TOTAL: RM {random.randint(100, 9999)}.{random.randint(10, 99)}",
           fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class OCRUser(HttpUser):
    wait_time = between(3, 6)
    api_key = os.environ["CSAI_API_KEY"]

    @task(4)
    def submit_plain(self):
        files = {"file": ("invoice.png", _sample_image(), "image/png")}
        self.client.post(
            "/api/v1/ocr",
            files=files,
            headers={"X-API-Key": self.api_key},
            name="/api/v1/ocr",
        )

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
