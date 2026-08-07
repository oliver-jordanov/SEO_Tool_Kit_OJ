from decimal import Decimal

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api_clients.dataforseo import DataForSEOClient
from app.config import Settings
from app.db import Base
from app.models import ApiRequest, CacheEntry, CostLedger, ResearchRun
from app.normalization import normalize_domain, normalize_keyword, request_hash
from app.security import redact
from app.services.foundation import keyword_difficulty, keyword_overview, keyword_overview_item, response_for_run


def settings() -> Settings:
    return Settings(dataforseo_login="user", dataforseo_password="secret", database_url="sqlite:///:memory:")


def response(task_id="task-1"):
    return {"status_code": 20000, "tasks": [{"id": task_id, "status_code": 20000, "cost": 0.01212, "result": [{"items": []}]}]}


def mock_client(data):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    return DataForSEOClient(settings(), transport=transport)


def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_redaction_and_normalization():
    assert redact({"Authorization": "Basic abc", "nested": {"password": "x"}}) == {"Authorization": "[REDACTED]", "nested": {"password": "[REDACTED]"}}
    assert normalize_domain("https://WWW.Example.com/path") == "example.com"
    assert normalize_keyword("  kredit   test ") == "kredit test"


def test_hash_is_stable_and_mapper_sensitive():
    assert request_hash("/x", [{"b": 2, "a": 1}]) == request_hash("/x", [{"a": 1, "b": 2}])


def test_keyword_difficulty_distinguishes_missing_from_zero():
    assert keyword_difficulty(None) is None
    assert keyword_difficulty({}) is None
    assert keyword_difficulty({"keyword_properties": {"keyword_difficulty": None}}) is None
    assert keyword_difficulty({"keyword_properties": {"keyword_difficulty": 0}}) == 0
    assert keyword_difficulty({"keyword_properties": {"keyword_difficulty": 42}}) == 42


def test_confirmation_required_on_cache_miss():
    db = session()
    try:
        keyword_overview(db, settings(), "test", confirmed=False, client=mock_client(response()))
        assert False
    except PermissionError:
        pass


def test_api_run_is_persisted_and_second_run_hits_cache():
    db = session()
    first = keyword_overview(db, settings(), "test", confirmed=True, client=mock_client(response()))
    second = keyword_overview(db, settings(), "test", confirmed=False, client=mock_client(response("unused")))
    assert first.cache_hit is False and first.cost_usd == Decimal("0.01212")
    assert second.cache_hit is True and second.cost_usd == 0
    assert len(db.scalars(select(ResearchRun)).all()) == 2
    assert len(db.scalars(select(ApiRequest)).all()) == 1
    assert len(db.scalars(select(CacheEntry)).all()) == 1
    assert db.scalar(select(CostLedger.actual_cost_usd)) == Decimal("0.012120")


def test_force_refresh_creates_second_paid_request():
    db = session()
    keyword_overview(db, settings(), "test", confirmed=True, client=mock_client(response("a")))
    keyword_overview(db, settings(), "test", confirmed=True, force_refresh=True, client=mock_client(response("b")))
    assert len(db.scalars(select(ApiRequest)).all()) == 2


def test_result_can_be_mapped_and_reloaded_for_api_and_cache_runs():
    db = session()
    data = response()
    data["tasks"][0]["result"][0]["items"] = [{
        "keyword": "test", "keyword_info": {"search_volume": 100}
    }]
    first = keyword_overview(db, settings(), "test", confirmed=True, client=mock_client(data))
    second = keyword_overview(db, settings(), "test", confirmed=False, client=mock_client(response("unused")))
    first_run = db.get(ResearchRun, first.run_id)
    second_run = db.get(ResearchRun, second.run_id)
    assert keyword_overview_item(response_for_run(db, first_run))["keyword"] == "test"
    assert keyword_overview_item(response_for_run(db, second_run))["keyword_info"]["search_volume"] == 100
