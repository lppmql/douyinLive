"""本地模型协议与资源释放测试；测试替身不会请求网络或写业务数据库。"""

from pathlib import Path
from types import SimpleNamespace
from builtins import ExceptionGroup

import pytest
import anyio

from app.core.config import settings
from app.services.ai import llm_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


class StubStream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for item in self.chunks:
            yield item

    async def close(self):
        self.closed = True


def chunk(text="", finish_reason=None, usage=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=finish_reason)],
        usage=usage,
    )


def install_response(monkeypatch, response):
    calls, observations = [], []

    def create(**kwargs):
        calls.append(kwargs)
        return response

    monkeypatch.setattr(llm_client, "get_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    async def async_create(**kwargs):
        return create(**kwargs)

    async def async_close():
        pass

    monkeypatch.setattr(llm_client, "get_async_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=async_create)), close=async_close,
    ))
    monkeypatch.setattr(llm_client, "record_ai_call", observations.append)
    return calls, observations


def test_client_is_local_and_disables_proxy_redirects_and_retries(monkeypatch):
    monkeypatch.setattr(llm_client, "_client", None)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    client = llm_client.get_client()
    try:
        assert str(client.base_url) == "http://127.0.0.1:11434/v1/"
        assert client.max_retries == 0
        assert client._client.trust_env is False
        assert client._client.follow_redirects is False
    finally:
        client.close()


def test_standalone_client_also_rejects_remote_url(monkeypatch):
    monkeypatch.setattr(llm_client, "_client", None)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "https://remote.example/v1")
    with pytest.raises(ValueError, match="本机"):
        llm_client.get_client()


@pytest.mark.parametrize("content,finish_reason", [("", "stop"), ("{}", "length"), ("[]", "stop")])
def test_empty_truncated_and_non_object_json_are_failures(monkeypatch, content, finish_reason):
    response = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish_reason,
    )])
    calls, observations = install_response(monkeypatch, response)
    with pytest.raises(ValueError):
        llm_client.chat_json("返回对象", "协议校验")
    assert calls[0]["reasoning_effort"] == "none"
    assert observations[0].status == "failed"


@pytest.mark.anyio
async def test_stream_records_usage_and_releases_connection(monkeypatch):
    stream = StubStream([
        chunk("连接"), chunk("成功", "stop"),
        SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12)),
    ])
    calls, observations = install_response(monkeypatch, stream)
    assert "".join([part async for part in llm_client.chat_stream("连接测试", "请回复")]) == "连接成功"
    assert stream.closed
    assert calls[0]["max_tokens"] == 4096
    assert observations[0].status == "success"
    assert observations[0].total_tokens == 12


@pytest.mark.anyio
async def test_cancelled_stream_is_closed_and_not_reported_success(monkeypatch):
    stream = StubStream([chunk("连接"), chunk("成功")])
    _, observations = install_response(monkeypatch, stream)
    response = llm_client.chat_stream("连接测试", "请回复")
    assert await response.__anext__() == "连接"
    await response.aclose()
    assert stream.closed
    assert [item.status for item in observations] == ["cancelled"]


@pytest.mark.parametrize("chunks", [[], [chunk(finish_reason="length")]])
@pytest.mark.anyio
async def test_empty_or_truncated_stream_fails(monkeypatch, chunks):
    stream = StubStream(chunks)
    _, observations = install_response(monkeypatch, stream)
    with pytest.raises(ValueError):
        [part async for part in llm_client.chat_stream("连接测试", "请回复")]
    assert stream.closed
    assert observations[0].status == "failed"


def test_asr_worker_has_no_automatic_clip_entrypoint():
    """锁住已确认的人工边界，避免后续重构重新引入隐式剪辑。"""
    backend_root = Path(__file__).resolve().parents[1]
    worker_source = (backend_root / "workers/asr_worker.py").read_text(encoding="utf-8")
    assert "queue_clip_after_offline_final" not in worker_source
    assert "CLIP_AUTO_GENERATE" not in type(settings).model_fields
    assert not (backend_root / "app/services/clips/auto_queue.py").exists()


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["before_first_token", "send_backpressure", "send_error"])
async def test_qa_endpoint_disconnect_cancels_model_and_closes_http(monkeypatch, phase):
    """模拟实际 SSE 断开，不用手动关闭生成器来代替浏览器断开。"""
    from starlette.requests import ClientDisconnect
    from app.api.v1.ai import QaRequest, knowledge_qa_stream
    from app.services.ai import kb_service

    ready = anyio.Event()
    observations = []
    state = {"client_closed": False, "stream_closed": False}
    monkeypatch.setattr(kb_service, "_prepare_qa_context", lambda *_args: {
        "system_prompt": "连接测试", "user_message": "请回复", "sources": [],
        "prompt_template": SimpleNamespace(type="qa", version=1),
    })
    monkeypatch.setattr(llm_client, "record_ai_call", observations.append)

    class WaitingStream:
        async def __aiter__(self):
            yield chunk("连接")
            await anyio.sleep_forever()

        async def close(self):
            state["stream_closed"] = True

    async def create(**_kwargs):
        if phase == "before_first_token":
            ready.set()
            await anyio.sleep_forever()
        return WaitingStream()

    async def close_client():
        state["client_closed"] = True

    monkeypatch.setattr(llm_client, "get_async_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=close_client,
    ))

    async def receive():
        await ready.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            ready.set()
            if phase == "send_error":
                raise OSError("浏览器连接已关闭")
            await anyio.sleep_forever()

    response = knowledge_qa_stream(QaRequest(question="协议验收"), db=object())
    scope = {"type": "http", "asgi": {"spec_version": "2.4" if phase == "send_error" else "2.3"}}
    with anyio.fail_after(1):
        if phase == "send_error":
            # 项目当前 Starlette 会包装为异常组；新版本会抛 ClientDisconnect。
            with pytest.raises((ClientDisconnect, OSError, ExceptionGroup)) as raised:
                await response(scope, receive, send)
            if isinstance(raised.value, ExceptionGroup):
                assert all(isinstance(error, OSError) for error in raised.value.exceptions)
        else:
            await response(scope, receive, send)
    assert state["client_closed"]
    if phase != "before_first_token":
        assert state["stream_closed"]
    assert [item.status for item in observations] == ["cancelled"]
