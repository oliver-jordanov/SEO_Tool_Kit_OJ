import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import ResearchRun
from app.services.foundation import (
    cost_total,
    keyword_difficulty,
    keyword_overview,
    keyword_overview_item,
    response_for_run,
)
from app.services.serp_explorer import RUN_TYPE, run_serp_explorer, serp_data_for_run, serp_request_for_run
from app.services.backlink_explorer import (RUN_TYPE as BACKLINK_RUN_TYPE, data_for_run as backlink_data_for_run,
    raw_responses_for_run, requests_for_run, run_backlink_explorer)

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=ROOT / "templates")


def safe_http_url(value: object) -> str:
    from urllib.parse import urlsplit
    text = str(value or "")
    try:
        return text if urlsplit(text).scheme.lower() in {"http", "https"} else ""
    except ValueError:
        return ""


templates.env.filters["safe_http_url"] = safe_http_url


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_settings().ensure_localhost()
    yield


app = FastAPI(title="DataForSEO Research Toolkit", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    runs = db.scalars(select(ResearchRun).order_by(ResearchRun.id.desc()).limit(10)).all()
    return templates.TemplateResponse(request, "index.html", {
        "runs": runs,
        "total_cost": cost_total(db),
        "credentials": get_settings().credentials_configured,
        "result": None,
        "keyword_item": None,
        "keyword_difficulty": None,
        "error": None,
        "serp_result": None,
        "backlink_result": None,
    })


@app.post("/foundation/keyword-overview", response_class=HTMLResponse)
def run_foundation(
    request: Request,
    keyword: str = Form(...),
    confirm_cost: bool = Form(False),
    force_refresh: bool = Form(False),
    db: Session = Depends(get_db),
):
    result = None
    error = None
    try:
        result = keyword_overview(
            db, get_settings(), keyword, confirmed=confirm_cost, force_refresh=force_refresh
        )
    except Exception as exc:
        error = str(exc)
    runs = db.scalars(select(ResearchRun).order_by(ResearchRun.id.desc()).limit(10)).all()
    return templates.TemplateResponse(request, "index.html", {
        "runs": runs,
        "total_cost": cost_total(db),
        "credentials": get_settings().credentials_configured,
        "result": result,
        "keyword_item": keyword_overview_item(result.response) if result else None,
        "keyword_difficulty": keyword_difficulty(keyword_overview_item(result.response)) if result else None,
        "error": error,
        "serp_result": None,
        "backlink_result": None,
    })


@app.post("/serp-explorer", response_class=HTMLResponse)
def run_serp(request: Request, keyword: str = Form(...), location_code: int = Form(2276),
             language_code: str = Form("de"), device: str = Form("desktop"),
             depth: int = Form(10), own_domain: str = Form(""),
             confirm_cost: bool = Form(False), db: Session = Depends(get_db)):
    result = None
    error = None
    try:
        result = run_serp_explorer(db, get_settings(), keyword, location_code=location_code,
            language_code=language_code, device=device, depth=depth,
            own_domain=own_domain, confirmed=confirm_cost)
    except Exception as exc:
        error = str(exc)
    runs = db.scalars(select(ResearchRun).order_by(ResearchRun.id.desc()).limit(10)).all()
    return templates.TemplateResponse(request, "index.html", {
        "runs": runs, "total_cost": cost_total(db),
        "credentials": get_settings().credentials_configured,
        "result": None, "keyword_item": None, "keyword_difficulty": None,
        "error": error, "serp_result": result, "backlink_result": None,
    })


@app.post("/backlink-explorer", response_class=HTMLResponse)
def run_backlinks(request: Request, target: str = Form(...), include_subdomains: bool = Form(False),
                  limit: int = Form(100), mode: str = Form("one_per_domain"),
                  confirm_cost: bool = Form(False), db: Session = Depends(get_db)):
    result = None; error = None
    try:
        result = run_backlink_explorer(db, get_settings(), target,
            include_subdomains=include_subdomains, limit=limit, mode=mode, confirmed=confirm_cost)
    except Exception as exc:
        error = str(exc)
    runs = db.scalars(select(ResearchRun).order_by(ResearchRun.id.desc()).limit(10)).all()
    return templates.TemplateResponse(request, "index.html", {"runs": runs,
        "total_cost": cost_total(db), "credentials": get_settings().credentials_configured,
        "result": None, "keyword_item": None, "keyword_difficulty": None,
        "error": error, "serp_result": None, "backlink_result": result})


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: int, request: Request, db: Session = Depends(get_db)):
    run = db.get(ResearchRun, run_id)
    if run is None:
        return templates.TemplateResponse(request, "run_detail.html", {
            "run": None, "keyword_item": None, "keyword_difficulty": None, "raw_response": None,
            "serp_rows": [], "serp_features": [], "api_request": None, "parameters": {},
            "backlink_summary": {}, "backlink_domains": [], "backlink_rows": [],
            "backlink_requests": [], "backlink_raw": {},
        }, status_code=404)
    response = response_for_run(db, run)
    item = keyword_overview_item(response or {}) if run.function not in {RUN_TYPE, BACKLINK_RUN_TYPE} else None
    serp_rows, serp_features = serp_data_for_run(db, run.id) if run.function == RUN_TYPE else ([], [])
    backlink_summary, backlink_domains, backlink_rows = backlink_data_for_run(db, run.id) if run.function == BACKLINK_RUN_TYPE else ({}, [], [])
    return templates.TemplateResponse(request, "run_detail.html", {
        "run": run,
        "keyword_item": item,
        "keyword_difficulty": keyword_difficulty(item),
        "raw_response": response,
        "serp_rows": serp_rows, "serp_features": serp_features,
        "api_request": serp_request_for_run(db, run.id),
        "parameters": json.loads(run.parameters_json),
        "backlink_summary": backlink_summary, "backlink_domains": backlink_domains,
        "backlink_rows": backlink_rows,
        "backlink_requests": requests_for_run(db, run.id) if run.function == BACKLINK_RUN_TYPE else [],
        "backlink_raw": raw_responses_for_run(db, run.id) if run.function == BACKLINK_RUN_TYPE else {},
    })
