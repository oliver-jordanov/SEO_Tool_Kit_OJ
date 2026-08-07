import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base, get_db
from app.main import app
from app.models import ApiRequest, CostLedger, ResearchRun
from app.security import redact
from app.services.backlink_explorer import (ENDPOINTS, build_payloads, data_for_run,
    normalize_backlinks, normalize_referring_domains, normalize_summary, normalize_target,
    run_backlink_explorer)


def settings():
    return Settings(dataforseo_login="user", dataforseo_password="secret", database_url="sqlite:///:memory:")


def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine)


def response(name, cost=0.02):
    items = {
        "summary": [{"rank": 0, "backlinks": 12, "referring_domains": 3,
            "referring_main_domains": 2, "referring_pages": 4, "referring_ips": 0,
            "referring_subnets": 1, "backlinks_spam_score": 0, "info": {"target_spam_score": 7}}],
        "referring_domains": [{"items": [{"domain": "example.org", "rank": 88,
            "backlinks": 2, "first_seen": "2025-01-01", "referring_pages": 1,
            "referring ips": 0, "referring subnets": 1}]}],
        "backlinks": [{"items": [{"domain_from": "example.org",
            "url_from": "https://example.org/a", "url_to": "https://target.test/",
            "domain_from_rank": 88, "page_from_rank": 0, "anchor": "<script>alert(1)</script>",
            "dofollow": False, "item_type": "anchor", "is_lost": True,
            "first_seen": "2025-01-01", "last_seen": "2025-02-01",
            "page_from_title": "A & B", "page_from_language": "de"}]}],
    }[name]
    return {"status_code": 20000, "tasks": [{"id": f"task-{name}", "status_code": 20000,
        "cost": cost, "result": items}], "debug": {"Authorization": "secret"}}


class FakeClient:
    def __init__(self, fail=None): self.fail = fail; self.calls = []
    def post(self, endpoint, payload):
        self.calls.append((endpoint, payload))
        name = next(k for k, v in ENDPOINTS.items() if v == endpoint)
        if name == self.fail: raise RuntimeError("redigierter Testfehler")
        return response(name)


@pytest.mark.parametrize("raw, expected, kind", [
    ("jodano.de", "jodano.de", "domain"),
    ("www.Jodano.de", "jodano.de", "domain"),
    ("blog.jodano.de", "blog.jodano.de", "subdomain"),
    ("https://www.jodano.de/a?x=1", "https://www.jodano.de/a?x=1", "url"),
])
def test_target_normalization(raw, expected, kind):
    assert normalize_target(raw) == (expected, kind)


@pytest.mark.parametrize("raw", ["", "not a domain", "ftp://example.com/a", "example.com/path"])
def test_invalid_targets_are_rejected(raw):
    with pytest.raises(ValueError): normalize_target(raw)


@pytest.mark.parametrize("mode", ["as_is", "one_per_domain"])
@pytest.mark.parametrize("limit", [25, 50, 100])
def test_payloads_for_all_endpoints(mode, limit):
    target, kind, payloads = build_payloads("www.example.com", False, limit, mode)
    assert target == "example.com" and kind == "domain"
    assert payloads["summary"] == [{"target": "example.com", "include_subdomains": False}]
    assert payloads["referring_domains"][0] == {"target": "example.com",
        "include_subdomains": False, "limit": limit, "order_by": ["rank,desc"]}
    assert payloads["backlinks"][0]["mode"] == mode
    assert payloads["backlinks"][0]["limit"] == limit


def test_normalizers_keep_zero_missing_follow_and_lost():
    summary = normalize_summary(response("summary"))
    assert summary["rank"] == 0 and summary["referring_ips"] == 0
    assert summary["dofollow"] is None and summary["spam_score"] == 0
    domains = normalize_referring_domains(response("referring_domains"))
    assert domains[0]["rank"] == 88 and domains[0]["referring_ips"] == 0
    links = normalize_backlinks(response("backlinks"))
    assert links[0]["dofollow"] is False and links[0]["is_lost"] is True
    assert links[0]["page_rank"] == 0 and links[0]["link_type"] == "anchor"


def test_three_requests_persist_costs_raw_and_normalized_data():
    db = session(); client = FakeClient()
    result = run_backlink_explorer(db, settings(), "example.com", confirmed=True, client=client)
    assert result.status == "completed" and result.cost_usd == Decimal("0.06")
    run = db.get(ResearchRun, result.run_id)
    assert run.function == "backlink_explorer_v1"
    assert len(db.scalars(select(ApiRequest)).all()) == 3
    assert sum(db.scalars(select(CostLedger.actual_cost_usd)).all()) == Decimal("0.060000")
    summary, domains, links = data_for_run(db, run.id)
    assert summary["backlinks"] == 12 and domains[0]["domain"] == "example.org"
    assert links[0]["anchor"].startswith("<script>")


def test_partial_failure_keeps_successful_sections_and_never_retries():
    db = session(); client = FakeClient(fail="referring_domains")
    result = run_backlink_explorer(db, settings(), "example.com", confirmed=True, client=client)
    assert result.status == "partial_failed" and len(client.calls) == 3
    requests = db.scalars(select(ApiRequest).order_by(ApiRequest.id)).all()
    assert [x.status for x in requests] == ["completed", "failed", "completed"]
    summary, domains, links = data_for_run(db, result.run_id)
    assert summary and not domains and links


def test_confirmation_prevents_any_run_or_request():
    db = session(); client = FakeClient()
    with pytest.raises(PermissionError):
        run_backlink_explorer(db, settings(), "example.com", confirmed=False, client=client)
    assert not client.calls and db.scalar(select(ResearchRun)) is None


def test_redaction_is_recursive():
    assert redact({"password": "x", "nested": [{"token": "y"}]}) == {
        "password": "[REDACTED]", "nested": [{"token": "[REDACTED]"}]}


def test_saved_run_page_escapes_external_text_and_performs_no_api_call(monkeypatch):
    db = session(); result = run_backlink_explorer(db, settings(), "example.com",
        confirmed=True, client=FakeClient())
    def override_db(): yield db
    app.dependency_overrides[get_db] = override_db
    try:
        page = TestClient(app).get(f"/runs/{result.run_id}")
    finally:
        app.dependency_overrides.clear()
    assert page.status_code == 200
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
    assert "<script>alert(1)</script>" not in page.text
