import gzip
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_clients.dataforseo import DataForSEOClient
from app.config import Settings
from app.models import ApiRequest, ApiResponseBlob, CacheEntry, CostLedger, ResearchRun, utcnow
from app.normalization import normalize_keyword, request_hash

ENDPOINT = "/v3/dataforseo_labs/google/keyword_overview/live"
TTL = timedelta(days=30)


@dataclass
class FoundationResult:
    run_id: int
    cache_hit: bool
    cost_usd: Decimal
    response: dict[str, Any]


def estimate_keyword_overview(keyword_count: int) -> Decimal:
    return Decimal("0.012") + Decimal(keyword_count) * Decimal("0.00012")


def actual_cost(response: dict[str, Any]) -> Decimal:
    return sum((Decimal(str(task.get("cost") or 0)) for task in response.get("tasks") or []), Decimal("0"))


def _unpack(blob: bytes) -> dict[str, Any]:
    return json.loads(gzip.decompress(blob).decode("utf-8"))


def keyword_overview_item(response: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first Keyword Overview item without assuming optional fields exist."""
    try:
        items = response["tasks"][0]["result"][0]["items"]
        return items[0] if items else None
    except (KeyError, IndexError, TypeError):
        return None


def keyword_difficulty(item: dict[str, Any] | None) -> int | float | None:
    """Return a supplied difficulty value, preserving a legitimate numeric zero."""
    if not item:
        return None
    properties = item.get("keyword_properties")
    if not isinstance(properties, dict):
        return None
    value = properties.get("keyword_difficulty")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def response_for_run(db: Session, run: ResearchRun) -> dict[str, Any] | None:
    """Load the persisted response for either an API run or a later cache-hit run."""
    if run.source == "api":
        blob = db.scalar(
            select(ApiResponseBlob)
            .join(ApiRequest, ApiResponseBlob.api_request_id == ApiRequest.id)
            .where(ApiRequest.run_id == run.id)
        )
    else:
        blob = db.scalar(
            select(ApiResponseBlob)
            .join(CacheEntry, CacheEntry.response_blob_id == ApiResponseBlob.id)
            .where(CacheEntry.key == run.cache_key)
        )
    return _unpack(blob.body_gzip) if blob else None


def keyword_overview(
    db: Session,
    settings: Settings,
    keyword: str,
    *,
    confirmed: bool,
    force_refresh: bool = False,
    client: DataForSEOClient | None = None,
) -> FoundationResult:
    normalized = normalize_keyword(keyword)
    if not normalized:
        raise ValueError("Keyword must not be empty.")
    payload = [{"keywords": [normalized], "location_code": 2276, "language_code": "de"}]
    key = request_hash(ENDPOINT, payload)

    if not force_refresh:
        cached = db.execute(
            select(CacheEntry, ApiResponseBlob)
            .join(ApiResponseBlob, CacheEntry.response_blob_id == ApiResponseBlob.id)
            .where(CacheEntry.key == key, CacheEntry.expires_at > utcnow())
        ).first()
        if cached:
            entry, blob = cached
            run = ResearchRun(
                function="keyword_overview_foundation",
                status="completed",
                source="cache",
                parameters_json=json.dumps(payload, ensure_ascii=False),
                cache_key=key,
                cache_hit=True,
                completed_at=utcnow(),
            )
            db.add(run)
            db.commit()
            return FoundationResult(run.id, True, Decimal("0"), _unpack(blob.body_gzip))

    estimate = estimate_keyword_overview(1)
    if not confirmed:
        raise PermissionError(f"Paid API request requires confirmation (estimate ${estimate:.5f}).")

    run = ResearchRun(
        function="keyword_overview_foundation",
        status="running",
        source="api",
        parameters_json=json.dumps(payload, ensure_ascii=False),
        cache_key=key,
    )
    db.add(run)
    db.flush()
    api_request = ApiRequest(
        run_id=run.id,
        endpoint=ENDPOINT,
        request_hash=key,
        status="running",
        estimated_cost_usd=estimate,
    )
    db.add(api_request)
    db.commit()

    try:
        response = (client or DataForSEOClient(settings)).post(ENDPOINT, payload)
        cost = actual_cost(response)
        task = (response.get("tasks") or [{}])[0]
        blob = ApiResponseBlob(
            api_request_id=api_request.id,
            body_gzip=gzip.compress(json.dumps(response, ensure_ascii=False).encode("utf-8")),
        )
        db.add(blob)
        db.flush()
        api_request.status = "completed"
        api_request.status_code = response.get("status_code")
        api_request.task_id = task.get("id")
        api_request.actual_cost_usd = cost
        run.status = "completed"
        run.completed_at = utcnow()
        db.add(CostLedger(
            run_id=run.id,
            api_request_id=api_request.id,
            task_id=task.get("id"),
            function=run.function,
            estimated_cost_usd=estimate,
            actual_cost_usd=cost,
        ))
        db.merge(CacheEntry(key=key, run_id=run.id, response_blob_id=blob.id, expires_at=utcnow() + TTL))
        db.commit()
        return FoundationResult(run.id, False, cost, response)
    except Exception as exc:
        run.status = "failed"
        run.completed_at = utcnow()
        api_request.status = "failed"
        api_request.error_message = str(exc)[:1000]
        db.commit()
        raise


def cost_total(db: Session) -> Decimal:
    value = db.scalar(select(func.coalesce(func.sum(CostLedger.actual_cost_usd), 0)))
    return Decimal(str(value))
