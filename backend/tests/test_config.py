from app.config import Settings


def test_settings_use_safe_local_database_defaults(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_name == "Smart Credit Cabinet API"
    assert settings.database_url == (
        "postgresql+asyncpg://credit:credit@localhost:55432/credit"
    )


def test_settings_can_read_database_url_from_environment(
    monkeypatch,
) -> None:
    database_url = "postgresql+asyncpg://user:pass@db:5432/app"
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert Settings().database_url == database_url