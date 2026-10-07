from app.core.config import Settings


def test_default_settings():
    settings = Settings()
    assert settings.PROJECT_NAME == "ZESTORA API"
    assert settings.VERSION == "0.1.0"
    assert settings.API_ENV == "development"
    assert settings.API_DEBUG is True
    assert settings.API_HOST == "127.0.0.1"
    assert settings.API_PORT == 8000
    assert settings.API_CORS_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert settings.DATABASE_URL == (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/zestora_dev"
    )
    assert settings.DB_POOL_SIZE == 5
    assert settings.DB_MAX_OVERFLOW == 10
    assert settings.safe_database_url == (
        "postgresql+asyncpg://postgres:***@localhost:5432/zestora_dev"
    )


def test_backward_compatibility_properties():
    settings = Settings()
    assert settings.HOST == settings.API_HOST
    assert settings.PORT == settings.API_PORT
    assert settings.DEBUG == settings.API_DEBUG
    assert settings.CORS_ORIGINS == settings.API_CORS_ORIGINS


def test_custom_settings_and_cors_parsing():
    settings = Settings(
        API_HOST="0.0.0.0",
        API_PORT=9000,
        API_ENV="production",
        API_DEBUG=False,
        API_CORS_ORIGINS="https://zestora.app, https://admin.zestora.app",
    )
    assert settings.API_HOST == "0.0.0.0"
    assert settings.API_PORT == 9000
    assert settings.API_ENV == "production"
    assert settings.API_DEBUG is False
    assert settings.API_CORS_ORIGINS == [
        "https://zestora.app",
        "https://admin.zestora.app",
    ]
    # Check properties match
    assert settings.HOST == "0.0.0.0"
    assert settings.PORT == 9000
    assert settings.DEBUG is False
    assert settings.CORS_ORIGINS == [
        "https://zestora.app",
        "https://admin.zestora.app",
    ]


def test_database_url_validation():
    # Standard postgresql:// schema should be converted to postgresql+asyncpg://
    s1 = Settings(DATABASE_URL="postgresql://user:secret@db.host:5432/db")
    assert s1.DATABASE_URL == "postgresql+asyncpg://user:secret@db.host:5432/db"
    assert s1.safe_database_url == "postgresql+asyncpg://user:***@db.host:5432/db"

    # Legacy postgres:// schema should also be converted
    s2 = Settings(DATABASE_URL="postgres://user:secret@db.host:5432/db")
    assert s2.DATABASE_URL == "postgresql+asyncpg://user:secret@db.host:5432/db"

    # Explicit asyncpg url should remain untouched
    s3 = Settings(DATABASE_URL="postgresql+asyncpg://user:secret@db.host:5432/db")
    assert s3.DATABASE_URL == "postgresql+asyncpg://user:secret@db.host:5432/db"
