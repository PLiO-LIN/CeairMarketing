from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "China Eastern Intelligent Marketing Platform API"
    environment: str = "development"
    database_url: str = "sqlite:///./ceair-marketing.db"
    encryption_key: str = ""
    cors_origins: str = "http://127.0.0.1:8780,http://localhost:8780"
    token_secret: str = "development-only-change-me"
    token_ttl_minutes: int = 480
    initial_admin_username: str = "admin"
    initial_admin_password: str = "Admin@12345"
    bootstrap_model_display_name: str = "预置大模型服务"
    bootstrap_model_base_url: str = ""
    bootstrap_model_name: str = ""
    bootstrap_model_api_key: str = ""
    bootstrap_mineru_base_url: str = "https://mineru.net"
    bootstrap_mineru_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
