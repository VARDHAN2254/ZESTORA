from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings configured via environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "ZESTORA API"
    VERSION: str = "0.1.0"
    API_ENV: str = "development"
    API_DEBUG: bool = True

    # Server settings
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # CORS configuration
    API_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Database configuration
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/zestora_dev"
    )
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False

    @field_validator("API_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: list[str] | str) -> list[str] | str:
        if isinstance(v, str) and not v.startswith("["):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            if v.startswith("postgresql://"):
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    # Convenience properties for backward compatibility
    @property
    def HOST(self) -> str:
        return self.API_HOST

    @property
    def PORT(self) -> int:
        return self.API_PORT

    @property
    def DEBUG(self) -> bool:
        return self.API_DEBUG

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return self.API_CORS_ORIGINS

    @property
    def safe_database_url(self) -> str:
        """Return DATABASE_URL with credentials masked for safe logging."""
        from urllib.parse import urlsplit, urlunsplit

        parsed = urlsplit(self.DATABASE_URL)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return urlunsplit(
                (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
            )
        return self.DATABASE_URL


settings = Settings()
