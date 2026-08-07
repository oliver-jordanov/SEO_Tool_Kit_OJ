import hashlib
import json
import re
from typing import Any
from urllib.parse import urlsplit

MAPPER_VERSION = "foundation-v1"


def normalize_domain(value: str) -> str:
    raw = value.strip().lower()
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    return (parsed.hostname or "").removeprefix("www.").rstrip(".")


def normalize_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonical_request(endpoint: str, payload: Any) -> str:
    document = {"endpoint": endpoint, "mapper_version": MAPPER_VERSION, "payload": payload}
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(endpoint: str, payload: Any) -> str:
    return hashlib.sha256(canonical_request(endpoint, payload).encode("utf-8")).hexdigest()

