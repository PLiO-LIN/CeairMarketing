from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def resolve_env_file() -> str | None:
    """Resolve .env in both the repository checkout and the container image."""
    parents = list(Path(__file__).resolve().parents)
    candidates = [
        parents[3] / ".env" if len(parents) > 3 else None,
        parents[2] / ".env" if len(parents) > 2 else None,
        Path("/app/.env"),
    ]
    return next((str(path) for path in candidates if path is not None and path.is_file()), None)


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

    # Resolve the repository env file independent of the process working directory.
    model_config = SettingsConfigDict(env_file=resolve_env_file(), extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def validate_production(self) -> None:
        if self.environment.lower() not in {"production", "prod"}:
            return
        if self.database_url.startswith("sqlite"):
            raise RuntimeError("生产环境必须使用 PostgreSQL，不允许使用 SQLite")
        if len(self.token_secret) < 32 or self.token_secret == "development-only-change-me":
            raise RuntimeError("生产环境必须配置长度不少于 32 位的 TOKEN_SECRET")
        if len(self.encryption_key) < 32:
            raise RuntimeError("生产环境必须配置 ENCRYPTION_KEY")
        if self.initial_admin_password in {"", "Admin@12345", "replace-with-a-long-random-password"}:
            raise RuntimeError("生产环境必须配置 INITIAL_ADMIN_PASSWORD")
        if self.cors_origins.strip() in {"", "*"}:
            raise RuntimeError("生产环境必须配置明确的 CORS_ORIGINS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
