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

    @field_validator("API_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: list[str] | str) -> list[str] | str:
        if isinstance(v, str) and not v.startswith("["):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
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


settings = Settings()
