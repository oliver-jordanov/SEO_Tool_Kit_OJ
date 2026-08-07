import gzip
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_clients.dataforseo import DataForSEOClient
from app.config import Settings
from app.models import (ApiRequest, ApiResponseBlob, BacklinkItem,
    BacklinkReferringDomain, BacklinkSummary, CostLedger, ResearchRun, utcnow)
from app.normalization import request_hash
from app.security import redact
from app.services.foundation import actual_cost

RUN_TYPE = "backlink_explorer_v1"
ENDPOINTS = {
    "summary": "/v3/backlinks/summary/live",
    "referring_domains": "/v3/backlinks/referring_domains/live",
    "backlinks": "/v3/backlinks/backlinks/live",
}
VALID_LIMITS = {25, 50, 100}
VALID_MODES = {"as_is", "one_per_domain"}
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)


@dataclass
class BacklinkExplorerResult:
    run_id: int
    cost_usd: Decimal
    status: str


def normalize_target(value: str) -> tuple[str, str]:
    original = value.strip()
    if not original or any(c.isspace() for c in original):
        raise ValueError("Bitte ein gültiges Ziel eingeben.")
    parsed = urlsplit(original)
    if parsed.scheme:
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Seiten-URLs müssen vollständige HTTP- oder HTTPS-URLs sein.")
        return original, "url"
    if any(x in original for x in "/?#:@"):
        raise ValueError("Domains ohne Protokoll, Seiten als vollständige URL eingeben.")
    domain = original.lower().rstrip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    if not DOMAIN_RE.fullmatch(domain):
        raise ValueError("Das Ziel ist keine gültige Domain, Subdomain oder URL.")
    # DataForSEO distinguishes by the supplied host; for display we use a
    # conservative label (three or more labels means subdomain).
    kind = "subdomain" if len(domain.split(".")) > 2 else "domain"
    return domain, kind


def build_payloads(target: str, include_subdomains: bool, limit: int, mode: str):
    normalized, target_type = normalize_target(target)
    if limit not in VALID_LIMITS:
        raise ValueError("Limit muss 25, 50 oder 100 sein.")
    if mode not in VALID_MODES:
        raise ValueError("Ungültiger Gruppierungsmodus.")
    common = {"target": normalized, "include_subdomains": bool(include_subdomains)}
    return normalized, target_type, {
        "summary": [dict(common)],
        "referring_domains": [{**common, "limit": limit, "order_by": ["rank,desc"]}],
        "backlinks": [{**common, "limit": limit, "mode": mode, "order_by": ["domain_from_rank,desc"]}],
    }


def _result(response: dict[str, Any]) -> dict[str, Any]:
    try:
        return response["tasks"][0]["result"][0] or {}
    except (KeyError, IndexError, TypeError):
        return {}


def _value(data: dict[str, Any], *names: str):
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
    return None


def normalize_summary(response: dict[str, Any]) -> dict[str, Any]:
    r = _result(response)
    info = r.get("info") or {}
    return {
        "rank": _value(r, "rank"), "backlinks": _value(r, "backlinks"),
        "referring_domains": _value(r, "referring_domains"),
        "referring_main_domains": _value(r, "referring_main_domains"),
        "referring_pages": _value(r, "referring_pages"),
        "referring_ips": _value(r, "referring_ips", "referring ips"),
        "referring_subnets": _value(r, "referring_subnets", "referring subnets"),
        "dofollow": _value(r, "backlinks_dofollow"),
        "nofollow": _value(r, "backlinks_nofollow"),
        "new_backlinks": _value(r, "new_backlinks"),
        "lost_backlinks": _value(r, "lost_backlinks"),
        "spam_score": _value(r, "backlinks_spam_score") if _value(r, "backlinks_spam_score") is not None else _value(info, "target_spam_score"),
        "first_seen": _value(r, "first_seen"), "last_seen": _value(r, "last_seen", "last_visited"),
    }


