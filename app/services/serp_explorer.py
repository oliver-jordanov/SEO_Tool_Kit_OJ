import gzip
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_clients.dataforseo import DataForSEOClient
from app.config import Settings
from app.models import (
    ApiRequest,
    ApiResponseBlob,
    CostLedger,
    ResearchRun,
    SerpFeature,
    SerpOrganicResult,
    utcnow,
)
from app.normalization import normalize_domain, normalize_keyword, request_hash
from app.security import redact
from app.services.foundation import actual_cost

ENDPOINT = "/v3/serp/google/organic/live/advanced"
RUN_TYPE = "serp_explorer_v1"
VALID_DEVICES = {"desktop", "mobile"}
VALID_DEPTHS = {10, 100}


@dataclass
class SerpExplorerResult:
    run_id: int
    cost_usd: Decimal
    response: dict[str, Any]


def build_payload(keyword: str, location_code: int, language_code: str,
                  device: str, depth: int) -> list[dict[str, Any]]:
    keyword = normalize_keyword(keyword)
    language_code = language_code.strip().lower()
    device = device.strip().lower()
    if not keyword:
        raise ValueError("Keyword darf nicht leer sein.")
    if location_code <= 0:
        raise ValueError("Der Location-Code muss eine positive Zahl sein.")
    if not language_code:
        raise ValueError("Der Sprachcode darf nicht leer sein.")
    if device not in VALID_DEVICES:
        raise ValueError("Gerät muss Desktop oder Mobile sein.")
    if depth not in VALID_DEPTHS:
        raise ValueError("Ergebnistiefe muss Top 10 oder Top 100 sein.")
    return [{
        "keyword": keyword,
        "location_code": location_code,
        "language_code": language_code,
        "device": device,
        "depth": depth,
    }]


def estimate_serp_cost(depth: int) -> Decimal:
    if depth not in VALID_DEPTHS:
        raise ValueError("Ergebnistiefe muss Top 10 oder Top 100 sein.")
    return Decimal("0.002") * (Decimal("1") if depth == 10 else Decimal("10"))


def _result(response: dict[str, Any]) -> dict[str, Any]:
    try:
        return response["tasks"][0]["result"][0] or {}
    except (KeyError, IndexError, TypeError):
        return {}


def normalize_serp(response: dict[str, Any], own_domain: str = "") -> tuple[list[dict[str, Any]], list[str]]:
    own = normalize_domain(own_domain) if own_domain else ""
    organic: list[dict[str, Any]] = []
    features: list[str] = []
    for item in _result(response).get("items") or []:
        item_type = str(item.get("type") or "unknown")
        if item_type != "organic":
            if item_type not in features:
                features.append(item_type)
            continue
        url = str(item.get("url") or "")
        domain = normalize_domain(str(item.get("domain") or urlsplit(url).hostname or ""))
        organic.append({
            "organic_position": int(item.get("rank_group") or len(organic) + 1),
            "serp_position": int(item.get("rank_absolute") or 0),
            "domain": domain,
            "url": url,
            "title": str(item.get("title") or ""),
            "snippet": str(item.get("description") or ""),
            "breadcrumb": str(item.get("breadcrumb") or ""),
            "is_own_domain": bool(own and (domain == own or domain.endswith("." + own))),
        })
    return organic, features


def serp_data_for_run(db: Session, run_id: int) -> tuple[list[SerpOrganicResult], list[str]]:
    rows = db.scalars(select(SerpOrganicResult).where(
        SerpOrganicResult.run_id == run_id).order_by(SerpOrganicResult.organic_position)).all()
    features = db.scalars(select(SerpFeature.feature).where(
        SerpFeature.run_id == run_id).order_by(SerpFeature.feature)).all()
    return list(rows), list(features)


def serp_request_for_run(db: Session, run_id: int) -> ApiRequest | None:
    return db.scalar(select(ApiRequest).where(ApiRequest.run_id == run_id))


def run_serp_explorer(db: Session, settings: Settings, keyword: str, *,
                      location_code: int, language_code: str, device: str,
                      depth: int, own_domain: str = "", confirmed: bool,
                      client: DataForSEOClient | None = None) -> SerpExplorerResult:
    payload = build_payload(keyword, location_code, language_code, device, depth)
    own = normalize_domain(own_domain) if own_domain else ""
    parameters = {**payload[0], "own_domain": own}
    key = request_hash(ENDPOINT, payload)
    estimate = estimate_serp_cost(depth)
    if not confirmed:
        raise PermissionError(f"Kostenpflichtiger API-Abruf muss bestätigt werden (Schätzung ${estimate:.3f}).")

    run = ResearchRun(function=RUN_TYPE, status="running", source="api",
                      parameters_json=json.dumps(parameters, ensure_ascii=False), cache_key=key)
    db.add(run)
    db.flush()
    api_request = ApiRequest(run_id=run.id, endpoint=ENDPOINT, request_hash=key,
                             status="running", estimated_cost_usd=estimate)
    db.add(api_request)
    db.commit()
    try:
        response = redact((client or DataForSEOClient(settings)).post(ENDPOINT, payload))
        cost = actual_cost(response)
        task = (response.get("tasks") or [{}])[0]
        organic, features = normalize_serp(response, own)
        blob = ApiResponseBlob(api_request_id=api_request.id, body_gzip=gzip.compress(
            json.dumps(response, ensure_ascii=False).encode("utf-8")))
        db.add(blob)
        db.add_all(SerpOrganicResult(run_id=run.id, **row) for row in organic)
        db.add_all(SerpFeature(run_id=run.id, feature=feature) for feature in features)
        api_request.status = "completed"
        api_request.status_code = response.get("status_code")
        api_request.task_id = task.get("id")
        api_request.actual_cost_usd = cost
        run.status = "completed"
        run.completed_at = utcnow()
        db.add(CostLedger(run_id=run.id, api_request_id=api_request.id,
                          task_id=task.get("id"), function=RUN_TYPE,
                          estimated_cost_usd=estimate, actual_cost_usd=cost))
        db.commit()
        return SerpExplorerResult(run.id, cost, response)
    except Exception as exc:
        run.status = "failed"
        run.completed_at = utcnow()
        api_request.status = "failed"
        api_request.error_message = str(exc)[:1000]
        db.commit()
        raise RuntimeError(f"SERP-Abfrage fehlgeschlagen. Run {run.id} wurde als fehlgeschlagen gespeichert: {exc}") from exc
