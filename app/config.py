from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DataForSEO Research Toolkit"
    app_host: str = "127.0.0.1"
    app_port: int = 8765
    database_url: str = "sqlite:///./data/seo_toolkit.db"
    dataforseo_login: str = ""
    dataforseo_password: SecretStr = Field(default=SecretStr(""))
    cost_confirmation_threshold_usd: float = 0.10
    http_timeout_seconds: float = 60

    @property
    def credentials_configured(self) -> bool:
        return bool(self.dataforseo_login and self.dataforseo_password.get_secret_value())

    def ensure_localhost(self) -> None:
        if self.app_host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Phase 1 may only bind to localhost (127.0.0.1).")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_localhost()
    Path("data").mkdir(exist_ok=True)
    return settings

