from pathlib import Path

import pytest

from app.core.config import Settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]


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


def test_production_allows_documented_seven_character_database_password():
    errors, _ = make_settings(DEBUG=False, DB_PASSWORD="root123", JWT_SECRET_KEY="x" * 32).runtime_configuration_issues()

    assert "DATABASE_PASSWORD_INSECURE" not in errors


def test_local_debug_allows_documented_first_run_database_password():
    errors, _ = make_settings(DEBUG=True, DB_PASSWORD="root123").runtime_configuration_issues()

    assert "DATABASE_PASSWORD_INSECURE" not in errors


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


@pytest.mark.parametrize("url", [
    "https://remote-model.example/v1",
    "http://127.0.0.1:11434/not-v1",
    "http://user:password@localhost:11434/v1",
    "http://localhost:11434/v1?redirect=remote",
    "http://localhost:99999/v1",
    "http://[invalid/v1",
])
def test_ollama_must_use_local_loopback_address(url):
    errors, _ = make_settings(OLLAMA_BASE_URL=url).runtime_configuration_issues()

    assert "OLLAMA_BASE_URL_NOT_LOCAL" in errors


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434/v1", "http://localhost:11434/v1/", "http://[::1]:11434/v1",
])
def test_valid_local_ollama_addresses(url):
    errors, _ = make_settings(OLLAMA_BASE_URL=url).runtime_configuration_issues()
    assert "OLLAMA_BASE_URL_NOT_LOCAL" not in errors


def test_ollama_model_and_timeout_are_validated():
    errors, _ = make_settings(OLLAMA_MODEL="", OLLAMA_REQUEST_TIMEOUT_SECONDS=10).runtime_configuration_issues()

    assert "OLLAMA_MODEL_MISSING" in errors
    assert "OLLAMA_TIMEOUT_INVALID" in errors


def test_alembic_uses_runtime_database_configuration_without_stored_password():
    env_source = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    ini_source = (BACKEND_ROOT / "alembic.ini").read_text(encoding="utf-8")

    assert 'config.set_main_option("sqlalchemy.url", settings.db_url.replace("%", "%%"))' in env_source
    assert "root123" not in ini_source
    assert "mysql+pymysql://localhost/douyin_live" in ini_source


def test_one_click_start_requires_core_health_and_keeps_optional_services_optional():
    start_source = (BACKEND_ROOT.parent / "start.sh").read_text(encoding="utf-8")

    assert "scripts.check_local_ai --service-url" in start_source
    assert "OLLAMA_NO_CLOUD=1" in start_source
    assert "OLLAMA_NUM_PARALLEL=1" in start_source
    assert "ollama pull" not in start_source

    assert "docker compose up -d mysql redis qdrant" in start_source
    assert 'if [ "$RUN_MODE" = "full" ] && [ -f "$ROOT_DIR/dataease/conf/application.yml" ]; then' in start_source
    assert "docker compose --profile observability up -d prometheus grafana" in start_source
    assert "if ! wait_for_backend; then" in start_source
    assert '[ "$DATAEASE_DB_READY" = "true" ] && wait_for_dataease' in start_source
    assert "scripts/check_dataease_crypto.py" in start_source
    assert "local ATTEMPTS=600" in start_source
    assert "douyinLive.dataeaseKeySha256" in start_source
    assert 'wait_for_http "Prometheus"' in start_source
    assert 'wait_for_http "Grafana"' in start_source
    assert 'wait_for_http "Qdrant"' in start_source
    assert "docker compose --profile funasr up -d funasr" in start_source
    assert 'if [ "$RUN_MODE" = "lite" ] || [ "$(env_value ASR_AUTO_START)" != "true" ]; then' in start_source
    assert 'FUNASR_WAIT_SECONDS="$(env_value ASR_ENGINE_READY_TIMEOUT_SECONDS)"' in start_source
    assert "FunASR 容器异常退出，主系统将继续启动" in start_source
    assert "FunASR 在 ${FUNASR_WAIT_SECONDS} 秒内未就绪，将在后台继续加载" in start_source
    assert start_source.index('echo "[2/6] 启动 Prometheus 与 Grafana..."') < start_source.index(
        'echo "[3/6] 启动后端 FastAPI..."'
    )
    assert start_source.index("if ! wait_for_backend; then") < start_source.index('echo "  ✅ 后端: http://localhost:8000"')
    assert start_source.index('[ "$DATAEASE_DB_READY" = "true" ] && wait_for_dataease') < start_source.index(
        'echo "  ✅ DataEase: http://localhost:8100"'
    )