def normalize_referring_domains(response: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for x in _result(response).get("items") or []:
        rows.append({"domain": _value(x, "domain"), "rank": _value(x, "rank"),
            "backlinks": _value(x, "backlinks"), "dofollow": _value(x, "backlinks_dofollow"),
            "nofollow": _value(x, "backlinks_nofollow"), "first_seen": _value(x, "first_seen"),
            "referring_pages": _value(x, "referring_pages"),
            "referring_ips": _value(x, "referring_ips", "referring ips"),
            "referring_subnets": _value(x, "referring_subnets", "referring subnets")})
    return rows


def normalize_backlinks(response: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for x in _result(response).get("items") or []:
        lost = _value(x, "lost_date")
        rows.append({"domain": _value(x, "domain_from"), "source_url": _value(x, "url_from"),
            "target_url": _value(x, "url_to"), "domain_rank": _value(x, "domain_from_rank"),
            "page_rank": _value(x, "page_from_rank", "rank"), "anchor": _value(x, "anchor"),
            "dofollow": _value(x, "dofollow"), "link_type": _value(x, "item_type"),
            "first_seen": _value(x, "first_seen"), "last_seen": _value(x, "last_seen"),
            "lost_date": lost, "is_lost": bool(_value(x, "is_lost") or lost),
            "title": _value(x, "page_from_title"), "language": _value(x, "page_from_language")})
    return rows


def data_for_run(db: Session, run_id: int):
    summary = db.scalar(select(BacklinkSummary).where(BacklinkSummary.run_id == run_id))
    domains = db.scalars(select(BacklinkReferringDomain).where(BacklinkReferringDomain.run_id == run_id).order_by(BacklinkReferringDomain.position)).all()
    links = db.scalars(select(BacklinkItem).where(BacklinkItem.run_id == run_id).order_by(BacklinkItem.position)).all()
    return (json.loads(summary.data_json) if summary else {},
        [json.loads(x.data_json) for x in domains], [json.loads(x.data_json) for x in links])


def requests_for_run(db: Session, run_id: int):
    return list(db.scalars(select(ApiRequest).where(ApiRequest.run_id == run_id).order_by(ApiRequest.id)).all())


def raw_responses_for_run(db: Session, run_id: int):
    import gzip as _gzip
    result = {}
    for req in requests_for_run(db, run_id):
        blob = db.scalar(select(ApiResponseBlob).where(ApiResponseBlob.api_request_id == req.id))
        result[req.endpoint] = json.loads(_gzip.decompress(blob.body_gzip)) if blob else None
    return result


def run_backlink_explorer(db: Session, settings: Settings, target: str, *, include_subdomains=True,
                          limit=100, mode="one_per_domain", confirmed=False, client=None):
    normalized, target_type, payloads = build_payloads(target, include_subdomains, limit, mode)
    if not confirmed:
        raise PermissionError("Bis zu drei kostenpflichtige API-Abrufe müssen bestätigt werden.")
    params = {"original_target": target.strip(), "target": normalized, "target_type": target_type,
        "include_subdomains": include_subdomains, "limit": limit, "mode": mode,
        "endpoints": list(ENDPOINTS.values())}
    run = ResearchRun(function=RUN_TYPE, status="running", source="api",
        parameters_json=json.dumps(params, ensure_ascii=False),
        cache_key=request_hash("|".join(ENDPOINTS.values()), [params]))
    db.add(run); db.flush()
    api_requests = {}
    for name, endpoint in ENDPOINTS.items():
        req = ApiRequest(run_id=run.id, endpoint=endpoint,
            request_hash=request_hash(endpoint, payloads[name]), status="pending")
        db.add(req); db.flush(); api_requests[name] = req
    db.commit()
    failures = 0
    total = Decimal("0")
    api = client or DataForSEOClient(settings)
    normalizers = {"summary": normalize_summary, "referring_domains": normalize_referring_domains,
        "backlinks": normalize_backlinks}
    for name, endpoint in ENDPOINTS.items():
        req = api_requests[name]; req.status = "running"; db.commit()
        try:
            response = redact(api.post(endpoint, payloads[name]))
            cost = actual_cost(response); total += cost
            task = (response.get("tasks") or [{}])[0]
            req.status = "completed"; req.task_id = task.get("id"); req.actual_cost_usd = cost
            req.status_code = task.get("status_code") or response.get("status_code")
            db.add(ApiResponseBlob(api_request_id=req.id, body_gzip=gzip.compress(json.dumps(response, ensure_ascii=False).encode())))
            data = normalizers[name](response)
            if name == "summary": db.add(BacklinkSummary(run_id=run.id, data_json=json.dumps(data, ensure_ascii=False)))
            elif name == "referring_domains": db.add_all(BacklinkReferringDomain(run_id=run.id, position=i, data_json=json.dumps(x, ensure_ascii=False)) for i, x in enumerate(data, 1))
            else: db.add_all(BacklinkItem(run_id=run.id, position=i, data_json=json.dumps(x, ensure_ascii=False)) for i, x in enumerate(data, 1))
            db.add(CostLedger(run_id=run.id, api_request_id=req.id, task_id=task.get("id"),
                function=RUN_TYPE, actual_cost_usd=cost))
            db.commit()
        except Exception as exc:
            failures += 1; req.status = "failed"; req.error_message = str(exc)[:1000]; db.commit()
    run.status = "completed" if failures == 0 else ("failed" if failures == 3 else "partial_failed")
    run.completed_at = utcnow(); db.commit()
    return BacklinkExplorerResult(run.id, total, run.status)
