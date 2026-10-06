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
