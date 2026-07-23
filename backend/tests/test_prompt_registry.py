"""AI 提示词统一注册表测试。"""

from app.models.prompt_templates import PromptTemplate
from app.prompts import DEFAULT_PROMPTS, SYSTEM_PROMPTS, get_default_prompt, get_system_prompt
from app.services.ai.prompt_service import get_prompt_template
from app.services.ai.seed_prompts import seed_prompts


def test_default_prompt_registry_has_unique_types_and_required_placeholders():
    definitions = {item.type: item for item in DEFAULT_PROMPTS}

    assert set(definitions) == {
        "speech_score",
        "trend_analysis",
        "anomaly_detection",
        "optimization",
        "high_intent",
        "qa",
    }
    assert "{transcript}" in definitions["speech_score"].content
    assert "{sessions_data}" in definitions["trend_analysis"].content
    assert "{session_data}" in definitions["anomaly_detection"].content
    assert "{history_data}" in definitions["anomaly_detection"].content
    assert "{knowledge_context}" in definitions["qa"].content
    assert "{question}" in definitions["qa"].content


def test_system_prompt_registry_rejects_unknown_names():
    assert set(SYSTEM_PROMPTS) >= {
        "connection_test",
        "speech_score",
        "trend_analysis",
        "anomaly_detection",
        "optimization",
        "high_intent",
        "knowledge_qa",
    }
    assert get_system_prompt("knowledge_qa")


def test_prompt_service_uses_versioned_code_default_only_when_database_is_missing(db):
    fallback = get_prompt_template(db, "qa")
    unknown_version = get_prompt_template(db, "qa", version=999)

    assert fallback is not None
    assert fallback.id is None
    assert fallback.version == get_default_prompt("qa").version
    assert unknown_version is None


def test_seed_prompts_fills_missing_versions_without_creating_duplicates(db):
    seed_prompts(db)
    seed_prompts(db)

    assert db.query(PromptTemplate).count() == len(DEFAULT_PROMPTS)
