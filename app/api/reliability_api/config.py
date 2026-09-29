from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "reliability-api"
    app_version: str = "dev"
    app_environment: str = "local"
    redis_url: str = "redis://127.0.0.1:6379/0"
    enable_failure_injection: bool = False
    log_level: str = "INFO"
    otel_console_exporter: bool = True

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
