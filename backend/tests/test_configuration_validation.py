from app.core.config import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "DEBUG": True,
        "DB_PASSWORD": "local-test-password",
        "JWT_SECRET_KEY": "local-test-secret",
        "DB_USER": "douyin_app",
        "DATAEASE_READER_PASSWORD": "dataease-test-password",
        "REDIS_URL": "redis://:redis-test-password@localhost:6379/0",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_runtime_configuration_has_no_issues():
    errors, warnings = make_settings().runtime_configuration_issues()

    assert errors == []
    assert warnings == []


def test_production_rejects_default_or_short_jwt_secret():
    errors, _ = make_settings(DEBUG=False, JWT_SECRET_KEY="short").runtime_configuration_issues()

    assert "JWT_SECRET_INSECURE" in errors


def test_production_rejects_short_database_password():
    errors, _ = make_settings(DEBUG=False, DB_PASSWORD="short", JWT_SECRET_KEY="x" * 32).runtime_configuration_issues()

    assert "DATABASE_PASSWORD_INSECURE" in errors


def test_unsafe_local_services_are_reported_without_exposing_secrets():
    errors, warnings = make_settings(
        DB_USER="root",
        REDIS_URL="redis://localhost:6379",
        DATAEASE_READER_PASSWORD="dataease_reader_change_me",
    ).runtime_configuration_issues()

    assert errors == []
    assert warnings == [
        "DATABASE_ROOT_USER",
        "REDIS_AUTH_DISABLED",
        "DATAEASE_READER_PASSWORD_INSECURE",
    ]


def test_redis_url_is_redacted_for_logs():
    settings = make_settings(REDIS_URL="redis://collector:do-not-log@127.0.0.1:6379/2")

    assert settings.redacted_redis_url == "redis://127.0.0.1:6379/2"
    assert "do-not-log" not in settings.redacted_redis_url
