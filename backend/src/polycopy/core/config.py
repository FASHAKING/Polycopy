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

    telegram_bot_token: str = ""
    telegram_bot_username: str = ""

    database_url: str = "sqlite+aiosqlite:///./polycopy.db"

    polymarket_data_api: str = "https://data-api.polymarket.com"
    polymarket_clob_api: str = "https://clob.polymarket.com"
    polymarket_gamma_api: str = "https://gamma-api.polymarket.com"
    polygon_rpc: str = "https://polygon-rpc.com"

    web_public_api_url: str = "http://localhost:8000"

    watcher_poll_interval: int = Field(default=15, ge=2)
    scout_poll_interval: int = Field(default=3600, ge=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()
