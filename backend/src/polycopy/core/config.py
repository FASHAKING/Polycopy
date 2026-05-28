from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    app_secret: str = "change-me"
    fernet_key: str = ""
    # Global kill switch: when true, NO real orders are placed for anyone —
    # every copy is simulated (paper) end-to-end. Per-user /paper also exists.
    paper_trading: bool = False

    telegram_bot_token: str = ""
    telegram_bot_username: str = ""

    database_url: str = "sqlite+aiosqlite:///./polycopy.db"

    polymarket_data_api: str = "https://data-api.polymarket.com"
    polymarket_clob_api: str = "https://clob.polymarket.com"
    polymarket_gamma_api: str = "https://gamma-api.polymarket.com"
    polymarket_lb_api: str = "https://lb-api.polymarket.com"
    polygon_rpc: str = "https://polygon-rpc.com"
    polygon_chain_id: int = 137

    web_public_api_url: str = "http://localhost:8000"
    # Public base URL of the web dashboard, used to build /login magic links.
    dashboard_url: str = "http://localhost:3000"
    # Comma-separated allowed origins for the API. "*" is fine for local dev;
    # set explicit origins in production.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() in ("prod", "production")

    def check_production_secrets(self) -> list[str]:
        """Return a list of insecure-default problems when running in prod."""
        problems: list[str] = []
        if not self.is_prod:
            return problems
        if not self.fernet_key:
            problems.append("FERNET_KEY is not set")
        if self.app_secret in ("", "change-me"):
            problems.append("APP_SECRET is unset or still the default")
        if self.cors_origins.strip() == "*":
            problems.append("CORS_ORIGINS is '*' — set explicit origins in production")
        return problems

    watcher_poll_interval: int = Field(default=15, ge=2)
    scout_poll_interval: int = Field(default=3600, ge=60)
    reconcile_poll_interval: int = Field(default=30, ge=5)


@lru_cache
def get_settings() -> Settings:
    return Settings()
