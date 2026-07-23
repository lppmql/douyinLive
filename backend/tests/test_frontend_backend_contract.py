import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.v1.ws import list_transcript_segments
from app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_API_ROOT = PROJECT_ROOT / "frontend" / "src" / "service" / "api"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def iter_backend_request_calls(source: str):
    """提取 backendRequest(...) 调用，兼容泛型和多行对象。"""
    position = 0
    while True:
        start = source.find("backendRequest", position)
        if start < 0:
            return
        opening = source.find("(", start)
        if opening < 0:
            return

        depth = 0
        quote = None
        escaped = False
        for index in range(opening, len(source)):
            char = source[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in {'"', "'", "`"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    yield source[start : index + 1]
                    position = index + 1
                    break
        else:
            return


def normalize_api_path(path: str) -> str:
    path = path.replace("${API_PREFIX}", "/api/v1")
    path = re.sub(r"\$\{[^}]+}", "{param}", path)
    path = re.sub(r"{[^}]+}", "{param}", path)
    return path.rstrip("/") or "/"


def frontend_contracts():
    contracts = set()
    for api_file in FRONTEND_API_ROOT.glob("*.ts"):
        source = api_file.read_text(encoding="utf-8")
        for call in iter_backend_request_calls(source):
            url_match = re.search(r"url:\s*([`'\"])(.*?)\1", call, re.DOTALL)
            if not url_match:
                continue
            path = url_match.group(2)
            if not (path.startswith("/") or path.startswith("${API_PREFIX}")):
                continue
            method_match = re.search(r"method:\s*['\"](get|post|put|patch|delete)['\"]", call, re.IGNORECASE)
            method = method_match.group(1).upper() if method_match else "GET"
            contracts.add((method, normalize_api_path(path)))
    return contracts


def backend_contracts():
    return {
        (method.upper(), normalize_api_path(path))
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method in HTTP_METHODS
    }


def test_every_frontend_backend_request_exists_in_fastapi_openapi():
    missing = sorted(frontend_contracts() - backend_contracts())

    assert missing == [], f"前端调用了后端不存在的接口: {missing}"


def test_collector_query_names_match_fastapi_contract():
    source = (FRONTEND_API_ROOT / "douyin.ts").read_text(encoding="utf-8")

    assert "params?: { task_id?: number; level?: string; limit?: number }" in source
    assert "params?: { status?: string; task_type?: string }" in source
    assert "taskId?: number" not in source
    assert "taskType?: string" not in source


def test_frontend_request_layer_does_not_bundle_fixed_api_tokens():
    source = (PROJECT_ROOT / "frontend" / "src" / "service" / "request" / "index.ts").read_text(encoding="utf-8")

    assert "apifoxToken" not in source


def test_transcript_websocket_uses_backend_service_and_vite_ws_proxy():
    realtime_source = (
        PROJECT_ROOT
        / "frontend"
        / "src"
        / "views"
        / "transcripts"
        / "composables"
        / "useTranscriptRealtime.ts"
    ).read_text(
        encoding="utf-8",
    )
    proxy_source = (PROJECT_ROOT / "frontend" / "build" / "config" / "proxy.ts").read_text(encoding="utf-8")

    assert "getServiceBaseURL" in realtime_source
    assert "otherBaseURL.backend" in realtime_source
    assert "VITE_SERVICE_BASE_URL" not in realtime_source
    assert "ws: true" in proxy_source


def test_transcript_segment_payload_contains_declared_session_id():
    segment = SimpleNamespace(
        id=7,
        session_id=99,
        segment_start=1.5,
        segment_end=3.0,
        text_content="真实转写内容",
        segment_type="知识讲解",
        asr_status="completed",
        ai_score=88,
    )
    query = MagicMock()
    query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [segment]
    db = MagicMock()
    db.query.return_value = query

    payload = list_transcript_segments(99, db=db)

    assert payload[0]["session_id"] == 99
