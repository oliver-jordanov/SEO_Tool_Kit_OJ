from typing import Any

import httpx

from app.config import Settings


class DataForSEOError(RuntimeError):
    pass


class DataForSEOAuthError(DataForSEOError):
    pass


class DataForSEOClient:
    base_url = "https://api.dataforseo.com"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        if not settings.credentials_configured:
            raise DataForSEOAuthError("DataForSEO credentials are not configured in .env.")
        self._client = httpx.Client(
            base_url=self.base_url,
            auth=(settings.dataforseo_login, settings.dataforseo_password.get_secret_value()),
            timeout=settings.http_timeout_seconds,
            transport=transport,
            headers={"User-Agent": "seo-research-toolkit/0.1"},
        )

    def post(self, endpoint: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            response = self._client.post(endpoint, json=tasks)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise DataForSEOAuthError("DataForSEO authentication failed.") from exc
            raise DataForSEOError(f"DataForSEO HTTP error {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            raise DataForSEOError("DataForSEO request failed or timed out.") from exc
        data = response.json()
        if data.get("status_code") != 20000:
            raise DataForSEOError(data.get("status_message", "DataForSEO API error"))
        for task in data.get("tasks") or []:
            if task.get("status_code") != 20000:
                raise DataForSEOError(task.get("status_message", "DataForSEO task error"))
        return data

