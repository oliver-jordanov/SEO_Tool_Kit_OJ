from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api_clients.dataforseo import DataForSEOClient
from app.config import Settings
from app.db import Base
from app.models import ApiRequest, CostLedger, ResearchRun, SerpFeature, SerpOrganicResult
from app.services.foundation import response_for_run
from app.services.serp_explorer import (
    ENDPOINT, build_payload, estimate_serp_cost, normalize_serp, run_serp_explorer,
)


def settings():
    return Settings(dataforseo_login="user", dataforseo_password="secret", database_url="sqlite:///:memory:")


def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def response(status=20000):
    return {"status_code": 20000, "tasks": [{"id": "serp-task-1", "status_code": status,
        "status_message": "Ok" if status == 20000 else "Invalid request", "cost": 0.002,
        "result": [{"items": [
            {"type": "featured_snippet", "rank_group": 1, "rank_absolute": 1},
            {"type": "organic", "rank_group": 1, "rank_absolute": 2,
             "domain": "www.example.com", "url": "https://www.example.com/page",
             "title": "Example", "description": "Snippet", "breadcrumb": "Home > Page"},
            {"type": "people_also_ask", "rank_group": 2, "rank_absolute": 3},
        ]}]}]}


def mock_client(data):
    return DataForSEOClient(settings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=data)))


def test_payload_maps_device_and_depth_exactly():
    assert build_payload("  Test  Keyword ", 2276, "DE", "mobile", 100) == [{
        "keyword": "Test Keyword", "location_code": 2276, "language_code": "de",
        "device": "mobile", "depth": 100,
    }]
    with pytest.raises(ValueError):
        build_payload("test", 2276, "de", "tablet", 10)
    with pytest.raises(ValueError):
        build_payload("test", 2276, "de", "desktop", 50)


def test_cost_estimate_and_actual_cost_are_kept_separate():
    assert estimate_serp_cost(10) == Decimal("0.002")
    assert estimate_serp_cost(100) == Decimal("0.020")
    db = session()
    result = run_serp_explorer(db, settings(), "test", location_code=2276,
        language_code="de", device="desktop", depth=100, confirmed=True,
        client=mock_client(response()))
    request = db.scalar(select(ApiRequest))
    assert request.endpoint == ENDPOINT
    assert request.estimated_cost_usd == Decimal("0.020000")
    assert request.actual_cost_usd == Decimal("0.002000")
    assert result.cost_usd == Decimal("0.002")


def test_normalization_features_and_subdomain_highlighting():
    rows, features = normalize_serp(response(), "example.com")
    assert features == ["featured_snippet", "people_also_ask"]
    assert rows[0] == {"organic_position": 1, "serp_position": 2,
        "domain": "example.com", "url": "https://www.example.com/page",
        "title": "Example", "snippet": "Snippet", "breadcrumb": "Home > Page",
        "is_own_domain": True}
    other, _ = normalize_serp(response(), "not-example.com")
    assert other[0]["is_own_domain"] is False


def test_confirmation_blocks_request_without_creating_run():
    db = session()
    with pytest.raises(PermissionError):
        run_serp_explorer(db, settings(), "test", location_code=2276,
            language_code="de", device="desktop", depth=10, confirmed=False,
            client=mock_client(response()))
    assert db.scalar(select(ResearchRun)) is None


def test_success_persists_normalized_data_task_cost_and_redacted_raw_response():
    db = session()
    data = response()
    data["debug"] = {"Authorization": "Basic secret", "password": "secret"}
    result = run_serp_explorer(db, settings(), "test", location_code=2276,
        language_code="de", device="desktop", depth=10, own_domain="example.com",
        confirmed=True, client=mock_client(data))
    run = db.get(ResearchRun, result.run_id)
    request = db.scalar(select(ApiRequest))
    raw = response_for_run(db, run)
    assert run.function == "serp_explorer_v1" and run.status == "completed"
    assert request.task_id == "serp-task-1"
    assert db.scalar(select(CostLedger.actual_cost_usd)) == Decimal("0.002000")
    assert db.scalar(select(SerpOrganicResult)).is_own_domain is True
    assert set(db.scalars(select(SerpFeature.feature)).all()) == {"featured_snippet", "people_also_ask"}
    assert raw["debug"] == {"Authorization": "[REDACTED]", "password": "[REDACTED]"}


def test_api_error_creates_failed_run_and_never_retries():
    db = session()
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response(status=40501))
    client = DataForSEOClient(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="Run 1"):
        run_serp_explorer(db, settings(), "test", location_code=2276,
            language_code="de", device="desktop", depth=10, confirmed=True, client=client)
    run = db.scalar(select(ResearchRun))
    request = db.scalar(select(ApiRequest))
    assert calls == 1
    assert run.status == "failed" and request.status == "failed"
    assert "Invalid request" in request.error_message
