import os

from prometheus_client import start_http_server
from redis import Redis
from rq import Queue, Worker

from app import metrics  # noqa: F401 — ensures counter objects are registered


def main() -> None:
    start_http_server(8004, addr="127.0.0.1")
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    r = Redis.from_url(redis_url)
    queue = Queue("csai-ocr", connection=r)
    Worker([queue], connection=r).work()


if __name__ == "__main__":
    main()
